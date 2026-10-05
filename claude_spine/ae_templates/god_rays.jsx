/*TEMPLATE {"name":"god_rays","doc":"Volumetric light rays (god rays) streaming from a source through a mask, with exaggerated real optics: light passes the GAPS of an occluder near the source (clouds or leaves = cycled fractal noise; slats = venetian blinds), a zoom radial blur centred on the source smears every gap outward into a shaft (what in-scattering by haze does), the shafts fade with distance (extinction, a radial falloff), the occluder turns slowly about the source (`sweep` degrees, one sine per loop, the same phase as fx_recipe god_rays) and drifts (evolution cycled) so the rays shift, and the light flickers as clouds pass (two sines with whole cycles per loop). `source` is in comp fractions (y down). Additive on black (mode=\"additive\"); loops exactly. Pair with fx_recipe recipe=god_rays (its ae_hint gives source, sweep and placement).","params":{"width":768,"height":768,"duration":4.0,"fps":24,"source":[0.29,0.14],"color":"FFE6A8","core":"FFFFFF","mask":"clouds","scale":55,"gaps":0.52,"opening":0.3,"slats":9,"length":95,"passes":2,"sweep":5,"drift":1,"flicker":0.3,"falloff":0.9,"gain":2.4,"glow":1.0,"seed":4}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "god_rays";
var sx = W * P.source[0], sy = H * P.source[1], diag = Math.sqrt(W * W + H * H);
function falloff(c, nm, r) {        // an OPAQUE radial ramp (white at the source, black beyond r), multiplied over what is below
  var l = c.layers.addSolid([1, 1, 1], nm, W, H, 1);
  var rp = AEFX.fx(l, "ADBE Ramp");
  AEFX.set(rp, "ADBE Ramp-0001", [sx, sy]); AEFX.set(rp, "ADBE Ramp-0002", [1, 1, 1, 1]);
  AEFX.set(rp, "ADBE Ramp-0003", [sx + r, sy]); AEFX.set(rp, "ADBE Ramp-0004", [0, 0, 0, 1]); AEFX.set(rp, "ADBE Ramp-0005", 2);
  l.blendingMode = BlendingMode.MULTIPLY;
  return l;
}
// 1. the mask: light only gets through the gaps, and only near the source (an opening around it)
var occ = AEFX.comp(name + "_mask", W, H, P.fps, D);
occ.layers.addSolid([0, 0, 0], "black", W, H, 1);
var S = Math.ceil(diag * 2);                                     // oversized so the sweep rotation never shows a corner
var gaps = occ.layers.addSolid(P.mask === "slats" ? [1, 1, 1] : [0, 0, 0], "gaps", S, S, 1);
gaps.position.setValue([sx, sy]);                                 // the layer turns about the source
if (P.mask === "slats") {
  var vb = AEFX.fx(gaps, "ADBE Venetian Blinds");
  AEFX.set(vb, "Transition Completion", 100 * (1 - P.gaps)); AEFX.set(vb, "Width", S / Math.max(1, P.slats) / 4);
  AEFX.set(vb, "Feather", 2);
} else {
  var fn = AEFX.fx(gaps, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", 160); AEFX.set(fn, "Brightness", 0);
  AEFX.set(fn, "Scale", P.scale); AEFX.set(fn, "Complexity", 4); AEFX.set(fn, "Random Seed", P.seed);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 360 * Math.max(1, P.drift));
  AEFX.set(fn, "Cycle Evolution", 1); AEFX.set(fn, "Cycle (in Revolutions)", Math.max(1, P.drift));
  var lv = AEFX.fx(gaps, "ADBE Easy Levels2");                  // keep only the holes: the light that gets through
  AEFX.set(lv, "Input Black", P.gaps); AEFX.set(lv, "Input White", Math.min(1, P.gaps + 0.14));
}
gaps.rotation.expression = "Math.sin(time * 2 * Math.PI / " + D + ") * " + P.sweep;   // the slow sweep, exact loop
falloff(occ, "opening", diag * P.opening);                       // only gaps near the source radiate
// 2. the rays: zoom blur from the source (in-scattering), extinction with distance, colour, flicker
var comp = AEFX.comp(name, W, H, P.fps, D);
comp.layers.addSolid([0, 0, 0], "black", W, H, 1);
var rays = comp.layers.add(occ); rays.name = "rays";
for (var i = 0; i < Math.max(1, P.passes); i++) {
  var rb = AEFX.fx(rays, "ADBE Radial Blur");
  AEFX.set(rb, "Amount", P.length); AEFX.set(rb, "Center", [sx, sy]); AEFX.set(rb, "Type", 2);    // 2 = Zoom
}
var gain = AEFX.fx(rays, "ADBE Easy Levels2");                    // the blur spreads the light thin: bring it back up
AEFX.set(gain, "Input White", Math.max(0.05, 1 / P.gain));
var tt = AEFX.fx(rays, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(P.core)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
rays.blendingMode = BlendingMode.ADD;
rays.opacity.expression = "100 * (1 - " + P.flicker + " * (0.6 * (0.5 + 0.5 * Math.sin(2 * Math.PI * time / " + D + " + 0.7))" +
                          " + 0.4 * (0.5 + 0.5 * Math.sin(2 * Math.PI * 3 * time / " + D + " + 2.1))))";
falloff(comp, "extinction", diag * P.falloff);                   // extinction: the light dies with distance
var g = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); g.adjustmentLayer = true;
var gf = AEFX.fx(g, "ADBE Glo2");
gf.property("Glow Threshold").setValue(45); gf.property("Glow Radius").setValue(Math.min(W, H) * 0.03 * P.glow);
gf.property("Glow Intensity").setValue(0.6 * P.glow);
return AEFX.done(comp, '"mode":"additive"');
