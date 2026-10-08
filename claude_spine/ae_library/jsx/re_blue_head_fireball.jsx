// re_blue_head_fireball: realistic version of ib_blue_head_fireball_v22 (the PROCEDURAL build; same size/timing).
// The exact cel body (white impact side, yellow lobes, red outlines, plum hollow, ember lines) is the heat map:
// heat = 0.52 R + 0.39 G with cooling gamma, textured by the explosion_02 fireball photo + Kenney fire puffs,
// gas-displaced, gradient-mapped white-hot > yellow > orange > red > burnt, alpha from the heat. Plus a refractive
// cyan shockwave shell (CC Glass), Advanced Lightning on the f6 flash with a flare, rising embers and Kenney black
// smoke drifting right.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "ib_blue_head_fireball_v22", S = 3, D = 24 / 25;
  RE.purge("re_blue_head_fireball_v");
  var tag = "re_blue_head_fireball_v" + V;
  var src = RE.findComp(SRC), W = src.width, H = src.height;
  var R = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24];
  function K(n) { var a = Math.floor(n), fr = n - a; if (a >= R.length - 1) return (R[R.length - 1] + (n - R.length + 1)) / 25; if (a < 0) return n / 25; return (R[a] + (R[a + 1] - R[a]) * fr) / 25; }
  function P(x, y) { return [x * S, y * S]; }
  var rnd = FX.rng(23);
  var WH = FX.rgb("FFFBEC"), YEL = FX.rgb("FFD04A"), ORA = FX.rgb("FF7414"), RED = FX.rgb("B81E08"), DK = FX.rgb("2A0603");
  var CORE = FX.rgb("F2F7FF"), PALE = FX.rgb("B8D4FF"), EBLUE = FX.rgb("5A78FF"), RIM = FX.rgb("8FE8F4");
  var body = RE.findComp(SRC + "_body");
  var pShell = RE.only(SRC, tag + "_shell", function (n) { return n === "shell"; });
  var pElec = RE.findComp(SRC + "_elec");

  // ---- heat field
  var heat = FX.comp(tag + "_heat", W, H, 25, D, RE.FOLDER);
  FX.solid(heat, "black", [0, 0, 0]);
  var base = heat.layers.add(body); base.name = "body_heat";
  var cm = FX.fx(base, "ADBE CHANNEL MIXER");
  var outs = ["Red", "Green", "Blue"];
  for (var oi = 0; oi < 3; oi++) {
    var mix = [["Red", 52], ["Green", 39], ["Blue", 0]];
    for (var mi = 0; mi < 3; mi++) if (!RE.trySet(cm, outs[oi] + "-" + mix[mi][0], mix[mi][1]) && !RE.trySet(cm, outs[oi] + " - " + mix[mi][0], mix[mi][1])) throw new Error("channel mixer names");
  }
  FX.blur(base, 1.2 * S);
  var gm = FX.fx(base, "ADBE Exposure2");
  FX.keys(FX.find(gm, "Gamma Correction"), [[K(6), 1.1], [K(7), 0.85], [K(9), 0.68], [K(12), 0.55], [K(16), 0.45]], false);
  var ex = heat.layers.add(FX.imp(RE.R + "explosion_02.png")); ex.name = "fireball_detail";
  ex.anchorPoint.setValue([940, 660]); RE.circMask(ex, 940, 660, 430, 260); RE.tint(ex, [1, 1, 1]);
  var exo = FX.fx(ex, "ADBE Exposure2"); FX.set(exo, "Offset", 0.12);
  FX.keys(ex.position, [[K(7), P(40, 58)], [K(11), P(62, 56)], [D, P(72, 52)]], "out");
  FX.keys(ex.scale, [[K(7), [8, 8]], [K(10), [20, 20]], [D, [24, 24]]], "out");
  ex.blendingMode = BlendingMode.OVERLAY; ex.opacity.setValue(45);
  for (var b = 0; b < 6; b++) {
    var fb = heat.layers.add(FX.imp(RE.K + (b % 2 ? "fire_01.png" : "fire_02.png"))); fb.name = "billow" + b;
    var ba = (b * 60 - 150) * Math.PI / 180;
    FX.keys(fb.position, [[K(7), P(40 + Math.cos(ba) * 6, 58 + Math.sin(ba) * 6)], [K(11), P(64 + Math.cos(ba) * 22, 56 + Math.sin(ba) * 22)], [D, P(72 + Math.cos(ba) * 28, 52 + Math.sin(ba) * 28)]], "out");
    FX.keys(fb.scale, [[K(7), [6, 6]], [K(11), [16, 16]], [D, [20, 20]]], "out");
    FX.keys(fb.rotation, [[0, rnd() * 360], [D, rnd() * 360]], false);
    fb.blendingMode = BlendingMode.OVERLAY; fb.opacity.setValue(50);
  }
  var gas = FX.comp(tag + "_gas", W, H, 25, D, RE.FOLDER);
  var hl = gas.layers.add(heat);
  var td = FX.fx(hl, "ADBE Turbulent Displace"); FX.set(td, "Amount", 18); FX.set(td, "Size", 3 * S); FX.set(td, "Complexity", 4);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 520]], false);
  FX.find(td, "Offset (Turbulence)").expression = "[" + (W / 2) + " - time * 160, " + (H / 2) + "]";   // gas streams to the right
  function heatMatte(cmp, name) { var m = cmp.layers.add(gas); m.name = name; var lv = FX.fx(m, "ADBE Pro Levels2");
    lv.property("ADBE Pro Levels2-0004").setValue(0.06); lv.property("ADBE Pro Levels2-0005").setValue(0.28); return m; }
  function toner(l, a, b2, cc, d, e) { var t = FX.fx(l, "CC Toner"); FX.set(t, "Tones", 3);
    FX.set(t, "Highlights", a); FX.set(t, "Brights", b2); FX.set(t, "Midtones", cc); FX.set(t, "Darktones", d); FX.set(t, "Shadows", e); return t; }

  var c = RE.comp(tag, W, H, D);
  // 1. black smoke drifting right behind the fire (Kenney sprites at the exact smoke puffs)
  var sp = [[104, 30, 13], [112, 46, 14], [114, 64, 15], [109, 82, 13], [98, 94, 11], [82, 98, 9]];
  for (var i = 0; i < sp.length; i++) {
    var bs = RE.tex(c, RE.KS + "Black smoke/blackSmoke" + (i * 3 + 3 < 10 ? "0" : "") + (i * 3 + 3) + ".png", "smoke" + i, { blend: BlendingMode.NORMAL });
    RE.tint(bs, FX.rgb("3A2C2A"), FX.rgb("0A0807"));
    FX.keys(bs.position, [[K(8), P(sp[i][0] - 8, sp[i][1])], [K(14), P(sp[i][0], sp[i][1])], [D, P(sp[i][0] + 8, sp[i][1] - 4)]], false);
    var ss = sp[i][2] * 2 * S * 1.8 / 370 * 100;
    FX.keys(bs.scale, [[K(8), [ss * 0.6, ss * 0.6]], [K(13), [ss, ss]], [D, [ss * 1.15, ss * 1.15]]], false);
    FX.keys(bs.rotation, [[0, rnd() * 360], [D, rnd() * 360]], false);
    FX.keys(bs.opacity, [[K(8), 0], [K(11), 55], [K(18), 60], [K(21), 35], [K(23), 0]], false);
  }
  // 2. heat halo + flame fringe (additive, alpha = luminance), then the gradient-mapped fire body
  var halo = c.layers.add(gas); halo.name = "halo";
  toner(halo, YEL, ORA, RED, FX.rgb("5A0C04"), [0, 0, 0]); FX.blur(halo, 8 * S); RE.lumAlpha(halo);
  halo.blendingMode = BlendingMode.ADD; FX.keys(halo.opacity, [[K(6), 0], [K(7), 90], [K(11), 70], [K(16), 30], [K(20), 0]], false);
  var fr = c.layers.add(heat); fr.name = "flame_fringe";
  var tf = FX.fx(fr, "ADBE Turbulent Displace"); FX.set(tf, "Amount", 70); FX.set(tf, "Size", 2.5 * S); FX.set(tf, "Complexity", 3);
  FX.keys(FX.find(tf, "Evolution"), [[0, 0], [D, 700]], false);
  FX.find(tf, "Offset (Turbulence)").expression = "[" + (W / 2) + " - time * 240, " + (H / 2) + "]";
  toner(fr, YEL, ORA, RED, FX.rgb("3A0802"), [0, 0, 0]); FX.blur(fr, 1 * S); RE.lumAlpha(fr);
  fr.blendingMode = BlendingMode.ADD; FX.keys(fr.opacity, [[K(6), 0], [K(7), 100], [K(12), 85], [K(17), 35], [K(21), 0]], false);
  var fire = c.layers.add(gas); fire.name = "fire_body";
  toner(fire, WH, FX.rgb("FFA030"), FX.rgb("F25A0C"), FX.rgb("A0180A"), DK);   // hotter colours shifted down: the cel yellow lobes read as orange flame
  fire.setTrackMatte(heatMatte(c, "fire_body_matte"), TrackMatteType.LUMA);

  // 3. shockwave shell: refractive translucent cyan with a bright fresnel rim
  var shl = c.layers.add(pShell); shl.name = "shell";
  var std = FX.fx(shl, "ADBE Turbulent Displace"); FX.set(std, "Amount", 8); FX.set(std, "Size", 3 * S);
  FX.keys(FX.find(std, "Evolution"), [[0, 0], [D, 600]], false);
  var sg = FX.fx(shl, "CC Glass");
  FX.set(sg, "Bump Map", shl.index); FX.set(sg, "Softness", 8); FX.set(sg, "Height", 40); FX.set(sg, "Displacement", 40);
  FX.set(sg, "Light Intensity", 100); FX.set(sg, "Light Direction", -60); FX.set(sg, "Ambient", 40); FX.set(sg, "Specular", 100); FX.set(sg, "Roughness", 0.03);
  shl.blendingMode = BlendingMode.SCREEN; shl.opacity.setValue(60);
  RE.light(c, pShell, "shell_glow", RIM, 4 * S, 45);

  // 4. the f6 flash: hot core flare + Advanced Lightning around it + the exact electric streak/sparks as glow
  var fl = RE.tex(c, RE.K + "flare_01.png", "flash_flare", { pos: P(24, 59) });
  RE.fill(fl, FX.rgb("FFB070"));
  FX.keys(fl.scale, [[K(5.5), [15, 15]], [K(6), [60, 60]], [K(7), [80, 80]], [K(8), [30, 30]]], false);
  FX.keys(fl.opacity, [[K(5.5), 0], [K(5.8), 100], [K(6.8), 90], [K(8), 0]], false);
  var fx3 = RE.tex(c, RE.KS + "Flash/flash03.png", "flash_puff", { pos: P(26, 59) });
  FX.keys(fx3.scale, [[K(5.5), [8, 8]], [K(6.2), [16, 16]], [K(7), [20, 20]]], "out");
  FX.keys(fx3.opacity, [[K(5.5), 0], [K(5.8), 100], [K(6.6), 70], [K(7.3), 0]], false);
  var tips = [[34, 33], [46, 34], [55, 39], [58, 61], [71, 70], [49, 75], [34, 82], [24, 67], [22, 54]];
  for (var k = 0; k < tips.length; k++) {
    var l = FX.solid(c, "flash_arc" + k, [0, 0, 0]);
    var lg = FX.fx(l, "ADBE Lightning 2");
    FX.set(lg, "Lightning Type", 2); FX.set(lg, "Origin", P(30, 58));
    FX.keys(FX.find(lg, "Contextual Control"), [[K(5.6), P(30 + (tips[k][0] - 30) * 0.5, 58 + (tips[k][1] - 58) * 0.5)], [K(6.4), P(tips[k][0], tips[k][1])], [K(7), P(30 + (tips[k][0] - 30) * 1.2 + 12, 58 + (tips[k][1] - 58) * 1.2)]], false);
    FX.find(lg, "Conductivity State").expression = "Math.floor(time * 25) * 6.1 + " + k * 3;
    FX.set(lg, "Core Radius", 0.9); FX.set(lg, "Core Opacity", 100); FX.set(lg, "Core Color", CORE);
    FX.set(lg, "Glow Radius", 6); FX.set(lg, "Glow Opacity", 55); FX.set(lg, "Glow Color", EBLUE);
    FX.set(lg, "Turbulence", 1.4); FX.set(lg, "Forking", 0.3); FX.set(lg, "Decay", 0.5); FX.set(lg, "Complexity", 6); FX.set(lg, "Min. Forkdistance", 25);
    FX.keys(l.opacity, [[K(5.5), 0], [K(5.8), 100], [K(6.6), 90], [K(7.2), 0]], false);
    l.blendingMode = BlendingMode.ADD;
  }
  var ecl = c.layers.add(pElec); ecl.name = "electric_glow"; ecl.blendingMode = BlendingMode.ADD; ecl.opacity.setValue(55);
  // 5. embers flying right and up off the burning outlines
  for (var e = 0; e < 20; e++) {
    var t0 = K(9 + rnd() * 9), t1 = t0 + 0.2 + rnd() * 0.3, ea = -50 + rnd() * 100;
    var p0 = P(85 + rnd() * 30, 30 + rnd() * 58);
    RE.spark(c, "ember" + e, p0, ea, (10 + rnd() * 26) * S, t0, t1, { len: (1 + rnd() * 1.5) * S, w: (0.6 + rnd() * 0.6) * S, color: rnd() < 0.35 ? YEL : ORA, grav: -(3 + rnd() * 8) * S });
  }
  var gb = FX.adj(c, "bloom"); var g = FX.glow(gb, 5 * S, 0.3, 85, YEL, ORA);
  FX.keys(FX.find(g, "Glow Intensity"), [[K(6), 0.8], [K(8), 0.3], [K(12), 0.1]], false);
  return FX.done(c);
}
