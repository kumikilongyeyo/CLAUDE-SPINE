/*TEMPLATE {"name":"orbit_ribbons","doc":"Ribbons of energy orbiting a subject on tilted rings, rendered as a BACK half and a FRONT half so the effect really wraps round it: in Spine the `<comp>_back` comp goes behind the subject and `<comp>_front` in front (same timing, import both). Each ring is a thin band of flowing fractal noise wrapped into a circle with Polar Coordinates (mirrored, so no seam), turning half a revolution per loop, squashed by `tilt` into an ellipse seen at an angle and turned `angle` degrees; the near (lower) half of each ellipse is the front. `rings` 1-3 rings at spread angles, alternate ones orbiting the other way. Ring radius `radius` (fraction of the half-size) must clear the subject so the split points sit beside it. Built in grey, coloured once (black -> color -> core): two-tone, import tintable. Additive on black (mode=\"additive\"); loops exactly. `<comp>` itself holds both halves (to judge it).","params":{"size":768,"duration":2.5,"fps":24,"color":"8A3CFF","core":"FFFFFF","radius":0.78,"band":0.05,"tilt":0.3,"angle":-16,"rings":2,"spread":34,"flow":160,"glow":1.0,"seed":4}} */
var S = P.size, D = P.duration, name = P.comp || "orbit_ribbons", C = S / 2;
var DD = 2 * D, SH = 256, rowR = SH * P.radius, half = SH * P.band;
// 1. a flowing band on a strip: x = angle round the ring, y = distance from the centre (top row = centre)
var src = AEFX.comp(name + "_band_src", 1024, SH, P.fps, DD);
src.layers.addSolid([0, 0, 0], "black", 1024, SH, 1);
function flow(nm, sx, sy, speed, op, seedK) {
  var n = src.layers.addSolid([0, 0, 0], nm, 1024, SH, 1);
  var fn = AEFX.fx(n, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 9); AEFX.set(fn, "Noise Type", 3);              // Dynamic Twist: twisting filaments
  AEFX.set(fn, "Contrast", 170); AEFX.set(fn, "Brightness", -20);
  AEFX.set(fn, "Uniform Scaling", 0); AEFX.set(fn, "Scale Width", sx); AEFX.set(fn, "Scale Height", sy);
  AEFX.set(fn, "Complexity", 4); AEFX.set(fn, "Random Seed", P.seed + seedK);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(DD, 360 * DD / D);
  AEFX.find(fn, "Offset Turbulence").expression = "[value[0] + time * " + speed + ", value[1]]";   // streams along the ring
  if (op < 100) { n.blendingMode = BlendingMode.SCREEN; n.opacity.setValue(op); }
}
flow("ribbon", 220, 26, P.flow, 100, 0);
flow("fine", 90, 12, P.flow * 1.7, 60, 5);
function bandRamp(nm, from, to) {          // multiply by a ramp white at the band's middle row, black at `to`
  var l = src.layers.addSolid([1, 1, 1], nm, 1024, SH, 1);
  var r = AEFX.fx(l, "ADBE Ramp");
  AEFX.set(r, "ADBE Ramp-0001", [512, from]); AEFX.set(r, "ADBE Ramp-0002", [1, 1, 1, 1]);
  AEFX.set(r, "ADBE Ramp-0003", [512, to]); AEFX.set(r, "ADBE Ramp-0004", [0, 0, 0, 1]);
  l.blendingMode = BlendingMode.MULTIPLY;
}
bandRamp("band_in", rowR, rowR - half);
bandRamp("band_out", rowR, rowR + half);
var strip = AEFX.loopify(src, name + "_band", D);
// 2. mirror (no seam at the wrap), squeeze into a square, wrap round the centre (one comp up: Polar Coordinates
//    works in the layer's own pixels), turn half a revolution per loop (the mirror makes 180 degrees an exact loop)
var M = AEFX.comp(name + "_mirror", 2048, SH, P.fps, D);
var ma = M.layers.add(strip); ma.position.setValue([512, SH / 2]);
var mb = M.layers.add(strip); mb.scale.setValue([-100, 100]); mb.position.setValue([1536, SH / 2]);
var Q = AEFX.comp(name + "_square", S, S, P.fps, D);
var sq = Q.layers.add(M); sq.scale.setValue([S / 2048 * 100, S / SH * 100]); sq.position.setValue([C, C]);
var RING = AEFX.comp(name + "_ring", S, S, P.fps, D);
var rl = RING.layers.add(Q);
var pc = AEFX.fx(rl, "ADBE Polar Coordinates");
pc.property(1).setValue(1); pc.property(2).setValue(1);
rl.rotation.expression = "180 * time / " + D;
// 3. per half: the ring squashed into an ellipse (tilt), masked to its near (lower) or far (upper) half; the split
//    runs through the centre, so its ends sit at the ellipse's left and right tips, beside the subject
function halfComp(which) {
  var H = AEFX.comp(name + "_ellipse_" + which, S, S, P.fps, D);
  var l = H.layers.add(RING); l.scale.setValue([100, 100 * P.tilt]);
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var sh = new Shape(), y0 = which === "front" ? C : -S, y1 = which === "front" ? 2 * S : C;
  sh.vertices = [[-S, y0], [2 * S, y0], [2 * S, y1], [-S, y1]]; sh.closed = true;
  m.property("ADBE Mask Shape").setValue(sh);
  m.property("ADBE Mask Feather").setValue([0, S * 0.03]);
  return H;
}
var HF = halfComp("front"), HB = halfComp("back");
// 4. grey light per half: every ring at its own angle (alternate rings orbit the other way), bloomed, coloured once
function lumaOf(which, H) {
  var G = AEFX.comp(name + "_luma_" + which, S, S, P.fps, D);
  G.layers.addSolid([0, 0, 0], "black", S, S, 1);
  var n = Math.max(1, Math.min(3, P.rings));
  for (var i = 0; i < n; i++) {
    var l = G.layers.add(H); l.blendingMode = BlendingMode.ADD;
    l.rotation.setValue(P.angle + P.spread * (i - (n - 1) / 2));
    if (i % 2 === 1) l.scale.setValue([-100, 100]);       // the other way round
    if (i > 0) {                                             // and out of step: time-remapped so it still loops
      l.timeRemapEnabled = true;
      l.property("ADBE Time Remapping").expression = "(time + " + (D * i / n) + ") % " + D;
    }
  }
  var gl = G.layers.addSolid([1, 1, 1], "bloom", S, S, 1); gl.adjustmentLayer = true;
  var gf = AEFX.fx(gl, "ADBE Glo2");
  gf.property("Glow Threshold").setValue(40); gf.property("Glow Radius").setValue(S * 0.02 * P.glow);
  gf.property("Glow Intensity").setValue(0.7 * P.glow);
  var out = AEFX.comp(name + "_" + which, S, S, P.fps, D);
  var col = out.layers.add(G);
  var tt = AEFX.fx(col, "ADBE Tritone");
  AEFX.set(tt, "Highlights", AEFX.rgb(P.core)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
  return out;
}
var front = lumaOf("front", HF), back = lumaOf("back", HB);
var comp = AEFX.comp(name, S, S, P.fps, D);
var b = comp.layers.add(back); b.blendingMode = BlendingMode.ADD;
var f = comp.layers.add(front); f.blendingMode = BlendingMode.ADD;
return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","tintable":true,"back":"' + back.name + '","front":"' + front.name + '"');
