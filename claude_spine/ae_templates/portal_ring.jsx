/*TEMPLATE {"name":"portal_ring","doc":"The churning edge of a magic portal: a thin hot ring and a second hair-line ring, both torn into lace by turbulence, inside a cloudy cyan fringe and wisps of plasma. Renders on black for an additive layer (mode=\"additive\"). Cycles seamlessly, so it can loop in Spine. Pair it with the portal recipe (fx_recipe recipe=portal), which supplies the swirling disc, specks, comet streaks and flashes.","params":{"size":384,"duration":2.0,"fps":24,"color":"D6F8FF","glow_color":"2FB4FF","deep":"1646FF","radius":0.3,"width":0.014,"roughness":15,"scale":50,"fringe":1.0,"plasma":0.8,"glow":1.0,"seed":3}} */
var W = P.size, D = P.duration, name = P.comp || "portal_ring";
var core = AEFX.rgb(P.color), cyan = AEFX.rgb(P.glow_color), deep = AEFX.rgb(P.deep);
var comp = AEFX.comp(name, W, W, P.fps, D);
var cx = W / 2, R = W * P.radius * 2;          // ellipse size is a diameter

function tdisp(layer, amount, size, seed, offset) {
  var td = AEFX.fx(layer, "ADBE Turbulent Displace");
  AEFX.set(td, "Amount", amount);
  AEFX.set(td, "Size", size);
  AEFX.set(td, "Complexity", 6);
  AEFX.set(td, "Random Seed", seed);
  var ev = AEFX.find(td, "Evolution");
  ev.setValueAtTime(0, offset); ev.setValueAtTime(D, offset + 360);
  AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1);
  return td;
}
function ring(nm, diameter, color, strokeW, opacity) {
  var l = AEFX.shape(comp, nm);
  var e = AEFX.ellipse(l, diameter, null, color, strokeW);
  l.position.setValue([cx, cx]);
  l.opacity.setValue(opacity);
  return l;
}

// back to front: cloudy fringe, plasma wisps, thick-ish ring, hair ring, hot core ring
var fr = ring("fringe", R * 1.02, cyan, W * 0.085 * P.fringe, 14);
tdisp(fr, P.roughness * 2.0, W * 0.16, P.seed + 11, 0);
AEFX.fx(fr, "ADBE Gaussian Blur 2").property("Blurriness").setValue(W * 0.012);
fr.blendingMode = BlendingMode.ADD;

// plasma: a noise cloud shown only inside a soft band around the ring
var band = ring("band_matte", R * 1.13, [1, 1, 1], W * 0.105, 100);
AEFX.fx(band, "ADBE Gaussian Blur 2").property("Blurriness").setValue(W * 0.05);
var pn = comp.layers.addSolid([0, 0, 0], "plasma", W, W, 1);
var fn = AEFX.fx(pn, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", 100); AEFX.set(fn, "Brightness", -32);
AEFX.set(fn, "Scale", P.scale * 1.1); AEFX.set(fn, "Complexity", 5); AEFX.set(fn, "Random Seed", P.seed);
var pev = AEFX.find(fn, "Evolution");
pev.setValueAtTime(0, 0); pev.setValueAtTime(D, 360);
AEFX.set(fn, "Cycle Evolution", 1); AEFX.set(fn, "Cycle (in Revolutions)", 1);
var tt = AEFX.fx(pn, "ADBE Tritone");
AEFX.set(tt, "Highlights", core); AEFX.set(tt, "Midtones", cyan); AEFX.set(tt, "Shadows", [0, 0, 0]);
pn.blendingMode = BlendingMode.ADD;
pn.opacity.setValue(87 * P.plasma);
band.moveBefore(pn);
pn.setTrackMatte(band, TrackMatteType.LUMA);
band.enabled = false;

var r1 = ring("ring", R, core, W * P.width * 1.2, 100);
tdisp(r1, P.roughness * 0.8, W * 0.09, P.seed, 0);
var r2 = ring("ring_hair", R * 0.985, core, W * P.width * 0.6, 85);
tdisp(r2, P.roughness * 1.05, W * 0.07, P.seed + 7, 200);
var r3 = ring("ring_hot", R * 1.01, [1, 1, 1], W * P.width * 0.32, 90);
tdisp(r3, P.roughness * 0.5, W * 0.115, P.seed + 3, 90);

// glow over everything
var glow = comp.layers.addSolid([1, 1, 1], "glow", W, W, 1); glow.adjustmentLayer = true;
var g1 = AEFX.fx(glow, "ADBE Glo2");
g1.property("Glow Threshold").setValue(70); g1.property("Glow Radius").setValue(W * 0.035 * P.glow); g1.property("Glow Intensity").setValue(0.7 * P.glow);
return AEFX.done(comp);
