// target_ring: dot -> flash star with asterisk -> glowing ring with cross spikes, thinning, breaking into dashes.
// Reference: 085820 GIF, 25 fps, GIF px x S. t = GIF frame * 0.04.
function BUILD(V) {
  var S = 2, W = 460, H = 408, F = 0.04, cx = W / 2, cy = H / 2;
  var name = "tr_target_ring_v" + V;
  var c = FX.comp(name, W, H, 25, 0.96);
  var CORE = FX.rgb("FFFFC4"), HOT = FX.rgb("FFE27A"), ORA = FX.rgb("FF7A1A"), RED = FX.rgb("E8360C");
  var f = FX.gt("target_ring");

  // 1. the dot (f8) and the flash disk (f9)
  var dot = FX.shape(c, "dot");
  var dg = FX.group(dot, "ellipse", { size: [10 * S, 10 * S], fill: CORE });
  dot.position.setValue([cx, cy]);
  FX.keys(dot.opacity, [[f(7.5), 0], [f(7.51), 100], [f(9.5), 100], [f(9.51), 0]], false);
  FX.keys(dg.size, [[f(8), [10 * S, 10 * S]], [f(9), [26 * S, 26 * S]]], false);
  var ast = FX.shape(c, "asterisk");                // dark spokes on the flash disk
  var ag = FX.group(ast, "path", { points: [[-7 * S, 0], [7 * S, 0]], stroke: RED, width: 1.6 * S, repeat: 3 });
  ag.rRot.setValue(60);
  ast.position.setValue([cx, cy]);
  FX.keys(ast.opacity, [[f(8.5), 0], [f(8.51), 100], [f(9.5), 100], [f(9.51), 0]], false);

  // 2. the ring: born at f10 at r=50, drifts to r=58, stroke 5 -> 2, then breaks into dashes and fades
  var ring = FX.shape(c, "ring");
  var rg = FX.group(ring, "ellipse", { size: [100 * S, 100 * S], stroke: FX.rgb("FFEFA2"), width: 5 * S });
  ring.position.setValue([cx, cy]);
  FX.keys(rg.size, [[f(9.6), [70 * S, 70 * S]], [f(10), [96 * S, 96 * S]], [f(11), [104 * S, 104 * S]], [f(16), [111 * S, 111 * S]], [f(22), [114 * S, 114 * S]]], "out");
  FX.keys(rg.strokeW, [[f(10), 5.2 * S], [f(12), 4.6 * S], [f(13), 2.0 * S], [f(22), 1.3 * S]], false);
  FX.keys(ring.opacity, [[f(9.5), 0], [f(9.6), 100], [f(18), 100], [f(22.5), 0]], false);
  // dashes: two dash/gap pairs of different lengths so the break-up looks irregular
  var stroke = rg.strokeProp;
  var dashes = stroke.property("ADBE Vector Stroke Dashes");
  dashes.addProperty("ADBE Vector Stroke Dash 1"); dashes.addProperty("ADBE Vector Stroke Gap 1");
  dashes.addProperty("ADBE Vector Stroke Dash 2"); dashes.addProperty("ADBE Vector Stroke Gap 2");
  stroke = ring.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
  dashes = stroke.property("ADBE Vector Stroke Dashes");
  FX.keys(dashes.property("ADBE Vector Stroke Dash 1"), [[f(15), 260 * S], [f(17), 110 * S], [f(19), 22 * S], [f(22), 4 * S]], false);
  FX.keys(dashes.property("ADBE Vector Stroke Gap 1"), [[f(15), 0], [f(17), 14 * S], [f(19), 24 * S], [f(22), 40 * S]], false);
  FX.keys(dashes.property("ADBE Vector Stroke Dash 2"), [[f(15), 180 * S], [f(17), 70 * S], [f(19), 12 * S], [f(22), 3 * S]], false);
  FX.keys(dashes.property("ADBE Vector Stroke Gap 2"), [[f(15), 0], [f(17), 22 * S], [f(19), 34 * S], [f(22), 50 * S]], false);

  // 3. four long cross spikes (thin, tapered both ends) and four short diagonal ticks; they fly out and shrink to dots
  function spikes(nm, rot, r0, r1, wid, keysIn, keysOut) {
    var l = FX.shape(c, nm);
    var g = FX.group(l, "path", { points: [[0, -r0 * S], [0, -r1 * S]], stroke: CORE, width: wid * S, repeat: 4, taper: [100, 100] });
    g.rRot.setValue(90);
    l.position.setValue([cx, cy]); l.rotation.setValue(rot);
    return { l: l, path: g.path, w: g.strokeW };
  }
  function seg(r0, r1) { var s = new Shape(); s.vertices = [[0, -r0 * S], [0, -r1 * S]]; s.closed = false; return s; }
  var cross = spikes("cross_spikes", 0, 20, 30, 4.2);
  FX.keys(cross.path, [[f(9), seg(12, 34)], [f(10), seg(34, 80)], [f(12), seg(38, 80)], [f(13), seg(70, 86)], [f(14), seg(80, 86)],
                       [f(16), seg(86, 89)], [f(19), seg(90, 91.5)]], false);
  FX.keys(cross.w, [[f(9), 3.4 * S], [f(12), 4.4 * S], [f(13), 2.8 * S], [f(19), 1.6 * S]], false);
  FX.keys(cross.l.opacity, [[f(8.5), 0], [f(8.6), 100], [f(17), 100], [f(20), 0]], false);
  var diag = spikes("diag_ticks", 45, 40, 52, 2.6);
  FX.keys(diag.path, [[f(9), seg(14, 24)], [f(10), seg(55, 66)], [f(12), seg(58, 66)], [f(14), seg(63, 66)], [f(17), seg(65, 66.5)], [f(20), seg(66, 67)]], false);
  FX.keys(diag.l.opacity, [[f(8.5), 0], [f(8.6), 100], [f(16), 100], [f(20), 0]], false);

  // 4. inner reticle dots: four at r=17 plus the centre, faint
  var dots = FX.shape(c, "reticle_dots");
  var rd = FX.group(dots, "ellipse", { size: [2.6 * S, 2.6 * S], fill: HOT, repeat: 4 });
  rd.rRot.setValue(90);
  dots.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group").property("ADBE Vector Position").setValue([0, -17 * S]);
  var dots2 = FX.shape(c, "reticle_dots_far");
  var rd2 = FX.group(dots2, "ellipse", { size: [2.2 * S, 2.2 * S], fill: HOT, repeat: 4 });
  rd2.rRot.setValue(90);
  dots2.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group").property("ADBE Vector Position").setValue([0, -30 * S]);
  dots.position.setValue([cx, cy]); dots2.position.setValue([cx, cy]);
  FX.keys(dots.opacity, [[f(9.5), 0], [f(9.6), 100], [f(15), 80], [f(18), 0]], false);
  FX.keys(dots2.opacity, [[f(9.5), 0], [f(9.6), 90], [f(15), 70], [f(18), 0]], false);

  // 5. light: a tight hot glow and a wide orange-red one, strongest on the flash, settling as the ring thins
  var g1 = FX.adj(c, "glow_tight");
  var gl1 = FX.glow(g1, 4 * S, 0.8, 50, HOT, ORA);
  var g2 = FX.adj(c, "glow_wide");
  var gl2 = FX.glow(g2, 16 * S, 0.7, 45, ORA, RED);
  FX.keys(FX.find(gl2, "Glow Intensity"), [[f(9), 2.0], [f(10), 1.5], [f(12.4), 1.3], [f(13), 0.22], [f(18), 0.1]], false);
  FX.keys(FX.find(gl1, "Glow Intensity"), [[f(9), 1.4], [f(11), 0.8], [f(13), 0.35]], false);
  return FX.done(c);
}
