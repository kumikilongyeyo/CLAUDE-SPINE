// el_ice_shatter: frost crystallises outward into an ice block, cracks race out from the impact point, then the
// block shatters into shards that fly on parabolas (drag + gravity, spinning, motion blurred) with glints, ice
// crumbs and heavy cold mist that SINKS and spreads. 512x512, 1.2 s one-shot.
// Material: Cell Pattern crystals + fractal frost + a refraction photo (water_drop_02) inside a translucent block,
// Bevel Alpha edges; every shard is the same material precomp cut by its own mask (so the pieces fit together).
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, D = 1.2, F = 0.04, OX = 252, OY = 246, TS = F * 13, G = 1500;
  EL.purge("el_ice_shatter_v");
  var tag = "el_ice_shatter_v" + V, rnd = FX.rng(31337 + V);
  var ICE = FX.rgb("5FAFD8"), PALE = FX.rgb("E8FAFF"), DEEP = FX.rgb("1F6E9E"), CYAN = FX.rgb("7FE4FF");
  // the block outline (chunky crystal)
  var BLOCK = [[176, 118], [262, 92], [338, 128], [356, 236], [332, 352], [252, 384], [168, 350], [148, 232]];

  // ---------- ice material (full block)
  var mat = EL.comp(tag + "_mat", 512, 512, D);
  var body = EL.poly(mat, "block_body", BLOCK, ICE); body.position.setValue([0, 0]); body.opacity.setValue(58);
  var refr = EL.tex(mat, EL.R + "water_drop_02.jpg", "refraction_photo", { pos: [256, 240], blend: BlendingMode.SCREEN });
  refr.scale.setValue([42, 42]); refr.rotation.setValue(-12); refr.opacity.setValue(55);
  RE.tint(refr, PALE, DEEP); refr.preserveTransparency = true;
  var cell = FX.solid(mat, "crystals", [0, 0, 0]);
  var cp = FX.fx(cell, "ADBE Cell Pattern");
  FX.set(cp, "Cell Pattern", 7); FX.set(cp, "ADBE Cell Pattern-0003", 160); FX.set(cp, "Disperse", 1); FX.set(cp, "Size", 46); FX.set(cp, "Random Seed", 9);
  RE.tint(cell, PALE, DEEP); cell.blendingMode = BlendingMode.SCREEN; cell.opacity.setValue(45); cell.preserveTransparency = true;
  var frost = FX.noise(mat, "frost", { type: 2, noise: 3, contrast: 260, brightness: -40, scale: 18, complexity: 6, seed: 3 });
  RE.tint(frost.layer, [1, 1, 1], [0, 0, 0]); frost.layer.blendingMode = BlendingMode.SCREEN; frost.layer.opacity.setValue(25);
  frost.layer.preserveTransparency = true;
  var core = EL.blob(mat, "inner_glow", PALE, 252, 230, 60, 70, BlendingMode.SCREEN); core.opacity.setValue(22); core.preserveTransparency = true;
  var edge = EL.poly(mat, "block_edge", BLOCK, null, PALE, 3); edge.position.setValue([0, 0]); edge.opacity.setValue(80); FX.blur(edge, 1.5);

  // ---------- frost growth matte: radial front + crystal noise, hard threshold -> dendritic front
  var grow = EL.comp(tag + "_grow", 512, 512, D);
  FX.solid(grow, "black", [0, 0, 0]);
  var gr = FX.ramp(grow, "front", OX, OY + 20, 10, [1, 1, 1, 1], [0, 0, 0, 1]);
  FX.rampRadius(gr, OX, OY + 20, [[0, 8], [F * 4, 120], [F * 10, 300]]);
  var gn = FX.noise(grow, "dendrites", { type: 2, noise: 3, contrast: 240, brightness: -30, scale: 22, complexity: 6, seed: 12 });
  gn.layer.blendingMode = BlendingMode.ADD; gn.layer.opacity.setValue(80);
  var gc = FX.solid(grow, "crystal_cells", [0, 0, 0]);       // faceted, crystalline growth front
  var gcp = FX.fx(gc, "ADBE Cell Pattern"); FX.set(gcp, "Cell Pattern", 7); FX.set(gcp, "ADBE Cell Pattern-0003", 120); FX.set(gcp, "Size", 30); FX.set(gcp, "Random Seed", 4);
  gc.blendingMode = BlendingMode.ADD; gc.opacity.setValue(26);
  var gl = FX.adj(grow, "threshold"); EL.levels(gl, 0.55, 0.62, 1);

  // ================= main
  var c = EL.comp(tag, W, H, D);

  // 1. cold mist: heavy, sinks and spreads (behind the shards)
  var puffs = ["whitePuff00", "whitePuff06", "whitePuff12", "whitePuff18", "whitePuff24", "whitePuff09", "whitePuff15"];
  for (var m = 0; m < puffs.length; m++) {
    var tm = TS + F * (m * 0.6), am = (m / puffs.length) * Math.PI * 2 + rnd() * 0.5;
    var mp = EL.tex(c, EL.KS + "White puff/" + puffs[m] + ".png", "cold_mist" + m);
    RE.tint(mp, [1, 1, 1], FX.rgb("A8D8F0")); FX.blur(mp, 8);
    EL.ball(mp, [OX + Math.cos(am) * 40, OY + 40 + Math.sin(am) * 50], [Math.cos(am) * 260, Math.sin(am) * 80 + 40], 120, 2.6, tm);
    var ms = 30 + rnd() * 12;
    FX.keys(mp.scale, [[tm, [ms * 0.4, ms * 0.35]], [D, [ms * 1.7, ms * 1.0]]], "out");
    EL.spin(mp, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * 30, 1, tm);
    FX.keys(mp.opacity, [[tm - 0.001, 0], [tm + 0.1, 26], [D - 0.3, 14], [D, 0]], false);
  }
  // frost breath before the break (mist creeping off the cold block)
  var cm = EL.tex(c, EL.K + "smoke_08.png", "frost_breath", { pos: [OX, OY + 120] });
  RE.tint(cm, PALE); cm.scale.setValue([70, 30]);
  FX.keys(cm.opacity, [[F * 3, 0], [F * 9, 30], [TS, 35], [TS + 0.3, 0]], false);
  FX.keys(cm.scale, [[F * 3, [50, 22]], [TS + 0.3, [95, 38]]], false);

  // 2. the unbroken block: grows behind a frost front, then cracks
  var blk = EL.layerOf(c, mat, "ice_block");
  var gm = EL.layerOf(c, grow, "grow_matte"); gm.moveBefore(blk);
  blk.setTrackMatte(gm, TrackMatteType.LUMA);
  EL.bevel(blk, 3, -50, 0.65);
  blk.outPoint = TS; gm.outPoint = TS;
  // bright rim on the frost front while it grows
  var rim = EL.layerOf(c, grow, "frost_front"); rim.blendingMode = BlendingMode.ADD;
  var fe = FX.fx(rim, "ADBE Find Edges"); FX.set(fe, "Invert", 1);
  EL.lumaAlpha(rim); RE.tint(rim, PALE); FX.blur(rim, 1);
  var rimm = EL.layerOf(c, mat, "front_inside_block"); rimm.moveBefore(rim);
  rim.setTrackMatte(rimm, TrackMatteType.ALPHA);
  FX.keys(rim.opacity, [[0, 100], [F * 9, 100], [F * 11, 0]], false);
  rim.outPoint = TS; rimm.outPoint = TS;

  // 3. shard geometry: rays from the impact point, three rings, jagged
  var N = 9, rays = [];
  for (var i = 0; i < N; i++) {
    var a = (i + 0.5 * (rnd() - 0.5)) / N * Math.PI * 2;
    var r1 = 36 + rnd() * 20, r2 = 92 + rnd() * 24, r3 = 270;
    var pa = a + (rnd() - 0.5) * 0.18, pb = a + (rnd() - 0.5) * 0.25;
    rays.push([[OX, OY], [OX + Math.cos(a) * r1, OY + Math.sin(a) * r1], [OX + Math.cos(pa) * r2, OY + Math.sin(pa) * r2], [OX + Math.cos(pb) * r3, OY + Math.sin(pb) * r3]]);
  }
  function ringPt(i, k) { return rays[i % N][k]; }
  var shards = [];
  for (var s = 0; s < N; s++) {
    shards.push([ringPt(s, 0), ringPt(s, 1), ringPt(s + 1, 1)]);
    shards.push([ringPt(s, 1), ringPt(s, 2), ringPt(s + 1, 2), ringPt(s + 1, 1)]);
    shards.push([ringPt(s, 2), ringPt(s, 3), ringPt(s + 1, 3), ringPt(s + 1, 2)]);
  }
  // 4. cracks: run out along the ray lines and the rings just before the break
  var cr = FX.shape(c, "cracks"); cr.position.setValue([0, 0]);
  for (var q = 0; q < N; q++) {
    var rr = rays[q];
    var g1 = FX.group(cr, "path", { points: [rr[0], rr[1], rr[2], [(rr[2][0] + rr[3][0]) / 2, (rr[2][1] + rr[3][1]) / 2]], stroke: [1, 1, 1], width: 2, trim: true });
  }
  for (var q2 = 1; q2 <= N; q2++) {
    var cc = cr.property("ADBE Root Vectors Group").property(q2).property("ADBE Vectors Group");
    var tri = cc.property("ADBE Vector Filter - Trim");
    var td = F * (8.5 + rnd() * 2);
    FX.keys(tri.property("ADBE Vector Trim End"), [[td, 0], [td + F * 3, 100]], "out");
  }
  var crm = EL.layerOf(c, mat, "cracks_inside_block"); crm.moveBefore(cr);
  cr.setTrackMatte(crm, TrackMatteType.ALPHA);
  FX.glow(cr, 8, 1.2, 40, PALE, CYAN);
  cr.outPoint = TS + F; crm.outPoint = TS + F;

  // 5. shards
  for (var k = 0; k < shards.length; k++) {
    var pts = shards[k], cxs = 0, cys = 0, n = 0;
    for (var j = 0; j < pts.length; j++) {           // centroid of the visible part (clamp far points to the block)
      var dx = pts[j][0] - OX, dy = pts[j][1] - OY, dd = Math.sqrt(dx * dx + dy * dy), cl = Math.min(dd, 120);
      cxs += OX + (dd > 0 ? dx / dd * cl : 0); cys += OY + (dd > 0 ? dy / dd * cl : 0); n++;
    }
    cxs /= n; cys /= n;
    var sh = EL.layerOf(c, mat, "shard" + k);
    EL.mask(sh, pts, 0.5);
    sh.anchorPoint.setValue([cxs, cys]);
    var vx = cxs - OX, vy = cys - OY, vl = Math.max(1, Math.sqrt(vx * vx + vy * vy));
    var spd = (k % 3 === 0 ? 220 : 320) + rnd() * 420;
    EL.ball(sh, [cxs, cys], [vx / vl * spd, vy / vl * spd * 0.8 - 260 - rnd() * 160], G, 1.1, TS);
    EL.spin(sh, 0, (rnd() < 0.5 ? -1 : 1) * (180 + rnd() * 520), 1.2, TS);
    sh.inPoint = TS;
    sh.motionBlur = true;
    EL.bevel(sh, 2.5, -50, 0.7);
    FX.keys(sh.opacity, [[TS, 100], [D - 0.25, 100], [D, 0]], false);
    if (k % 4 === 1) {                               // a glint that rides this shard
      var gt = EL.tex(c, EL.K + "star_06.png", "glint" + k, { blend: BlendingMode.ADD });
      RE.fill(gt, PALE);
      gt.parent = sh; gt.position.setValue([cxs + (rnd() - 0.5) * 20, cys + (rnd() - 0.5) * 20]);
      var tg = TS + F * (2 + rnd() * 8);
      FX.keys(gt.scale, [[tg - F * 2, [0, 0]], [tg, [16, 16]], [tg + F * 3, [0, 0]]], false);
      FX.keys(gt.rotation, [[tg - F * 2, 0], [tg + F * 3, 60]], false);
      gt.inPoint = TS;
    }
  }
  // 6. ice crumbs (tiny bright chips) and glitter
  for (var e = 0; e < 40; e++) {
    var ae = rnd() * Math.PI * 2, sp = 300 + rnd() * 600, sz = 2 + rnd() * 3;
    var d = EL.dot(c, "crumb" + e, sz, sz * (0.6 + rnd() * 0.6), rnd() < 0.5 ? PALE : ICE);
    d.layer.motionBlur = true;
    EL.ball(d.layer, [OX + Math.cos(ae) * 30, OY + Math.sin(ae) * 30], [Math.cos(ae) * sp, Math.sin(ae) * sp * 0.8 - 200], G, 1.4, TS);
    d.layer.inPoint = TS;
    var lf = 0.35 + rnd() * 0.35;
    FX.keys(d.layer.opacity, [[TS, 100], [Math.min(D, TS + lf) - 0.05, 100], [Math.min(D, TS + lf), 0]], false);
  }
  var bk = EL.tex(c, EL.R + "bokeh_01.png", "glitter", { pos: [OX, OY], blend: BlendingMode.ADD, mask: 140, inset: 110 });
  EL.hueSat(bk, 0, 10, true, 195, 45);
  FX.keys(bk.scale, [[TS, [12, 12]], [TS + 0.35, [34, 34]]], "out");
  FX.keys(bk.opacity, [[TS - 0.001, 0], [TS + F, 55], [TS + 0.35, 0]], false);
  // 7. the break: a cold flash
  var fl = EL.tex(c, EL.K + "flare_01.png", "break_flash", { pos: [OX, OY], blend: BlendingMode.ADD });
  RE.fill(fl, PALE);
  FX.keys(fl.scale, [[TS - F, [30, 30]], [TS + F, [110, 70]], [TS + F * 4, [50, 30]]], "out");
  FX.keys(fl.opacity, [[TS - F, 0], [TS, 100], [TS + F * 5, 0]], false);
  var lb = EL.blob(c, "break_light", CYAN, OX, OY, 50, 60);
  FX.keys(lb.opacity, [[TS - F, 0], [TS, 45], [TS + F * 4, 0]], false);
  var bl = FX.adj(c, "cold_bloom"); FX.glow(bl, 14, 0.5, 72, PALE, CYAN);
  return EL.done(c, "normal", [OX, OY], false);
}
