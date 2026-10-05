/*TEMPLATE {"name":"electric_frame","doc":"A rounded rectangle of crackling electricity: a hot hair-line and a thicker coloured line both torn into jagged lightning by fast turbulence, over a soft halo. Renders on black for an additive layer (mode=\"additive\"). Loops seamlessly (the turbulence cycles `cycles` times per loop), so it can sit in a Spine loop. Frames, buttons, win borders, power-up outlines. Pair it with the electric_frame recipe (fx_recipe recipe=electric_frame) for the underglow and sparks.","params":{"width":512,"height":512,"duration":1.0,"fps":24,"color":"E6B8FF","glow_color":"9A30FF","margin":0.09,"corner":0.07,"roughness":16,"scale":22,"thickness":0.0048,"cycles":2,"halo":1.0,"glow":1.0,"seed":4}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "electric_frame";
var core = AEFX.rgb(P.color), vio = AEFX.rgb(P.glow_color);
var comp = AEFX.comp(name, W, H, P.fps, D);
var inset = Math.min(W, H) * P.margin, RW = W - 2 * inset, RH = H - 2 * inset, rad = Math.min(W, H) * P.corner * 2;

function tdisp(layer, amount, size, seed, offset, revs) {
  var td = AEFX.fx(layer, "ADBE Turbulent Displace");
  AEFX.set(td, "Amount", amount);
  AEFX.set(td, "Size", size);
  AEFX.set(td, "Complexity", 6);
  AEFX.set(td, "Random Seed", seed);
  var ev = AEFX.find(td, "Evolution");
  ev.setValueAtTime(0, offset); ev.setValueAtTime(D, offset + 360 * revs);
  AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", revs);
  return td;
}
function frameLine(nm, grow, color, strokeW, opacity) {
  var l = AEFX.shape(comp, nm);
  var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
  var c = g.property("ADBE Vectors Group");
  c.addProperty("ADBE Vector Shape - Rect");
  c.addProperty("ADBE Vector Graphic - Stroke");
  var cc = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
  cc.property("ADBE Vector Shape - Rect").property("ADBE Vector Rect Size").setValue([RW + grow, RH + grow]);
  cc.property("ADBE Vector Shape - Rect").property("ADBE Vector Rect Roundness").setValue(rad);
  var s = cc.property("ADBE Vector Graphic - Stroke");
  s.property("ADBE Vector Stroke Color").setValue(color);
  s.property("ADBE Vector Stroke Width").setValue(strokeW);
  l.position.setValue([W / 2, H / 2]);
  l.opacity.setValue(opacity);
  return l;
}

var m = Math.min(W, H);
// back to front: soft halo, wide violet line, thin bright lines
var h = frameLine("halo", 0, vio, m * 0.07 * P.halo, 35);
tdisp(h, P.roughness * 1.4, m * 0.12, P.seed + 9, 0, 1);
AEFX.fx(h, "ADBE Gaussian Blur 2").property("Blurriness").setValue(m * 0.025);
h.blendingMode = BlendingMode.ADD;

var w = frameLine("wide", 0, vio, m * P.thickness * 4.5, 85);
tdisp(w, P.roughness, m * P.scale / 400, P.seed, 0, P.cycles);
w.blendingMode = BlendingMode.ADD;

var t = frameLine("thin", 0, core, m * P.thickness * 2.0, 100);
tdisp(t, P.roughness * 0.85, m * P.scale / 400 * 1.2, P.seed + 3, 140, P.cycles);
var t2 = frameLine("hot", 0, [1, 1, 1], m * P.thickness * 0.9, 95);
tdisp(t2, P.roughness * 0.7, m * P.scale / 400 * 1.5, P.seed + 6, 250, P.cycles);

var glow = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); glow.adjustmentLayer = true;
var g1 = AEFX.fx(glow, "ADBE Glo2");
g1.property("Glow Threshold").setValue(55); g1.property("Glow Radius").setValue(m * 0.03 * P.glow); g1.property("Glow Intensity").setValue(0.9 * P.glow);
return AEFX.done(comp);
