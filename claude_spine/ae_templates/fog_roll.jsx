/*TEMPLATE {"name":"fog_roll","doc":"A fog bank or sandstorm rolling SIDEWAYS, with exaggerated convection physics turned on its side (smoke_haze rises; this flows): the noise is advected horizontally at `speed` px/s (Offset Turbulence), a deeper, bigger layer behind moves at 45% of it (parallax), the bank is densest at the ground and thins upward (a vertical density ramp up to `top` of the height), its top edge billows in waves that travel with the flow (turbulent displace whose offset drifts with it, the shear layer at the top of the bank), and sand adds fast fine grit streaking along the ground. Rendered twice the duration and crossfaded (AEFX.loopify), so it loops while really flowing. `kind` picks the preset (fog = cool grey, slow, soft; sand = ochre, fast, streaky); any preset value left at 0 / empty comes from the kind. Transparent background (mode=\"alpha\"). Pair with fx_recipe recipe=fog_roll (its ae_hint gives size, speed and placement).","params":{"width":1024,"height":384,"duration":4.0,"fps":24,"kind":"fog","speed":0,"scale":0,"stretch":0,"grit":-1,"turbulence":0,"light":"","mid":"","shadow":"","contrast":80,"brightness":20,"top":0.85,"density":0.9,"edge":0.04,"seed":8}} */
var K = {
  fog: { speed: 70, scale: 150, stretch: 0.5, grit: 0, turbulence: 36, light: "EEF3F8", mid: "AEB9C6", shadow: "56606E" },
  sand: { speed: 260, scale: 90, stretch: 0.3, grit: 0.4, turbulence: 22, light: "F2D29A", mid: "C8964E", shadow: "6A4524" }
}[P.kind];
if (!K) throw new Error("kind must be fog | sand");
function pick(k) { var v = P[k]; return (v === 0 || v === "" || v === -1 || v === null) ? K[k] : v; }
var W = P.width, H = P.height, D = P.duration, name = P.comp || ("fog_roll_" + P.kind);
var V = pick("speed"), SC = pick("scale"), ST = pick("stretch"), GR = pick("grit"), TB = pick("turbulence");
var DD = 2 * D;
var src = AEFX.comp(name + "_src", W, H, P.fps, DD);
src.layers.addSolid([0, 0, 0], "black", W, H, 1);                   // an opaque luma base for the crossfade
function bank(nm, scaleK, speedK, stretchK, opacity, blend, seedK) {
  var l = src.layers.addSolid([0, 0, 0], nm, W, H, 1);
  var fn = AEFX.fx(l, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", P.brightness);
  AEFX.set(fn, "Uniform Scaling", 0);
  AEFX.set(fn, "Scale Width", SC * scaleK); AEFX.set(fn, "Scale Height", SC * scaleK * stretchK);   // wide, flat billows
  AEFX.set(fn, "Complexity", 5); AEFX.set(fn, "Random Seed", P.seed + seedK);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(DD, 360 * DD / D * 0.5);
  AEFX.find(fn, "Offset Turbulence").expression = "[value[0] + time * " + (V * speedK) + ", value[1]]";   // advection: sideways
  if (blend) l.blendingMode = blend;
  if (opacity < 100) l.opacity.setValue(opacity);
  return l;
}
bank("deep", 1.7, 0.45, ST, 100, null, 3);                          // far layer: bigger, slower (parallax)
bank("near", 1.0, 1.0, ST, 55, BlendingMode.SCREEN, 0);              // near layer: finer, faster
if (GR > 0) bank("grit", 0.16, 2.2, 0.18, 100 * GR, BlendingMode.SCREEN, 9);   // sand: fine fast streaks
// densest at the ground, thinning upward to `top` of the height (stratified bank)
var prof = src.layers.addSolid([1, 1, 1], "profile", W, H, 1);
var r = AEFX.fx(prof, "ADBE Ramp");
AEFX.set(r, "ADBE Ramp-0001", [W / 2, H * (1 - P.top)]); AEFX.set(r, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(r, "ADBE Ramp-0003", [W / 2, H * 0.97]); AEFX.set(r, "ADBE Ramp-0004", [1, 1, 1, 1]); AEFX.set(r, "ADBE Ramp-0005", 1);
prof.blendingMode = BlendingMode.MULTIPLY;
// the billowing top: turbulence that drifts WITH the flow (the shear layer rolls up into travelling waves)
var roll = src.layers.addSolid([1, 1, 1], "roll", W, H, 1); roll.adjustmentLayer = true;
var td = AEFX.fx(roll, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", TB); AEFX.set(td, "Size", H * 0.3); AEFX.set(td, "Complexity", 3);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(DD, 360 * DD / D * 0.5);
var toff = AEFX.find(td, "Offset (Turbulence)");
if (toff) toff.expression = "[value[0] + time * " + (V * 0.8) + ", value[1]]";
if (P.edge > 0) {                                                    // soft left/right ends AFTER the displace (see smoke_haze)
  var e = src.layers.addSolid([0, 0, 0], "ends", W, H, 1);
  var em = e.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var esh = new Shape(), ex = W * P.edge;
  esh.vertices = [[ex, -H], [W - ex, -H], [W - ex, H * 2], [ex, H * 2]]; esh.closed = true;
  em.property("ADBE Mask Shape").setValue(esh);
  em.property("ADBE Mask Feather").setValue([ex * 1.8, 0]);
  em.inverted = true;
}
var lum = AEFX.loopify(src, name + "_luma", D);
var comp = AEFX.comp(name, W, H, P.fps, D);
var matte = comp.layers.add(lum); matte.name = "alpha_from_density";
var col = comp.layers.add(lum); col.name = "colour"; col.moveAfter(matte);
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(pick("light"))); AEFX.set(tt, "Midtones", AEFX.rgb(pick("mid"))); AEFX.set(tt, "Shadows", AEFX.rgb(pick("shadow")));
col.setTrackMatte(matte, TrackMatteType.LUMA);
matte.enabled = false;
col.opacity.setValue(100 * P.density);
return AEFX.done(comp, '"mode":"alpha","kind":"' + P.kind + '"');
