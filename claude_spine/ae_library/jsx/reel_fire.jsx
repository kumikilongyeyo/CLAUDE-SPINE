// reel_fire (clip B, reel 4 anticipation column, t 0.0-1.4): a column of streaming fire flowing UPWARD with strong
// vertical motion blur, hot white-yellow / orange / red-pink, a hot white line on each edge with pink glow spilling
// outside, thin vertical pink-white streaks inside and thin white diagonal speed sparks. Seamless 1.0 s loop.
// Comp px = clip px. Comp covers clip x 779..1379, y 100..1420 (centre 1079, 760). Edge lines at clip x 920 / 1238.
// Seamless upward flow: noise -> vertically TILEABLE texture (copy offset by H/2, crossfaded where the seam is) ->
// Offset effect (wraps) moved by whole tiles per loop; noise evolution is cycled over the loop.
function BUILD(V) {
  var W = 600, H = 1320, D = 1.0, FPS = 30;
  var XL = 141, XR = 459, XC = (XL + XR) / 2;
  var name = "cb_reel_fire_v" + V;
  var HOT = FX.rgb("FFF4DC"), FY = FX.rgb("FFD44C"), YEL = FX.rgb("FFC83A"), ORA = FX.rgb("FF7214"), RED = FX.rgb("E85A30"), FR = FX.rgb("C81E48"), SAL = FX.rgb("FF6E8C"), PINK = FX.rgb("FF3FA8"),
      MAG = FX.rgb("FF2A9A");

  function tileTex(nm, build) {
    var src = FX.comp(nm + "_n", W, H, FPS, D, "fxlib_density");
    FX.solid(src, "black", [0, 0, 0]);
    build(src);
    var t = FX.comp(nm, W, H, FPS, D, "fxlib_density");
    // B: offset by H/2 (continuous across the wrap, seam in the middle) under A (seam-free middle, fades out at the
    // top/bottom). Masks run BEFORE effects, so the mask goes on A (no effects), never on the offset copy.
    var b = t.layers.add(src); b.name = "B_offset";
    var of = FX.fx(b, "ADBE Offset"); of.property("ADBE Offset-0001").setValue([W / 2, H]);
    var a = t.layers.add(src); a.name = "A_middle";
    var m = a.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var s = new Shape(); s.vertices = [[-W, H * 0.22], [2 * W, H * 0.22], [2 * W, H * 0.78], [-W, H * 0.78]]; s.closed = true;
    m.property("ADBE Mask Shape").setValue(s);
    m.property("ADBE Mask Feather").setValue([0, H * 0.36]);
    return t;
  }
  function flow(comp, tex, nm, tiles) {
    var l = comp.layers.add(tex); l.name = nm;
    var of = FX.fx(l, "ADBE Offset");
    of.property("ADBE Offset-0001").expression =
      "var y = (" + (H / 2) + " - time / " + D + " * " + (tiles * H) + ") % " + H + "; if (y < 0) y += " + H + "; [" + (W / 2) + ", y]";
    return l;
  }

  // 1. fire density: big rising tongues (tall noise) + finer streak noise screened on, shaped by a column profile
  var fireTex = tileTex("cb_rf_fire_v" + V, function (c) {
    FX.noise(c, "body", { type: 1, noise: 3, contrast: 190, brightness: -5, sw: 110, sh: 800, complexity: 4, seed: 7,
      evo: [[0, 0], [D, 360]], cycle: 1 });
    FX.noise(c, "licks", { type: 1, noise: 3, contrast: 170, brightness: -20, sw: 34, sh: 380, complexity: 3, seed: 31,
      evo: [[0, 0], [D, 720]], cycle: 2, blend: BlendingMode.SCREEN, opacity: 70 });
  });
  var streakTex = tileTex("cb_rf_streak_v" + V, function (c) {
    FX.noise(c, "streaks", { type: 1, noise: 2, contrast: 260, brightness: -70, sw: 2.5, sh: 3000, complexity: 2, seed: 5,
      evo: [[0, 0], [D, 360]], cycle: 1 });
  });

  var c = FX.comp(name, W, H, FPS, D);

  // 2. outer red/pink glow spilling outside the edge lines (behind everything)
  function vline(nm, x, w, col, blur, op) {
    var l = FX.shape(c, nm);
    FX.group(l, "path", { points: [[x, -40], [x, H + 40]], stroke: col, width: w, cap: 1 });
    l.position.setValue([0, 0]); l.anchorPoint.setValue([0, 0]);
    if (blur) FX.blur(l, blur);
    if (op !== undefined) l.opacity.setValue(op);
    return l;
  }
  var outer = [vline("spillL", XL, 80, RED, 30, 50), vline("spillR", XR, 80, RED, 30, 50)];

  // 3. fire body: colour from a soft levels + tritone, alpha from a HARD luma matte (mostly opaque, holes where dark)
  function fireLayer(nm, lo, hi) {
    var l = flow(c, fireTex, nm, 2);
    var d = FX.fx(l, "ADBE Motion Blur"); FX.set(d, "Direction", 0); FX.set(d, "Blur Length", 110);
    var lv = FX.fx(l, "ADBE Pro Levels2");
    lv.property("ADBE Pro Levels2-0004").setValue(lo); lv.property("ADBE Pro Levels2-0005").setValue(hi);
    return l;
  }
  var fire = fireLayer("fire", 0.1, 1.0);
  var tt = FX.fx(fire, "ADBE Tritone"); FX.set(tt, "Highlights", FY); FX.set(tt, "Midtones", ORA); FX.set(tt, "Shadows", FR);
  var fmat = fireLayer("fire_alpha", 0.12, 0.55);
  fire.moveBefore(fmat); fmat.moveBefore(fire);
  fire.setTrackMatte(fmat, TrackMatteType.LUMA);
  // keep it inside the lines (soft)
  var fm = fire.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var fs = new Shape(); fs.vertices = [[XL - 4, -50], [XR + 4, -50], [XR + 4, H + 50], [XL - 4, H + 50]]; fs.closed = true;
  fm.property("ADBE Mask Shape").setValue(fs); fm.property("ADBE Mask Feather").setValue([10, 0]);
  // breathing: bright 0.1-0.45, dim 0.6-1.0 (measured mean column colour)
  FX.keys(fire.opacity, [[0, 75], [0.17, 100], [0.42, 92], [0.58, 35], [0.7, 18], [0.88, 18], [1.0, 75]], "both");

  // column matte (track mattes run AFTER effects; a mask would be undone by Shift Channels)
  var colm = FX.solid(c, "column_matte", [1, 1, 1]);
  var cm = colm.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var cms = new Shape(); cms.vertices = [[XL + 2, -50], [XR - 2, -50], [XR - 2, H + 50], [XL + 2, H + 50]]; cms.closed = true;
  cm.property("ADBE Mask Shape").setValue(cms); cm.property("ADBE Mask Feather").setValue([16, 0]);
  colm.enabled = false;

  // 3b. white-hot cores: the brightest part of the same flow, added
  var hotL = fireLayer("hot", 0.62, 0.95);
  var hsc = FX.fx(hotL, "ADBE Shift Channels"); FX.set(hsc, "Take Alpha From", 5);
  var hfl = FX.fx(hotL, "ADBE Fill"); FX.set(hfl, "Color", FX.rgb("FFF6C8"));
  hotL.blendingMode = BlendingMode.ADD;
  hotL.setTrackMatte(colm, TrackMatteType.ALPHA);
  hotL.opacity.expression = "thisComp.layer(\"fire\").transform.opacity * 0.4";

  // 3b2. slower pink-red zones breaking up the flame pattern (same texture, half the speed -> decorrelated)
  var pz = flow(c, fireTex, "pink_zones", 1);
  var pzb = FX.fx(pz, "ADBE Motion Blur"); FX.set(pzb, "Direction", 0); FX.set(pzb, "Blur Length", 90);
  var pzl = FX.fx(pz, "ADBE Pro Levels2");
  pzl.property("ADBE Pro Levels2-0004").setValue(0.42); pzl.property("ADBE Pro Levels2-0005").setValue(0.75);
  var pzs = FX.fx(pz, "ADBE Shift Channels"); FX.set(pzs, "Take Alpha From", 5);
  var pzf = FX.fx(pz, "ADBE Fill"); FX.set(pzf, "Color", FX.rgb("D8306A"));
  pz.setTrackMatte(colm, TrackMatteType.ALPHA);
  pz.opacity.expression = "thisComp.layer(\"fire\").transform.opacity * 0.7";

  // 3c. dim phase: the column goes dark red-magenta between the fire surges
  var tint = FX.solid(c, "dim_tint", FX.rgb("A83860"));
  var tm = tint.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  tm.property("ADBE Mask Shape").setValue(fs); tm.property("ADBE Mask Feather").setValue([16, 0]);
  tint.opacity.expression = "Math.max(0, 70 - thisComp.layer(\"fire\").transform.opacity) * 0.45";

  // 4. inner yellow bands hugging the edge lines
  var inner = [vline("innerL", XL + 26, 44, FX.rgb("FFD838"), 16, 90), vline("innerR", XR - 26, 44, FX.rgb("FFD838"), 16, 90)];
  for (var i = 0; i < 2; i++) { inner[i].blendingMode = BlendingMode.SCREEN; inner[i].opacity.expression = "Math.max(0, (thisComp.layer(\"fire\").transform.opacity - 30) * 1.4)"; }

  // 5. thin vertical pink-white streaks inside (additive)
  var st = flow(c, streakTex, "streaks", 3);
  var lv2 = FX.fx(st, "ADBE Pro Levels2");
  lv2.property("ADBE Pro Levels2-0004").setValue(0.35); lv2.property("ADBE Pro Levels2-0005").setValue(0.7);
  var sc2 = FX.fx(st, "ADBE Shift Channels"); FX.set(sc2, "Take Alpha From", 5);
  var fl2 = FX.fx(st, "ADBE Fill"); FX.set(fl2, "Color", FX.rgb("FF9AD8"));
  st.blendingMode = BlendingMode.ADD;
  st.setTrackMatte(colm, TrackMatteType.ALPHA);
  st.opacity.setValue(100);

  // 6. edge lines: pink halo + white-hot core, gentle periodic flicker (whole cycles per loop)
  var halo = [vline("haloL", XL, 26, SAL, 9, 70), vline("haloR", XR, 26, SAL, 9, 70)];
  var core = [vline("coreL", XL, 9, HOT, 2), vline("coreR", XR, 9, HOT, 2)];
  for (var j = 0; j < 2; j++) {
    halo[j].blendingMode = BlendingMode.ADD;
    halo[j].opacity.expression = "0.8 * (88 + 12 * Math.sin(2 * Math.PI * (" + (5 + j) + " * time / " + D + ") + " + j + "))";
    core[j].opacity.expression = "92 + 8 * Math.sin(2 * Math.PI * (" + (7 + j) + " * time / " + D + ") + " + (2 * j) + ")";
  }

  // 7. thin white diagonal speed sparks shooting up and out from the column (periodic births, wrap copies)
  var rnd = FX.rng(23), N = 36;
  for (var k = 0; k < N; k++) {
    var side = k % 2 ? 1 : -1;
    var x0 = (side < 0 ? XL : XR) + side * (rnd() * 50 - 35);
    var y0 = 120 + rnd() * (H - 240);
    var ang = -90 + side * (25 + rnd() * 30);           // up and outward
    var len = 110 + rnd() * 120, life = 0.12 + rnd() * 0.1, dist = 90 + rnd() * 120;
    var tb = (k + rnd() * 0.6) * D / N;
    for (var w = 0; w < 2; w++) {
      var t0 = tb - w * D;
      if (t0 + life < 0) continue;
      FX.streak(c, "spark" + k + "_" + w, x0, y0, ang, 0, dist, t0, t0 + life, len, 3 + rnd() * 1.5, HOT);
    }
  }
  var g1 = FX.adj(c, "glow_sparks"); FX.glow(g1, 8, 0.6, 70, PINK, RED);
  for (var o = 0; o < 2; o++) outer[o].moveToEnd();
  return FX.done(c);
}
