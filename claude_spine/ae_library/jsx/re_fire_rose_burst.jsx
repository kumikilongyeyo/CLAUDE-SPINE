// re_fire_rose_burst: realistic version of fr_rose_v9 (same 7-petal silhouette, size and timing: the exact comp is
// used as the heat map, since its cel bands already run white > red > crimson > plum and its holes open on time).
// heat = exact luminance, softened, modulated by the explosion_02 fireball photo + gas noise, then gradient-mapped
// white-hot > yellow > orange > deep red; Kenney flames lick off the petal tips; embers fly; dark smoke lingers.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "fr_rose_v9", S = 3, D = 1.12;
  RE.purge("re_fire_rose_burst_v");
  var tag = "re_fire_rose_burst_v" + V;
  var src = RE.findComp(SRC), W = src.width, H = src.height, cx = 82 * S, cy = 100 * S;
  var f = FX.gt("fire_rose_burst");
  var rnd = FX.rng(9);
  var WH = FX.rgb("FFFBEC"), YEL = FX.rgb("FFD04A"), ORA = FX.rgb("FF7414"), RED = FX.rgb("B81E08"), DK = FX.rgb("2A0603");

  // the exact comp without its soft halo (the halo's noise leaks faint blobs all over the frame)
  var rose = RE.only(SRC, tag + "_rose", function (n) { return n !== "halo"; });
  // ---- heat field (grey on black): heat = 0.55 R + 0.45 G of the exact colours -> white 1.0, red .6, crimson .43,
  // plum .26 (white lobes white-hot, red petals orange, burnt centre deep red)
  var heat = FX.comp(tag + "_heat", W, H, 25, D, RE.FOLDER);
  FX.solid(heat, "black", [0, 0, 0]);
  var base = heat.layers.add(rose); base.name = "rose_heat";
  var cm = FX.fx(base, "ADBE CHANNEL MIXER");
  function cmSet(names, v) { for (var ci = 0; ci < names.length; ci++) { var pp = FX.find(cm, names[ci]); if (pp) { pp.setValue(v); return; } } throw new Error("channel mixer: " + names[0]); }
  var outs = ["Red", "Green", "Blue"];
  for (var oi = 0; oi < 3; oi++) {
    cmSet([outs[oi] + "-Red", outs[oi] + " - Red"], 52); cmSet([outs[oi] + "-Green", outs[oi] + " - Green"], 39);
    cmSet([outs[oi] + "-Blue", outs[oi] + " - Blue"], 0);
  }
  FX.blur(base, 1.5 * S);
  var gm = FX.fx(base, "ADBE Exposure2");   // cooling: gamma < 1 pulls the mids down over time (orange -> red -> burnt)
  FX.keys(FX.find(gm, "Gamma Correction"), [[f(1), 1.0], [f(4), 0.72], [f(8), 0.52], [f(14), 0.42]], false);
  // real fireball photo as heat detail (grey, overlay): its billows and hot spots break up the flat cel bands
  var ex = heat.layers.add(FX.imp(RE.R + "explosion_02.png")); ex.name = "fireball_detail";
  ex.anchorPoint.setValue([940, 660]); ex.position.setValue([cx, cy]);
  RE.circMask(ex, 940, 660, 430, 260);
  RE.tint(ex, [1, 1, 1]);
  var exo = FX.fx(ex, "ADBE Exposure2"); FX.set(exo, "Offset", 0.12);
  FX.keys(ex.scale, [[0, [8, 8]], [f(3), [24, 24]], [f(6), [30, 30]], [D, [36, 36]]], "out");
  FX.keys(ex.rotation, [[0, -10], [D, 25]], false);
  ex.blendingMode = BlendingMode.OVERLAY; ex.opacity.setValue(40);
  // billowy fire texture: Kenney fire blobs riding out on each petal (overlay on the heat)
  for (var b = 0; b < 7; b++) {
    var ba = (b * 360 / 7 + 8 - 90 + (rnd() - 0.5) * 20) * Math.PI / 180;
    var fb = heat.layers.add(FX.imp(RE.K + (b % 2 ? "fire_01.png" : "fire_02.png"))); fb.name = "billow" + b;
    FX.keys(fb.position, [[f(1), [cx + Math.cos(ba) * 8 * S, cy + Math.sin(ba) * 8 * S]], [f(5), [cx + Math.cos(ba) * 32 * S, cy + Math.sin(ba) * 32 * S]], [D, [cx + Math.cos(ba) * 42 * S, cy + Math.sin(ba) * 42 * S]]], "out");
    FX.keys(fb.scale, [[f(1), [10, 10]], [f(5), [24, 24]], [D, [30, 30]]], "out");
    FX.keys(fb.rotation, [[0, rnd() * 360], [D, rnd() * 360]], false);
    fb.blendingMode = BlendingMode.OVERLAY; fb.opacity.setValue(55);
  }
  // (no fractal-noise overlay here: its evolution aliased into an every-other-frame brightness flicker)
  // the heat field displaced like gas: one precomp so the colour layer and its alpha matte stay identical
  var gas = FX.comp(tag + "_gas", W, H, 25, D, RE.FOLDER);
  var hl = gas.layers.add(heat);
  var td = FX.fx(hl, "ADBE Turbulent Displace"); FX.set(td, "Amount", 24); FX.set(td, "Size", 4 * S); FX.set(td, "Complexity", 4);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 520]], false);
  FX.find(td, "Offset (Turbulence)").expression = "[" + cx + ", " + cy + " + time * 150]";
  var td2 = FX.fx(hl, "ADBE Turbulent Displace"); FX.set(td2, "Amount", 10); FX.set(td2, "Size", 12 * S); FX.set(td2, "Complexity", 2);
  FX.keys(FX.find(td2, "Evolution"), [[0, 0], [D, 300]], false);
  function heatMatte(cmp, name) {           // luma matte: anything warmer than ~0.25 is opaque, soft fiery edge below
    var m = cmp.layers.add(gas); m.name = name;
    var lvm = FX.fx(m, "ADBE Pro Levels2");
    lvm.property("ADBE Pro Levels2-0004").setValue(0.06); lvm.property("ADBE Pro Levels2-0005").setValue(0.28);
    return m;
  }
  function toner(l, a, b, cc, d, e) { var t = FX.fx(l, "CC Toner"); FX.set(t, "Tones", 3);
    FX.set(t, "Highlights", a); FX.set(t, "Brights", b); FX.set(t, "Midtones", cc); FX.set(t, "Darktones", d); FX.set(t, "Shadows", e); return t; }

  var c = RE.comp(tag, W, H, D);
  // ---- 1. dark smoke behind (normal blend): photo smoke + Kenney black smoke puffs drifting out and up
  for (var q = 0; q < 7; q++) {
    var a = (q * 360 / 7 + 8 + (rnd() - 0.5) * 20) * Math.PI / 180, r0 = 30 * S, r1 = (58 + rnd() * 14) * S;
    var bs = RE.tex(c, RE.KS + "Black smoke/blackSmoke" + ((q * 2 + 2) < 10 ? "0" : "") + (q * 2 + 2) + ".png", "smoke_back" + q, { blend: BlendingMode.NORMAL });
    RE.tint(bs, FX.rgb("332824"), FX.rgb("0A0807"));
    FX.keys(bs.position, [[f(4), [cx + Math.cos(a) * r0, cy + Math.sin(a) * r0]], [D, [cx + Math.cos(a) * r1, cy + Math.sin(a) * r1 - 22 * S]]], "out");
    FX.keys(bs.scale, [[f(4), [30, 30]], [D, [62 + rnd() * 20, 62 + rnd() * 20]]], "out");
    FX.keys(bs.rotation, [[f(4), rnd() * 360], [D, rnd() * 360]], false);
    FX.keys(bs.opacity, [[f(4), 0], [f(9), 65], [f(18), 50], [D, 0]], false);
  }
  var ps = RE.tex(c, RE.R + "smoke_04.png", "smoke_photo", { blend: BlendingMode.NORMAL, mask: 200, inset: 80, pos: [cx, cy - 10 * S] });
  RE.tint(ps, FX.rgb("3E322E"), FX.rgb("0A0807"));
  FX.keys(ps.scale, [[f(6), [30, 30]], [D, [46, 46]]], false);
  FX.keys(ps.position, [[f(6), [cx, cy]], [D, [cx, cy - 26 * S]]], false);
  FX.keys(ps.opacity, [[f(6), 0], [f(11), 55], [D, 10]], false);

  // ---- 2. outer heat halo (behind the body)
  var halo = c.layers.add(gas); halo.name = "halo";
  toner(halo, YEL, ORA, RED, FX.rgb("5A0C04"), [0, 0, 0]);
  FX.blur(halo, 9 * S);
  RE.lumAlpha(halo);
  halo.blendingMode = BlendingMode.ADD;
  FX.keys(halo.opacity, [[f(1), 0], [f(2), 80], [f(7), 60], [f(14), 25], [f(20), 0]], false);
  // ---- 2b. flame fringe: heat torn into rising wisps, additive, behind the body
  var fr = c.layers.add(heat); fr.name = "flame_fringe";
  var tf = FX.fx(fr, "ADBE Turbulent Displace"); FX.set(tf, "Amount", 85); FX.set(tf, "Size", 3 * S); FX.set(tf, "Complexity", 3);
  FX.keys(FX.find(tf, "Evolution"), [[0, 0], [D, 700]], false);
  FX.find(tf, "Offset (Turbulence)").expression = "[" + cx + ", " + cy + " + time * 220]";
  toner(fr, YEL, ORA, RED, FX.rgb("3A0802"), [0, 0, 0]);
  FX.blur(fr, 1 * S);
  RE.lumAlpha(fr);
  fr.blendingMode = BlendingMode.ADD;
  FX.keys(fr.opacity, [[f(1), 0], [f(2), 100], [f(9), 85], [f(16), 35], [f(21), 0]], false);
  // ---- 3. fire body: gradient-mapped heat, alpha from the heat itself (luma matte)
  var body = c.layers.add(gas); body.name = "fire_body";
  toner(body, WH, YEL, ORA, RED, DK);
  body.setTrackMatte(heatMatte(c, "fire_body_matte"), TrackMatteType.LUMA);
  var exa = RE.tex(c, RE.R + "explosion_02.png", "fireball_core_add", { pos: [cx, cy] });
  exa.anchorPoint.setValue([940, 660]);
  RE.circMask(exa, 940, 660, 420, 260);
  FX.keys(exa.scale, [[0, [8, 8]], [f(3), [22, 22]], [f(6), [26, 26]]], "out");
  FX.keys(exa.opacity, [[f(1), 0], [f(2), 45], [f(5), 25], [f(9), 0]], false);
  exa.setTrackMatte(heatMatte(c, "fireball_core_matte"), TrackMatteType.LUMA);

  // ---- 5. embers: specks in the burning rim + sparks flying out (rising a little)
  var sp = FX.noise(c, "ember_specks", { type: 1, noise: 4, contrast: 650, brightness: -165, scale: 2.5 * S, complexity: 2, seed: 17, evo: [[0, 0], [D, 2400]] });
  RE.tint(sp.layer, FX.rgb("FFA030")); sp.layer.blendingMode = BlendingMode.ADD;
  var spm = c.layers.add(rose); spm.name = "ember_specks_matte";
  FX.matte(sp.layer, spm, false);
  FX.keys(sp.layer.opacity, [[f(5), 0], [f(9), 100], [f(20), 60], [f(23), 0]], false);
  for (var e = 0; e < 40; e++) {
    var ea = rnd() * 360, ear = ea * Math.PI / 180, er = (28 + rnd() * 26) * S, t0 = f(4 + rnd() * 10), t1 = t0 + 0.25 + rnd() * 0.4;
    RE.spark(c, "ember" + e, [cx + Math.cos(ear) * er, cy + Math.sin(ear) * er], ea, (14 + rnd() * 34) * S, t0, t1,
             { len: (1.5 + rnd() * 3) * S, w: (0.6 + rnd() * 0.7) * S, color: rnd() < 0.3 ? YEL : ORA, grav: -(4 + rnd() * 10) * S });
  }
  // ---- 6. ignition flash and front smoke as it burns out
  var fx0 = RE.tex(c, RE.K + "flare_01.png", "ignite", { pos: [cx, cy] });
  RE.fill(fx0, WH);
  FX.keys(fx0.scale, [[f(0.8), [20, 20]], [f(2), [90, 90]], [f(4), [50, 50]]], false);
  FX.keys(fx0.opacity, [[f(0.8), 0], [f(1.5), 100], [f(3), 60], [f(5), 0]], false);
  for (var k = 0; k < 4; k++) {
    var ka = (k * 90 + 30) * Math.PI / 180;
    var fs = RE.tex(c, RE.KS + "Black smoke/blackSmoke1" + (k * 2 + 1) + ".png", "smoke_front" + k, { blend: BlendingMode.NORMAL });
    RE.tint(fs, FX.rgb("3A2E2A"), FX.rgb("0A0706"));
    FX.keys(fs.position, [[f(9), [cx + Math.cos(ka) * 22 * S, cy + Math.sin(ka) * 22 * S]], [D, [cx + Math.cos(ka) * 40 * S, cy + Math.sin(ka) * 40 * S - 18 * S]]], "out");
    FX.keys(fs.scale, [[f(9), [26, 26]], [D, [48, 48]]], "out");
    FX.keys(fs.rotation, [[f(9), k * 70], [D, k * 70 + 40]], false);
    FX.keys(fs.opacity, [[f(9), 0], [f(14), 40], [D, 0]], false);
  }
  var gb = FX.adj(c, "bloom"); var g = FX.glow(gb, 6 * S, 0.3, 88, YEL, ORA);
  FX.keys(FX.find(g, "Glow Intensity"), [[f(1), 0.9], [f(3), 0.35], [f(6), 0.12], [f(12), 0.08]], false);
  return FX.done(c);
}
