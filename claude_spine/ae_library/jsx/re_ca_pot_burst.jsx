// re_ca_pot_burst: realistic version of ca_pot_burst_v9 (same 540x496 @30 fps, 0.5 s, same timing/placement:
// clip A t0 1.64, comp centre on clip (320, 532), 1.5x clip px). A ceramic pot bursting: white-hot flash, a billowing
// photo dust cloud (Kenney White puff sequence) lit white-hot -> warm, ceramic dust (Kenney smoke) and photo smoke
// drifting out, terracotta shards (clay_02 texture, bevelled) on parabolas with motion blur, ice-blue shard light
// (driven by the exact comp's spikes) and sparkles. Normal blend (alpha), light parts added inside.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "ca_pot_burst_v9", S = 1.5, W = 540, H = 496, cx = W / 2, cy = H / 2, D = 0.5, FPS = 30;
  RE.purge("re_ca_pot_burst_v");
  var tag = "re_ca_pot_burst_v" + V;
  var rnd = FX.rng(101);
  function P(x, y) { return [cx + x * S, cy + y * S]; }
  var WHITE = FX.rgb("FFFDF4"), WARM = FX.rgb("FFE9B0"), GOLD = FX.rgb("FFC870"), ICE = FX.rgb("C8DCFF"),
      DUST = FX.rgb("F2E6D2"), DUST2 = FX.rgb("DCC4A4");
  function pre(nm, keep) {
    var p = RE.only(SRC, tag + "_" + nm, keep);
    for (var i = 1; i <= p.numLayers; i++) p.layer(i).motionBlur = true;
    p.motionBlur = true; p.shutterAngle = 270; p.shutterPhase = -135; return p;
  }
  var pCore = pre("core", function (n) { return n === "core" || n === "crack_flash"; });
  var pShard = pre("shardlight", function (n) { return n.indexOf("shard") === 0; });
  var pSpark = pre("sparks", function (n) { return n.indexOf("spark") === 0; });
  var pBody = pre("body", function (n) { return n === "body" || n === "rim"; });

  var c = FX.comp(tag, W, H, FPS, D, RE.FOLDER);
  c.motionBlur = true; c.shutterAngle = 270; c.shutterPhase = -135;
  try { c.motionBlurSamplesPerFrame = 24; c.motionBlurAdaptiveSampleLimit = 128; } catch (x) {}

  // the Kenney White puff flipbook (25 frames) as one sequence footage
  function puffSeq() {
    var f0 = new File(RE.KS + "White puff/whitePuff00.png");
    for (var i = 1; i <= app.project.numItems; i++) {
      var q = app.project.item(i);
      if (q instanceof FootageItem && q.mainSource instanceof FileSource && !q.mainSource.isStill && q.mainSource.file && q.mainSource.file.fsName === f0.fsName) return q;
    }
    var io = new ImportOptions(f0); io.sequence = true; io.forceAlphabetical = true;
    var it = app.project.importFile(io); it.mainSource.conformFrameRate = 30; it.parentFolder = FX.folder("fxlib_textures");
    return it;
  }
  var PUFF = puffSeq();

  // 1. photo smoke behind (bluish photo smoke lit warm white), slow expansion, lingers into the tail
  for (var s = 0; s < 2; s++) {
    var ps = RE.tex(c, RE.R + "smoke_04.png", "photo_smoke" + s, { blend: BlendingMode.NORMAL });
    RE.circMask(ps, 360 + s * 260, 420, 250, 200);
    ps.anchorPoint.setValue([360 + s * 260, 420]);
    RE.tint(ps, FX.rgb("F8F0E4"), FX.rgb("8C7A6C"));
    ps.position.setValue(P(s ? 30 : -30, 6));
    ps.rotation.setValue(s * 150 + 20);
    FX.keys(ps.scale, [[0.03, [20, 20]], [0.12, [42, 42]], [D, [56, 56]]], "out");
    FX.keys(ps.opacity, [[0.03, 0], [0.1, 50], [0.28, 30], [0.45, 0]], false);
  }

  // 2. ceramic dust puffs (Kenney smoke) pushed outward, beige, normal blend
  var SM = ["smoke_04.png", "smoke_07.png", "smoke_05.png", "smoke_08.png"];
  for (var d = 0; d < 7; d++) {
    var a = d * (360 / 7) + rnd() * 30, ar = a * Math.PI / 180, r1 = 55 + rnd() * 30;
    var dl = RE.tex(c, RE.K + SM[d % 4], "dust" + d, { blend: BlendingMode.NORMAL });
    RE.tint(dl, d % 2 ? DUST : DUST2, FX.rgb("9A8068"));
    FX.keys(dl.position, [[0.04, P(Math.cos(ar) * 30, 6 + Math.sin(ar) * 26)], [D, P(Math.cos(ar) * r1, 6 + Math.sin(ar) * r1 * 0.85 - 10)]], "out");
    FX.keys(dl.scale, [[0.04, [16, 16]], [0.15, [30, 30]], [D, [42, 42]]], "out");
    FX.keys(dl.rotation, [[0, rnd() * 360], [D, rnd() * 360]], false);
    FX.keys(dl.opacity, [[0.04, 0], [0.1, 65], [0.26, 35], [0.42, 0]], false);
  }

  // 3. ice-blue shard light from the exact spikes (soft, additive)
  RE.light(c, pShard, "shard_bloom", ICE, 6 * S, 45);
  RE.light(c, pShard, "shard_light", FX.rgb("EEF4FF"), 2.5 * S, 32);

  // 4. the billowing cloud: three White puff sequences, white-hot -> warm, turbulent edges
  for (var k = 0; k < 3; k++) {
    var pl = c.layers.add(PUFF); pl.name = "puff" + k;
    pl.stretch = 46;                       // 25 frames over ~0.38 s
    pl.startTime = 0.005;
    pl.position.setValue(P([0, -14, 14][k], [6, 0, 10][k]));
    pl.rotation.setValue(k * 120 + 10);
    var sc = [[0.005, [14, 13]], [0.017, [40, 36]], [0.033, [74, 66]], [0.05, [84, 75]], [0.08, [92, 82]], [0.2, [100, 90]], [0.34, [106, 96]]];
    for (var z = 0; z < sc.length; z++) sc[z][1] = [sc[z][1][0] * (k ? 0.82 : 1), sc[z][1][1] * (k ? 0.82 : 1)];
    FX.keys(pl.scale, sc, "out");
    var tn = RE.tint(pl, WHITE, FX.rgb("8E9CB8"));
    FX.keys(FX.find(tn, "Map White To"), [[0.1, WHITE], [0.17, WARM], [0.26, GOLD]], false);
    FX.keys(FX.find(tn, "Map Black To"), [[0.1, FX.rgb("8E9CB8")], [0.2, FX.rgb("A88A6C")]], false);
    var td = FX.fx(pl, "ADBE Turbulent Displace"); FX.set(td, "Amount", 30); FX.set(td, "Size", 18 * S);
    FX.keys(FX.find(td, "Evolution"), [[0, k * 60], [D, k * 60 + 240]], false);
    FX.keys(pl.opacity, [[0.004, 0], [0.008, 100], [0.15, 100], [0.22, 70], [0.3, 25], [0.36, 0]], false);
  }

  // 5. white-hot core + flash
  var cb = RE.light(c, pCore, "core_bloom", GOLD, 10 * S, 70);
  FX.keys(cb.opacity, [[0, 70], [0.06, 70], [0.14, 40]], false);
  var ch = RE.light(c, pCore, "core_hot", WHITE, 2 * S, 100);
  FX.keys(ch.opacity, [[0, 100], [0.04, 100], [0.08, 50], [0.2, 20]], false);
  var fl = RE.tex(c, RE.K + "flare_01.png", "flash", { pos: P(2, 6) });
  FX.keys(fl.scale, [[0, [60, 60]], [0.03, [130, 130]], [0.1, [90, 90]], [0.18, [40, 40]]], false);
  FX.keys(fl.opacity, [[0, 90], [0.03, 100], [0.12, 60], [0.2, 0]], false);
  var lt = RE.tex(c, RE.K + "light_01.png", "flash_light", { pos: P(2, 6) });
  RE.fill(lt, WARM);
  FX.keys(lt.scale, [[0, [30, 30]], [0.04, [70, 65]], [0.2, [85, 80]]], "out");
  FX.keys(lt.opacity, [[0, 60], [0.04, 80], [0.16, 40], [0.26, 0]], false);

  // 6. terracotta shards on parabolas (clay_02 texture cut by small polygon masks, bevelled, motion blurred)
  for (var h = 0; h < 12; h++) {
    var sh = c.layers.add(FX.imp(RE.R + "clay_02.jpg")); sh.name = "shard" + h;
    var tx = 150 + rnd() * 700, ty = 120 + rnd() * 440, sz = (11 + rnd() * 10) * S, n = 4 + Math.floor(rnd() * 2), pts = [];
    for (var v = 0; v < n; v++) { var va = v * 360 / n + rnd() * 50, vr = sz * (0.55 + rnd() * 0.5); pts.push([tx + Math.cos(va * Math.PI / 180) * vr, ty + Math.sin(va * Math.PI / 180) * vr * (0.5 + rnd() * 0.4)]); }
    var shp = new Shape(); shp.vertices = pts; shp.closed = true;
    var mk = sh.property("ADBE Mask Parade").addProperty("ADBE Mask Atom"); mk.property("ADBE Mask Shape").setValue(shp);
    sh.anchorPoint.setValue([tx, ty]);
    var bv = FX.fx(sh, "ADBE Bevel Alpha"); try { FX.set(bv, "Edge Thickness", 2.5); FX.set(bv, "Light Intensity", 0.6); } catch (x) {}
    var cv = FX.fx(sh, "ADBE Brightness & Contrast 2"); try { FX.keys(FX.find(cv, "Brightness"), [[0, 60], [0.12, 25], [0.3, 5]], false); } catch (x) {}
    var ang = -160 + rnd() * 140 + (rnd() < 0.3 ? 180 : 0), angr = ang * Math.PI / 180, spd = (260 + rnd() * 320) * S;
    var x0 = cx + Math.cos(angr) * 50 * S, y0 = cy + 6 * S + Math.sin(angr) * 42 * S, t0 = 0.03 + rnd() * 0.04;
    sh.position.expression = "var t = Math.max(0, time - " + t0.toFixed(3) + "); [" + x0.toFixed(1) + " + " + (Math.cos(angr) * spd).toFixed(1) + " * t, " +
      y0.toFixed(1) + " + " + (Math.sin(angr) * spd).toFixed(1) + " * t + 0.5 * " + (1300 * S) + " * t * t]";
    sh.rotation.expression = "value + " + ((rnd() - 0.5) * 1400).toFixed(0) + " * Math.max(0, time - " + t0.toFixed(3) + ")";
    sh.rotation.setValue(rnd() * 360);
    sh.scale.setValue([100, 100]);
    FX.keys(sh.opacity, [[t0 - 0.01, 0], [t0, 100], [D - 0.08, 100], [D, 0]], false);
    sh.motionBlur = true;
  }

  // 7. sparkles: exact spark paths as hot light + a few star twinkles
  RE.light(c, pSpark, "spark_bloom", GOLD, 3 * S, 90);
  RE.light(c, pSpark, "spark_core", WHITE, 0, 100);
  for (var w = 0; w < 6; w++) {
    var wa = rnd() * 360 * Math.PI / 180, wr = 50 + rnd() * 50, tw = 0.06 + rnd() * 0.18;
    var st = RE.tex(c, RE.K + "star_06.png", "twinkle" + w, { pos: P(Math.cos(wa) * wr, 6 + Math.sin(wa) * wr * 0.8) });
    st.rotation.setValue(rnd() * 40);
    FX.keys(st.scale, [[tw, [2, 2]], [tw + 0.04, [9 + rnd() * 6, 9 + rnd() * 6]], [tw + 0.12, [2, 2]]], false);
    FX.keys(st.opacity, [[tw, 0], [tw + 0.03, 100], [tw + 0.12, 0]], false);
  }

  // 8. bloom on the light
  var gb = FX.adj(c, "bloom"); var g = FX.glow(gb, 14 * S, 0.5, 70, FX.rgb("FFFFFF"), FX.rgb("FFD890"));
  FX.keys(FX.find(g, "Glow Intensity"), [[0, 0.8], [0.04, 0.7], [0.12, 0.3], [0.3, 0.15]], false);
  return FX.done(c);
}
