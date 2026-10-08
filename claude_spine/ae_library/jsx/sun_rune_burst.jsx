// sun_rune_burst: sparks gather in -> centre dot -> thick ring + cross spikes + radial streaks burst out ->
// ring expands and thins, a starburst of chords spins in the middle, a soft amber donut and a dashed outer ring
// linger and fade. Reference 085813 cell, measured: ring r 22 (f8) -> 32 (f9) -> 34 (f10), gone by f12; donut r~30.
function BUILD(V) {
  var S = 3, W = 138 * S, H = 147 * S, cx = 76 * S, cy = 70 * S;
  var name = "sr_sun_rune_v" + V;
  var c = FX.comp(name, W, H, 25, 0.96);
  var f = FX.gt("sun_rune_burst");
  var CORE = FX.rgb("FFFBD0"), YEL = FX.rgb("FFE07A"), ORA = FX.rgb("FF8A1E"), RED = FX.rgb("E0400C"), AMB = FX.rgb("C8801E");
  var rnd = FX.rng(13);

  // 1. gathering sparks: 12 short streaks fly IN from r 55..75 to the centre (f2..f7), growing brighter
  for (var i = 0; i < 12; i++) {
    var a = rnd() * 360, r0 = (52 + rnd() * 24) * S, t0 = f(1.5 + rnd() * 2.5);
    var l = FX.shape(c, "gather" + i);
    FX.group(l, "path", { points: [[-3 * S, 0], [3 * S, 0]], stroke: YEL, width: 1.6 * S, taper: [100, 100] });
    var ar = a * Math.PI / 180;
    FX.keys(l.position, [[t0, [cx + Math.cos(ar) * r0, cy + Math.sin(ar) * r0]], [f(7.2), [cx + Math.cos(ar) * r0 * 0.25, cy + Math.sin(ar) * r0 * 0.25]]], "in");
    l.rotation.setValue(a);
    FX.keys(l.scale, [[t0, [60, 100]], [f(6), [100, 100]], [f(7.2), [200, 80]]], false);
    FX.keys(l.opacity, [[t0, 0], [t0 + 0.04, 85], [f(7.2), 100], [f(7.3), 0]], false);
  }
  // 2. centre dot (f7) that pops into the ring
  var dot = FX.shape(c, "dot");
  var dg = FX.group(dot, "ellipse", { size: [8 * S, 8 * S], fill: CORE });
  dot.position.setValue([cx, cy]);
  FX.keys(dot.opacity, [[f(6.8), 0], [f(6.9), 100], [f(7.7), 100], [f(7.8), 0]], false);

  // 3. the ring: r 22 thick at f8, r 32 at f9, r 34 at f10 thinning, fading by f12
  var ring = FX.shape(c, "ring");
  var rg = FX.group(ring, "ellipse", { size: [44 * S, 44 * S], stroke: FX.rgb("FFE9A6"), width: 7 * S });
  ring.position.setValue([cx, cy]);
  FX.keys(rg.size, [[f(7.7), [30 * S, 30 * S]], [f(8), [44 * S, 44 * S]], [f(9), [64 * S, 64 * S]], [f(10), [68 * S, 68 * S]], [f(12), [72 * S, 72 * S]]], "out");
  FX.keys(rg.strokeW, [[f(8), 8 * S], [f(9), 3.2 * S], [f(10), 2.4 * S], [f(12), 1.2 * S]], false);
  FX.keys(ring.opacity, [[f(7.7), 0], [f(7.8), 100], [f(10.5), 100], [f(12.5), 0]], false);

  // 4. four cross spikes on the flash
  var cr = FX.shape(c, "cross");
  var cg = FX.group(cr, "path", { points: [[0, -16 * S], [0, -40 * S]], stroke: CORE, width: 2.6 * S, repeat: 4, taper: [100, 100] });
  cg.rRot.setValue(90); cr.position.setValue([cx, cy]);
  function seg(r0, r1) { var s = new Shape(); s.vertices = [[0, -r0 * S], [0, -r1 * S]]; s.closed = false; return s; }
  FX.keys(cg.path, [[f(8), seg(14, 44)], [f(9), seg(30, 56)], [f(10), seg(44, 60)], [f(11), seg(54, 61)]], false);
  FX.keys(cr.opacity, [[f(7.7), 0], [f(7.8), 100], [f(10), 100], [f(11.5), 0]], false);

  // 5. radial streaks bursting out (f8..f12): 22 thin lines from r~24 to r~65, plus fat ember sparks
  for (var k = 0; k < 22; k++) {
    var aa = k * 360 / 22 + (rnd() - 0.5) * 12, len = (6 + rnd() * 10) * S;
    FX.streak(c, "ray" + k, cx, cy, aa, (20 + rnd() * 6) * S, (48 + rnd() * 20) * S, f(7.8), f(11.5 + rnd() * 1.5), len, (1.1 + rnd() * 0.8) * S, YEL);
  }
  for (var q = 0; q < 14; q++) {
    var ab = rnd() * 360, l2 = (2.5 + rnd() * 3) * S;
    FX.streak(c, "ember" + q, cx, cy, ab, 26 * S, (62 + rnd() * 14) * S, f(8), f(12 + rnd() * 6), l2, 2.0 * S, ORA);
  }

  // 6. spinning starburst of chords in the middle (f9..f19): 9 lines through near the centre, rotating, shrinking
  var sb = FX.shape(c, "starburst");
  for (var j = 0; j < 9; j++) {
    var aj = j * 20 + rnd() * 14, rr = (22 + rnd() * 18) * S, off = (rnd() - 0.5) * 6 * S;
    var cs = Math.cos(aj * Math.PI / 180), sn = Math.sin(aj * Math.PI / 180);
    FX.group(sb, "path", { points: [[-cs * rr - sn * off, -sn * rr + cs * off], [cs * rr - sn * off, sn * rr + cs * off]], stroke: j % 3 ? ORA : YEL, width: 1.7 * S, taper: [70, 70] });
  }
  sb.position.setValue([cx, cy]);
  FX.keys(sb.rotation, [[f(9), -10], [f(20), 75]], false);
  FX.keys(sb.scale, [[f(9), [130, 130]], [f(13), [100, 100]], [f(17), [55, 55]], [f(19.5), [15, 15]]], false);
  FX.keys(sb.opacity, [[f(8.7), 0], [f(9), 100], [f(18), 100], [f(19.6), 0]], false);

  // 7. soft amber donut (f12..f23) behind, and the thin dashed outer ring (f13..f19)
  var don = FX.shape(c, "donut");
  var dn = FX.group(don, "ellipse", { size: [60 * S, 60 * S], stroke: FX.rgb("9A5E1C"), width: 12 * S });
  don.position.setValue([cx, cy]);
  FX.blur(don, 6 * S);
  FX.keys(dn.size, [[f(11), [52 * S, 52 * S]], [f(23), [62 * S, 62 * S]]], "out");
  FX.keys(don.opacity, [[f(11), 0], [f(13), 80], [f(19), 70], [f(23.5), 25]], false);
  don.blendingMode = BlendingMode.SCREEN;
  var dsh = FX.shape(c, "dashed_ring");
  var dr = FX.group(dsh, "ellipse", { size: [80 * S, 80 * S], stroke: YEL, width: 0.8 * S });
  dsh.position.setValue([cx, cy]);
  var st = dsh.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
  st.property("ADBE Vector Stroke Dashes").addProperty("ADBE Vector Stroke Dash 1");
  st = dsh.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
  st.property("ADBE Vector Stroke Dashes").addProperty("ADBE Vector Stroke Gap 1");
  st = dsh.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
  st.property("ADBE Vector Stroke Dashes").property("ADBE Vector Stroke Dash 1").setValue(26 * S);
  st.property("ADBE Vector Stroke Dashes").property("ADBE Vector Stroke Gap 1").setValue(8 * S);
  FX.keys(dr.size, [[f(12), [76 * S, 76 * S]], [f(20), [80 * S, 80 * S]]], "out");
  FX.keys(dsh.rotation, [[f(12), 0], [f(20), 40]], false);
  FX.keys(dsh.opacity, [[f(12), 0], [f(13), 80], [f(18), 60], [f(20), 0]], false);

  // 8. light
  var g1 = FX.adj(c, "glow_tight"); var gl1 = FX.glow(g1, 3 * S, 1.0, 50, YEL, ORA);
  var g2 = FX.adj(c, "glow_wide"); var gl2 = FX.glow(g2, 12 * S, 1.0, 45, ORA, RED);
  FX.keys(FX.find(gl2, "Glow Intensity"), [[f(7.5), 0.8], [f(8), 2.6], [f(9.5), 1.6], [f(12), 0.9], [f(18), 0.6]], false);
  don.moveToBeginning();
  return FX.done(c);
}
