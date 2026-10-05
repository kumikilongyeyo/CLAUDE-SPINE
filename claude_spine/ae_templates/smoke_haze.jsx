/*TEMPLATE {"name":"smoke_haze","doc":"A soft churning haze that fills a box (a glowing cell, a bar, a window): wide billowing noise, tinted, thinning toward the edges and the top. Transparent background (mode=\"alpha\"). Cycles seamlessly so it loops in Spine. Pair with fx_recipe recipe=smoke_glow (base glow) or cell_glow.","params":{"width":192,"height":512,"duration":2.0,"fps":24,"light":"FFD6C8","mid":"C98A7A","shadow":"5A3530","scale":90,"contrast":75,"brightness":28,"turbulence":22,"density":0.95,"edge":0.12,"seed":6}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "smoke_haze";
var hi = AEFX.rgb(P.light), mid = AEFX.rgb(P.mid), lo = AEFX.rgb(P.shadow);
var lum = AEFX.comp(name + "_luma", W, H, P.fps, D);
lum.layers.addSolid([0, 0, 0], "black", W, H, 1);      // without a black base the multiply box shows as a hard rectangle
var noise = lum.layers.addSolid([0, 0, 0], "noise", W, H, 1);
var fn = AEFX.fx(noise, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", P.brightness);
AEFX.set(fn, "Scale", P.scale); AEFX.set(fn, "Complexity", 5); AEFX.set(fn, "Random Seed", P.seed);
var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 360);
AEFX.set(fn, "Cycle Evolution", 1); AEFX.set(fn, "Cycle (in Revolutions)", 1);
// fade at the box edges and toward the top (smoke is denser low down)
var box = lum.layers.addSolid([1, 1, 1], "box", W, H, 1);
var r = AEFX.fx(box, "ADBE Ramp");
AEFX.set(r, "ADBE Ramp-0001", [W / 2, H * 0.05]); AEFX.set(r, "ADBE Ramp-0002", [0.6, 0.6, 0.6, 1]);
AEFX.set(r, "ADBE Ramp-0003", [W / 2, H * 0.95]); AEFX.set(r, "ADBE Ramp-0004", [1, 1, 1, 1]);
var m = noise.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");      // on the noise: a mask on a multiply layer leaves the noise outside it
var sh = new Shape(); var ex = W * P.edge, ey = H * P.edge * 0.4;
sh.vertices = [[ex, ey], [W - ex, ey], [W - ex, H - ey], [ex, H - ey]]; sh.closed = true;
m.property("ADBE Mask Shape").setValue(sh);
m.property("ADBE Mask Feather").setValue([W * 0.18, W * 0.18]);
box.blendingMode = BlendingMode.MULTIPLY;
var roll = lum.layers.addSolid([1, 1, 1], "roll", W, H, 1); roll.adjustmentLayer = true;
var td = AEFX.fx(roll, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.turbulence); AEFX.set(td, "Size", W * 0.4); AEFX.set(td, "Complexity", 3);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 360);
AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1);
var comp = AEFX.comp(name, W, H, P.fps, D);
var matte = comp.layers.add(lum); matte.name = "alpha_from_density";
var col = comp.layers.add(lum); col.name = "colour"; col.moveAfter(matte);
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", hi); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", lo);
col.setTrackMatte(matte, TrackMatteType.LUMA);
matte.enabled = false;
col.opacity.setValue(100 * P.density);
return AEFX.done(comp);
