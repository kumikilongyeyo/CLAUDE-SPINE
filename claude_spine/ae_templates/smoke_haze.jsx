/*TEMPLATE {"name":"smoke_haze","doc":"A churning haze that fills a box, with exaggerated convection physics: the smoke RISES (noise streams upward at `rise` px/s), a deeper slower layer behind it gives depth (parallax), the whole mass SWIRLS back and forth (`swirl` degrees, a convection cell), it is denser low down and thins toward the edges and the top. Transparent background (mode=\"alpha\"). Rendered twice the duration and crossfaded, so it loops seamlessly while really moving. Pair with fx_recipe recipe=smoke_glow (base glow) or cell_glow.","params":{"width":192,"height":512,"duration":2.0,"fps":24,"light":"FFD6C8","mid":"C98A7A","shadow":"5A3530","scale":90,"contrast":75,"brightness":28,"rise":90,"swirl":18,"turbulence":22,"density":0.95,"edge":0.12,"seed":6}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "smoke_haze";
var hi = AEFX.rgb(P.light), mid = AEFX.rgb(P.mid), lo = AEFX.rgb(P.shadow);
var DD = 2 * D;
var src = AEFX.comp(name + "_src", W, H, P.fps, DD);
src.layers.addSolid([0, 0, 0], "black", W, H, 1);      // without a black base the multiply box shows as a hard rectangle
function haze(nm, scaleK, riseK, opacity, blend, seedK) {
  var n = src.layers.addSolid([0, 0, 0], nm, W, H, 1);
  var fn = AEFX.fx(n, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", P.brightness);
  AEFX.set(fn, "Scale", P.scale * scaleK); AEFX.set(fn, "Complexity", 5); AEFX.set(fn, "Random Seed", P.seed + seedK);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(DD, 360 * DD / D);
  AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] - time * " + (P.rise * riseK) + "]";   // convection: up
  if (blend) n.blendingMode = blend;
  if (opacity < 100) n.opacity.setValue(opacity);
  return n;
}
haze("deep", 1.6, 0.5, 100, null, 3);                       // far layer: bigger, slower (parallax)
haze("near", 1.0, 1.0, 42, BlendingMode.SCREEN, 0);          // near layer: finer, faster
// denser low down, thinning toward the top
var box = src.layers.addSolid([1, 1, 1], "box", W, H, 1);
var r = AEFX.fx(box, "ADBE Ramp");
AEFX.set(r, "ADBE Ramp-0001", [W / 2, H * 0.05]); AEFX.set(r, "ADBE Ramp-0002", [0.5, 0.5, 0.5, 1]);
AEFX.set(r, "ADBE Ramp-0003", [W / 2, H * 0.95]); AEFX.set(r, "ADBE Ramp-0004", [1, 1, 1, 1]);
box.blendingMode = BlendingMode.MULTIPLY;
var roll = src.layers.addSolid([1, 1, 1], "roll", W, H, 1); roll.adjustmentLayer = true;
var td = AEFX.fx(roll, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.turbulence); AEFX.set(td, "Size", W * 0.4); AEFX.set(td, "Complexity", 3);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(DD, 360 * DD / D);
if (P.swirl > 0) {                                           // the convection cell rocks the whole mass; sine period D keeps the loop exact
  var tw = src.layers.addSolid([1, 1, 1], "swirl", W, H, 1); tw.adjustmentLayer = true;
  var twf = AEFX.fx(tw, "ADBE Twirl");
  AEFX.set(twf, "ADBE Twirl-0002", 60); AEFX.set(twf, "ADBE Twirl-0003", [W / 2, H * 0.55]);
  AEFX.find(twf, "ADBE Twirl-0001").expression = "Math.sin(time * 2 * Math.PI / " + D + ") * " + P.swirl;
}
// soft box edges AFTER the twirl (a mask on the noise gets dragged into curved black bands by it): a black overlay
// with an inverted, feathered mask
var edge = src.layers.addSolid([0, 0, 0], "edge", W, H, 1);
var em = edge.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
var esh = new Shape(); var ex = W * P.edge, ey = H * P.edge * 0.4;
esh.vertices = [[ex, ey], [W - ex, ey], [W - ex, H - ey], [ex, H - ey]]; esh.closed = true;
em.property("ADBE Mask Shape").setValue(esh);
em.property("ADBE Mask Feather").setValue([W * 0.18, W * 0.18]);
em.inverted = true;
var lum = AEFX.loopify(src, name + "_luma", D);
var comp = AEFX.comp(name, W, H, P.fps, D);
var matte = comp.layers.add(lum); matte.name = "alpha_from_density";
var col = comp.layers.add(lum); col.name = "colour"; col.moveAfter(matte);
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", hi); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", lo);
col.setTrackMatte(matte, TrackMatteType.LUMA);
matte.enabled = false;
col.opacity.setValue(100 * P.density);
return AEFX.done(comp);
