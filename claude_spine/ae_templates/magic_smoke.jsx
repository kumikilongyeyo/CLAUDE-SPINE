/*TEMPLATE {"name":"magic_smoke","doc":"Magical smoke rising from a source and curling: ribbons of swirling smoke (swirly fractal noise streaming up at `rise` px/s) laced with thin glowing threads (faster), torn into curls by a two-scale turbulent displacement and rocked by a convection twirl, dense near the source and thinning to nothing as it climbs, with motes drifting up inside it. Built in grey and coloured once. luminous=true (default): glowing magic smoke, black -> color -> light, additive on black (mode=\"additive\"). luminous=false: see-through smoke, alpha = density, colour = a two-colour tint shadow -> light (mode=\"alpha\"). Both are two-tone: import with tintable=True and one frame set plays in any colour. Loops exactly (rendered twice as long and crossfaded).","params":{"width":448,"height":640,"duration":2.5,"fps":24,"luminous":true,"color":"7A2CFF","light":"F2E6FF","shadow":"2A0A60","rise":85,"scale":150,"threads":0.8,"curl":70,"fine_curl":28,"swirl":22,"spread":0.3,"height_fade":0.95,"density":1.0,"glow":0.9,"motes":16,"seed":5}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "magic_smoke";
var DD = 2 * D, base = [W / 2, H * 0.92];
var src = AEFX.comp(name + "_src", W, H, P.fps, DD);
src.layers.addSolid([0, 0, 0], "black", W, H, 1);
function noise(nm, type, sw, sh, contrast, bright, riseK, op, seedK) {
  var n = src.layers.addSolid([0, 0, 0], nm, W, H, 1);
  var fn = AEFX.fx(n, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", type); AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", contrast); AEFX.set(fn, "Brightness", bright);
  AEFX.set(fn, "Uniform Scaling", 0); AEFX.set(fn, "Scale Width", sw); AEFX.set(fn, "Scale Height", sh);
  AEFX.set(fn, "Complexity", 5); AEFX.set(fn, "Random Seed", P.seed + seedK);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(DD, 360 * DD / D);
  AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] - time * " + (P.rise * riseK) + "]";   // rises
  if (op < 100) { n.blendingMode = BlendingMode.SCREEN; n.opacity.setValue(op); }
  return n;
}
noise("ribbons", 13, P.scale * 0.7, P.scale * 1.6, 150, -32, 1.0, 100, 0);          // Swirly, stretched upward
noise("threads", 20, P.scale * 0.6, P.scale * 1.2, 180, -24, 1.6, 100 * P.threads, 9);   // Threads: fine glowing strands
// the plume: dense at the source, a soft column, thinning to nothing as it climbs and fading in above the source
// (a tall ellipse sitting ON the source was tried: with the linear top and bottom fades it reads as a box)
var col = src.layers.addSolid([1, 1, 1], "plume", W, H, 1);
var cr = AEFX.fx(col, "ADBE Ramp");
AEFX.set(cr, "ADBE Ramp-0001", base); AEFX.set(cr, "ADBE Ramp-0002", [1, 1, 1, 1]);
AEFX.set(cr, "ADBE Ramp-0003", [base[0] + W * P.spread, base[1]]); AEFX.set(cr, "ADBE Ramp-0004", [0, 0, 0, 1]);
AEFX.set(cr, "ADBE Ramp-0005", 2);
col.property("ADBE Transform Group").property("ADBE Anchor Point").setValue(base);
col.position.setValue(base); col.scale.setValue([100, 300]);
col.blendingMode = BlendingMode.MULTIPLY;
var hf = src.layers.addSolid([1, 1, 1], "height", W, H, 1);
var hr = AEFX.fx(hf, "ADBE Ramp");
AEFX.set(hr, "ADBE Ramp-0001", [W / 2, H * (1 - P.height_fade)]); AEFX.set(hr, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(hr, "ADBE Ramp-0003", [W / 2, H * 0.55]); AEFX.set(hr, "ADBE Ramp-0004", [1, 1, 1, 1]);
hf.blendingMode = BlendingMode.MULTIPLY;
var sf = src.layers.addSolid([1, 1, 1], "source", W, H, 1);
var sr = AEFX.fx(sf, "ADBE Ramp");
AEFX.set(sr, "ADBE Ramp-0001", [W / 2, H * 0.99]); AEFX.set(sr, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(sr, "ADBE Ramp-0003", [W / 2, H * 0.8]); AEFX.set(sr, "ADBE Ramp-0004", [1, 1, 1, 1]);
sf.blendingMode = BlendingMode.MULTIPLY;
// curls at two scales AFTER the plume mask, so the silhouette itself tears into curls instead of staying a blob
function curl(nm, amount, size, seedK) {
  var cu = src.layers.addSolid([1, 1, 1], nm, W, H, 1); cu.adjustmentLayer = true;
  var td = AEFX.fx(cu, "ADBE Turbulent Displace");
  AEFX.set(td, "Displacement", 7);                                   // Twist Smoother: curls, not jitter
  AEFX.set(td, "Amount", amount); AEFX.set(td, "Size", size); AEFX.set(td, "Complexity", 2);
  AEFX.set(td, "Random Seed", P.seed + seedK);
  var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(DD, 360 * DD / D);
}
curl("curl", P.curl, W * 0.3, 1);
curl("fine_curl", P.fine_curl, W * 0.09, 2);
var sw = src.layers.addSolid([1, 1, 1], "swirl", W, H, 1); sw.adjustmentLayer = true;
var twf = AEFX.fx(sw, "ADBE Twirl");
AEFX.set(twf, "ADBE Twirl-0002", 70); AEFX.set(twf, "ADBE Twirl-0003", [W / 2, H * 0.5]);
AEFX.find(twf, "ADBE Twirl-0001").expression = "Math.sin(time * 2 * Math.PI / " + D + ") * " + P.swirl;
var dens = AEFX.loopify(src, name + "_density", D);
var rnd = AEFX.rng(P.seed * 13 + 2);
for (var i = 0; i < P.motes; i++) {                                   // motes drifting up inside (whole cycles per loop)
  var l = AEFX.shape(dens, "mote" + i);
  AEFX.ellipse(l, 3 + 4 * rnd(), [1, 1, 1]);
  AEFX.fx(l, "ADBE Gaussian Blur 2").property("Blurriness").setValue(1.5);
  var ph = rnd(), x0 = W / 2 + (rnd() * 2 - 1) * W * P.spread * 0.6, rise = H * (0.45 + 0.3 * rnd()), tw = 3 + Math.floor(rnd() * 3);
  var head = "var D = " + D + ", ph = " + ph.toFixed(4) + ", t = ((time / D) + ph) % 1; ";
  l.position.expression = head + "[" + x0.toFixed(1) + " + " + (W * 0.05).toFixed(1) + " * Math.sin(2 * Math.PI * (t + ph)), " +
    (H * 0.85).toFixed(1) + " - " + rise.toFixed(1) + " * t]";
  l.opacity.expression = head + "Math.max(0, 100 * Math.sin(Math.PI * t) * (0.5 + 0.5 * Math.sin(2 * Math.PI * (" + tw + " * t + ph))))";
}
var comp = AEFX.comp(name, W, H, P.fps, D);
if (P.luminous) {
  // glowing smoke: brightness is the light; black -> color -> light keeps every frame on one colour line
  var lum = comp.layers.add(dens); lum.name = "colour";
  var lg = AEFX.fx(lum, "ADBE Easy Levels2"); AEFX.set(lg, "Gamma", 0.7);     // Levels gamma < 1 darkens: most of it in the colour, white only in the threads
  var g1 = AEFX.fx(lum, "ADBE Glo2");
  g1.property("Glow Threshold").setValue(45); g1.property("Glow Radius").setValue(W * 0.05 * P.glow); g1.property("Glow Intensity").setValue(0.5 * P.glow);
  var tt = AEFX.fx(lum, "ADBE Tritone");
  AEFX.set(tt, "Highlights", AEFX.rgb(P.light)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
  lum.opacity.setValue(100 * Math.min(1, P.density));
  return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","tintable":true');
}
// see-through smoke: alpha = density on a soft curve, colour = a two-colour tint of the same light
var matte = comp.layers.add(dens); matte.name = "alpha_from_density";
var la = AEFX.fx(matte, "ADBE Easy Levels2"); AEFX.set(la, "Input Black", 0.03); AEFX.set(la, "Input White", 0.85); AEFX.set(la, "Gamma", 0.8);
var c = comp.layers.add(dens); c.name = "colour"; c.moveAfter(matte);
var lc = AEFX.fx(c, "ADBE Easy Levels2"); AEFX.set(lc, "Gamma", 0.65);
var g = AEFX.fx(c, "ADBE Glo2");
g.property("Glow Threshold").setValue(45); g.property("Glow Radius").setValue(W * 0.04 * P.glow); g.property("Glow Intensity").setValue(0.6 * P.glow);
var tn = AEFX.fx(c, "ADBE Tint");
AEFX.set(tn, "ADBE Tint-0001", AEFX.rgb(P.shadow)); AEFX.set(tn, "ADBE Tint-0002", AEFX.rgb(P.light));
c.setTrackMatte(matte, TrackMatteType.LUMA);
matte.enabled = false;
c.opacity.setValue(100 * Math.min(1, P.density));
return AEFX.done(comp, '"mode":"alpha","seq_mode":"loop","tintable":true');
