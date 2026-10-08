// sunburst_loop (clip B, free-spins intro, held from 4.62 under the centre "5"): a warm yellow-white sunburst - soft
// god-ray spokes from a bright centre at clip px (780, 540), turning slowly, a hot core glow, a wide warm wash over
// the frame and glittering bokeh sparkles drifting out. ADDITIVE (rendered over black). Full frame 1556x1740 (comp px
// = clip px). Seamless 3.0 s loop: every ray / sparkle has a periodic life (age = time/D + phase, wrapped), so the
// "rotation" is each spoke drifting 15 deg clockwise over its life while fading in and out (sin^2).
// Ray texture: vertical bars in a 2160x2160 strip (x = angle, 2160 px = 360 deg) -> horizontal blur -> Polar
// Coordinates (Rect to Polar) -> radial falloff.
function BUILD(V) {
  var W = 1556, H = 1740, D = 3.0, FPS = 30, CX = 780, CY = 540, S = 2160;
  var name = "cb_sunburst_loop_v" + V;
  var CORE = FX.rgb("FFE880"), YEL = FX.rgb("FFD848"), WARM = FX.rgb("FFB040"), ORA = FX.rgb("FF9A2A");
  var rnd = FX.rng(101);

  // 1. strip of drifting bars (one shape layer per bar, + a twin one strip-width left for the wrap)
  var strip = FX.comp("cb_sb_strip_v" + V, S, S, FPS, D, "fxlib_density");
  FX.solid(strip, "black", [0, 0, 0]);
  var N = 46, SHIFT = S * 15 / 360;
  for (var i = 0; i < N; i++) {
    var x0 = (i + rnd() * 0.8) * S / N, w = 14 + Math.pow(rnd(), 1.6) * 70, ph = rnd(), pk = 45 + rnd() * 55;
    for (var tw = 0; tw < 2; tw++) {
      var xb = x0 - tw * S;
      if (tw === 1 && x0 + SHIFT + w < S) continue;
      var l = FX.shape(strip, "ray" + i + "_" + tw);
      FX.group(l, "rect", { size: [w, S + 200], fill: [1, 1, 1] });
      l.anchorPoint.setValue([0, 0]);
      l.position.expression = "var a = (time / " + D + " + " + ph + ") % 1; [" + xb + " + " + SHIFT + " * a, " + (S / 2) + "]";
      l.opacity.expression = "var a = (time / " + D + " + " + ph + ") % 1; var s = Math.sin(Math.PI * a); " + pk + " * s * s";
    }
  }
  // 2. rays comp: blur across the bars (soft spokes), polar, radial falloff
  var rc = FX.comp("cb_sb_rays_v" + V, S, S, FPS, D, "fxlib_density");
  var rl = rc.layers.add(strip); rl.name = "strip";
  FX.blur(rl, 16, 2);                                             // 2 = horizontal only
  var pc = FX.fx(rl, "ADBE Polar Coordinates");
  FX.set(pc, "Interpolation", 1); FX.set(pc, "Type of Conversion", 1);   // AE 26: interpolation is 0..1; 1 = Rect to Polar
  var fo = FX.ramp(rc, "falloff", S / 2, S / 2, 980, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.MULTIPLY);
  var fo2 = FX.ramp(rc, "falloff2", S / 2, S / 2, 1150, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.MULTIPLY);

  // 3. the loop
  var c = FX.comp(name, W, H, FPS, D);
  // wide warm wash (the whole scene goes warm when the burst is on)
  var wash = FX.ramp(c, "warm_wash", CX, CY, 1150, [1, 0.3, 0, 1], [0, 0, 0, 1], BlendingMode.ADD);
  wash.layer.opacity.setValue(30);
  // spokes
  var rays = c.layers.add(rc); rays.name = "rays";
  rays.position.setValue([CX, CY]); rays.rotation.setValue(180);     // strip seam points down, behind the number
  var tt = FX.fx(rays, "ADBE Tritone"); FX.set(tt, "Highlights", FX.rgb("FFE060")); FX.set(tt, "Midtones", FX.rgb("FFC040")); FX.set(tt, "Shadows", [0, 0, 0]);
  rays.blendingMode = BlendingMode.ADD; rays.opacity.setValue(35);
  // core glow: hot centre + yellow body
  var g1 = FX.ramp(c, "glow_yellow", CX, CY, 700, [1, 0.86, 0, 1], [0, 0, 0, 1], BlendingMode.ADD);
  var g2 = FX.ramp(c, "glow_core", CX, CY, 350, [CORE[0], CORE[1], CORE[2], 1], [0, 0, 0, 1], BlendingMode.ADD);
  g2.layer.opacity.setValue(65);
  // breathing (2 cycles per loop), on the glows only
  g1.layer.opacity.expression = "58 + 6 * Math.sin(2 * Math.PI * 2 * time / " + D + ")";

  // 4. glitter: bokeh dots drifting outward and twinkling, a few 4-point glints (own precomp so its glow only
  //    blooms the sparkles)
  var main = c;
  c = FX.comp("cb_sb_glitter_v" + V, W, H, FPS, D, "fxlib_density");
  var DC = [FX.rgb("FFE070"), FX.rgb("FFB040"), FX.rgb("FFF4C0"), ORA];
  for (var k = 0; k < 110; k++) {
    var d = FX.shape(c, "dot" + k), sz = 6 + Math.pow(rnd(), 2) * 10;
    FX.group(d, "ellipse", { size: [sz, sz], fill: DC[k % 4] });
    d.anchorPoint.setValue([0, 0]);
    var ang = rnd() * 2 * Math.PI, r0 = 120 + rnd() * 380, r1 = r0 + 160 + rnd() * 260, ph2 = rnd(), tw2 = 3 + Math.floor(rnd() * 4);
    d.position.expression = "var a = (time / " + D + " + " + ph2 + ") % 1; var r = " + r0 + " + (" + (r1 - r0) + ") * a; [" +
      CX + " + Math.cos(" + ang + ") * r, " + CY + " + Math.sin(" + ang + ") * r]";
    d.opacity.expression = "var a = (time / " + D + " + " + ph2 + ") % 1; var s = Math.sin(Math.PI * a); " +
      "var tw = 0.55 + 0.45 * Math.sin(2 * Math.PI * " + tw2 + " * time / " + D + " + " + (rnd() * 6.28) + "); 100 * s * tw";
    d.blendingMode = BlendingMode.ADD;
  }
  for (var q = 0; q < 12; q++) {
    var st = FX.shape(c, "glint" + q), L = 14 + rnd() * 18;
    FX.group(st, "path", { points: [[-L, 0], [L, 0]], stroke: CORE, width: 2.2, taper: [100, 100] });
    FX.group(st, "path", { points: [[0, -L], [0, L]], stroke: CORE, width: 2.2, taper: [100, 100] });
    st.anchorPoint.setValue([0, 0]);
    var a2 = rnd() * 2 * Math.PI, rr = 150 + rnd() * 450;
    st.position.setValue([CX + Math.cos(a2) * rr, CY + Math.sin(a2) * rr]);
    var f = 1 + Math.floor(rnd() * 2), p = rnd() * 6.28;
    st.opacity.expression = "var v = Math.sin(2 * Math.PI * " + f + " * time / " + D + " + " + p + "); 100 * Math.pow(Math.max(0, v), 3)";
    st.scale.expression = "var v = Math.max(0, Math.sin(2 * Math.PI * " + f + " * time / " + D + " + " + p + ")); [40 + 60 * v, 40 + 60 * v]";
    st.blendingMode = BlendingMode.ADD;
  }
  var gl = FX.adj(c, "glow_glitter"); FX.glow(gl, 10, 0.6, 60, YEL, WARM);
  var gli = main.layers.add(c); gli.name = "glitter"; gli.blendingMode = BlendingMode.ADD;
  return FX.done(main, '"mode":"additive"');
}
