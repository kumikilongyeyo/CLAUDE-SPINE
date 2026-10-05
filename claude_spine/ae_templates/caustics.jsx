/*TEMPLATE {"name":"caustics","doc":"Shimmering underwater light (caustics): a net of bright wavy lines that drifts and breathes, tinted water-cyan, on black for an additive layer (mode=\"additive\"). Cycles seamlessly so it loops in Spine. Pool / underwater backgrounds, a water symbol, a sea-themed frame (put it behind the art, or clipped to a cell). Pair with fx_recipe recipe=bubbles.","params":{"width":384,"height":384,"duration":2.0,"fps":24,"pattern":1,"size":38,"contrast":160,"disperse":0.85,"warp":14,"threshold":0.38,"light":"F2FFFF","mid":"5FD8F0","shadow":"000000","glow":1.0,"soft_edges":0.12,"seed":3}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "caustics";
var comp = AEFX.comp(name, W, H, P.fps, D);
var net = comp.layers.addSolid([0, 0, 0], "net", W, H, 1);
var cp = AEFX.fx(net, "ADBE Cell Pattern");
AEFX.set(cp, "Cell Pattern", P.pattern);
AEFX.set(cp, "Invert", 1);
AEFX.set(cp, "ADBE Cell Pattern-0003", P.contrast);     // "Contrast" (shown as "Contextual Slider" on AE 2026)
AEFX.set(cp, "Disperse", P.disperse);
AEFX.set(cp, "Size", P.size);
AEFX.set(cp, "Random Seed", P.seed);
var ev = AEFX.find(cp, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 360);
AEFX.set(cp, "Cycle Evolution", 1); AEFX.set(cp, "Cycle (in Revolutions)", 1);
var lvl = AEFX.fx(net, "ADBE Easy Levels2");                  // keep only the cores of the cell edges: thin bright lines
AEFX.set(lvl, "Input Black", P.threshold); AEFX.set(lvl, "Input White", 1.0);
var td = AEFX.fx(net, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.warp); AEFX.set(td, "Size", Math.min(W, H) * 0.25); AEFX.set(td, "Complexity", 2);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 360);
AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1);
var tt = AEFX.fx(net, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(P.light)); AEFX.set(tt, "Midtones", AEFX.rgb(P.mid)); AEFX.set(tt, "Shadows", AEFX.rgb(P.shadow));
if (P.soft_edges > 0) {                       // fade toward the comp border so it can sit in any box
  var m = net.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var sh = new Shape(), ex = W * P.soft_edges, ey = H * P.soft_edges;
  sh.vertices = [[ex, ey], [W - ex, ey], [W - ex, H - ey], [ex, H - ey]]; sh.closed = true;
  m.property("ADBE Mask Shape").setValue(sh);
  m.property("ADBE Mask Feather").setValue([ex * 1.8, ey * 1.8]);
}
var glow = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); glow.adjustmentLayer = true;
var g1 = AEFX.fx(glow, "ADBE Glo2");
g1.property("Glow Threshold").setValue(55); g1.property("Glow Radius").setValue(Math.min(W, H) * 0.02 * P.glow); g1.property("Glow Intensity").setValue(0.8 * P.glow);
return AEFX.done(comp);
