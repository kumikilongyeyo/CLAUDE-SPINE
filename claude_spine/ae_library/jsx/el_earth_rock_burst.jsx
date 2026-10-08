// el_earth_rock_burst: rocks and dirt erupting out of the ground, 512x512, 1.2 s one-shot. Ground contact (256, 402).
// Physics: the ground heaves (crater scar), then debris is thrown on parabolas with drag: big rocks slow and low,
// small ones fast and high, all spinning (spin also braked by drag), falling back under gravity 1600 px/s^2;
// dirt clumps spread as they fly; dust is pushed out low along the ground (a skirt) and billows up slowly,
// lingering after everything else has landed.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, D = 1.2, F = 0.04, GX = 256, GY = 402, G = 1600, TB = F * 2;
  EL.purge("el_earth_rock_burst_v");
  var tag = "el_earth_rock_burst_v" + V, rnd = FX.rng(9090 + V);
  var DUST = FX.rgb("9C8670"), DUSTD = FX.rgb("3E3228"), EARTH = FX.rgb("5A4231");

  // ---------- rock material: terracotta photo turned into weathered stone + grain
  var mat = EL.comp(tag + "_rockmat", 512, 512, D);
  var ph = EL.tex(mat, EL.R + "clay_02.jpg", "stone_photo", { pos: [256, 256] }); ph.scale.setValue([80, 80]); ph.rotation.setValue(37);
  EL.hueSat(ph, 0, -28, true, 28, 18);
  var ph2 = EL.tex(mat, EL.R + "clay_01.jpg", "rock_photo", { pos: [256, 256], blend: BlendingMode.OVERLAY }); ph2.scale.setValue([45, 45]);
  EL.hueSat(ph2, -80, 0); ph2.opacity.setValue(70);
  var gr = FX.noise(mat, "grain", { type: 2, noise: 3, contrast: 180, brightness: 0, scale: 9, complexity: 6, seed: 5 });
  gr.layer.blendingMode = BlendingMode.MULTIPLY; gr.layer.opacity.setValue(55);
  var gr2 = FX.noise(mat, "mottle", { type: 1, noise: 3, contrast: 140, brightness: 10, scale: 60, complexity: 3, seed: 8 });
  gr2.layer.blendingMode = BlendingMode.OVERLAY; gr2.layer.opacity.setValue(60);
  var dk = FX.adj(mat, "stone_grade"); EL.levels(dk, 0.02, 0.85, 1.0);

  var c = EL.comp(tag, W, H, D);

  // 1. back dust: billowing column of dust (photo + Kenney), tan, slow
  var dustB = ["smoke_07", "smoke_04", "smoke_08", "smoke_06", "smoke_05"];
  for (var b = 0; b < dustB.length; b++) {
    var tb = TB + F * (b * 0.8), ab = -Math.PI / 2 + (b - 2) * 0.5;
    var dl = EL.tex(c, EL.K + dustB[b] + ".png", "dust_back" + b);
    RE.tint(dl, DUST, DUSTD); FX.blur(dl, 4);
    EL.ball(dl, [GX + Math.cos(ab) * 20, GY - 20], [Math.cos(ab) * 160, Math.sin(ab) * 260], -40, 2.6, tb);
    var sc = 40 + rnd() * 16;
    FX.keys(dl.scale, [[tb, [sc * 0.3, sc * 0.3]], [D, [sc * 1.4, sc * 1.3]]], "out");
    EL.spin(dl, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * 40, 1.2, tb);
    FX.keys(dl.opacity, [[tb - 0.001, 0], [tb + 0.1, 48], [D - 0.3, 38], [D, 0]], false);
  }
  var pd = EL.tex(c, EL.R + "smoke_04.png", "dust_photo", { anchor: [380, 360], mask: 200, inset: 120 });
  RE.tint(pd, FX.rgb("C2A47E"), FX.rgb("3A2C20"));
  pd.position.expression = "var t = Math.max(0, time - " + (TB + 0.1) + "); [" + GX + ", " + (GY - 70) + " - 50 * t]";
  FX.keys(pd.scale, [[TB, [18, 14]], [D, [44, 34]]], "out");
  FX.keys(pd.opacity, [[TB, 0], [TB + 0.25, 50], [D - 0.2, 38], [D, 0]], false);

  // 2. crater scar + heave
  var sc1 = EL.tex(c, EL.K + "scorch_03.png", "crater", { pos: [GX, GY + 4] });
  RE.fill(sc1, FX.rgb("2A1E16")); sc1.scale.setValue([62, 16]);
  FX.keys(sc1.opacity, [[0, 0], [TB, 90], [D, 85]], false);
  var heave = EL.layerOf(c, mat, "heave"); EL.mask(heave, [[GX - 70, GY + 4], [GX - 40, GY - 18], [GX + 5, GY - 26], [GX + 46, GY - 16], [GX + 72, GY + 4], [GX, GY + 14]], 3);
  heave.anchorPoint.setValue([GX, GY]); heave.position.setValue([GX, GY]);
  FX.keys(heave.scale, [[0, [60, 0]], [TB, [100, 110]], [TB + F, [100, 60]]], "out");
  FX.keys(heave.opacity, [[0, 100], [TB + F, 100], [TB + F * 2, 0]], false);
  EL.bevel(heave, 3, -50, 0.6);

  // 3. rocks (stone material cut by jagged masks), bevelled, spinning on parabolas
  for (var k = 0; k < 15; k++) {
    var big = k < 6, rx = big ? 26 + rnd() * 12 : 11 + rnd() * 8, ry = rx * (0.6 + rnd() * 0.35);
    var mx = 80 + rnd() * 350, my = 80 + rnd() * 350;            // where in the material this rock is cut
    var pts = EL.jag(7, rx, ry, 0.35, rnd);
    for (var j = 0; j < pts.length; j++) { pts[j][0] += mx; pts[j][1] += my; }
    var r = EL.layerOf(c, mat, "rock" + k);
    EL.mask(r, pts, 0.6);
    r.anchorPoint.setValue([mx, my]);
    var ang = (-90 + (rnd() - 0.5) * (big ? 90 : 130)) * Math.PI / 180, spd = big ? 560 + rnd() * 220 : 760 + rnd() * 360;
    var tk = TB + rnd() * F * 2;
    EL.ball(r, [GX + Math.cos(ang) * 25, GY - 8], [Math.cos(ang) * spd, Math.sin(ang) * spd], G, big ? 0.5 : 0.9, tk);
    EL.spin(r, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * (big ? 160 + rnd() * 200 : 400 + rnd() * 500), 0.8, tk);
    r.motionBlur = true;
    var s0 = big ? 100 : 100;
    FX.keys(r.scale, [[tk - F, [20, 20]], [tk + F, [s0, s0]]], "out");
    FX.keys(r.opacity, [[tk - 0.001, 0], [tk, 100], [D - 0.1, 100], [D, 0]], false);
    EL.bevel(r, big ? 5 : 3, -55, 0.45);
    var sh = FX.fx(r, "ADBE Drop Shadow");
    FX.set(sh, "Opacity", 60); FX.set(sh, "Distance", big ? 4 : 2); FX.set(sh, "Softness", 4); FX.set(sh, "Direction", 150);
  }
  // 4. dirt clumps (Kenney dirt clusters) spreading as they fly
  var dirt = ["dirt_01", "dirt_02", "dirt_03", "dirt_01", "dirt_02", "dirt_03"];
  for (var q = 0; q < dirt.length; q++) {
    var aq = (-90 + (q - 2.5) * 22 + (rnd() - 0.5) * 10) * Math.PI / 180, sq = 380 + rnd() * 260, tq = TB + F * rnd();
    var dq = EL.tex(c, EL.K + dirt[q] + ".png", "dirt" + q);
    RE.tint(dq, FX.rgb("7A5A40"), FX.rgb("1E140C"));
    EL.ball(dq, [GX, GY - 10], [Math.cos(aq) * sq, Math.sin(aq) * sq], G, 1.0, tq);
    FX.keys(dq.scale, [[tq, [6, 6]], [tq + 0.35, [26 + rnd() * 8, 26 + rnd() * 8]], [D, [34, 34]]], "out");
    EL.spin(dq, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * 90, 1, tq);
    dq.motionBlur = false;     // a fast, wide cluster texture under motion blur samples into visible stripes
    FX.keys(dq.opacity, [[tq - 0.001, 0], [tq, 100], [tq + 0.55, 90], [D - 0.15, 0]], false);
  }
  // 5. pebbles
  for (var e = 0; e < 46; e++) {
    var ae = (-90 + (rnd() - 0.5) * 160) * Math.PI / 180, se = 450 + rnd() * 650, sz = 2 + rnd() * 3.5;
    var pe = EL.poly(c, "pebble" + e, EL.jag(5, sz, sz * 0.8, 0.3, rnd), rnd() < 0.5 ? EARTH : FX.rgb("3A2E26"));
    var te = TB + rnd() * F * 2;
    EL.ball(pe, [GX + (rnd() - 0.5) * 50, GY - 6], [Math.cos(ae) * se, Math.sin(ae) * se], G, 1.0, te);
    EL.spin(pe, 0, 600, 1, te);
    pe.motionBlur = true;
    FX.keys(pe.opacity, [[te - 0.001, 0], [te, 100], [D - 0.1, 100], [D, 0]], false);
  }
  // 6. front dust skirt: pushed out low along the ground, then curling up
  var skirt = ["smoke_07", "smoke_08", "smoke_04", "smoke_07", "smoke_06", "smoke_08"];
  for (var f = 0; f < skirt.length; f++) {
    var side = f % 2 ? 1 : -1, tf = TB + F * (0.5 + f * 0.4), sp = 260 + rnd() * 200;
    var sk = EL.tex(c, EL.K + skirt[f] + ".png", "dust_skirt" + f); FX.blur(sk, 3);
    RE.tint(sk, FX.rgb("B49A7A"), FX.rgb("4E3E30"));
    EL.ball(sk, [GX + side * 20, GY + 2], [side * sp, -50 - rnd() * 60], -30, 3.0, tf);
    var ss = 26 + rnd() * 10;
    FX.keys(sk.scale, [[tf, [ss * 0.4, ss * 0.3]], [D, [ss * 1.6, ss * 1.2]]], "out");
    EL.spin(sk, rnd() * 360, side * 50, 1.2, tf);
    FX.keys(sk.opacity, [[tf - 0.001, 0], [tf + 0.08, 70], [D - 0.3, 50], [D, 0]], false);
  }
  return EL.done(c, "normal", [GX, GY], false);
}
