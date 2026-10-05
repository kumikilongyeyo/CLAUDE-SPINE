/*TEMPLATE {"name":"fire","doc":"A column of flame with real (exaggerated) fire physics: hot gas RISES and accelerates (the noise drifts upward at `rise` px/s, stretched into tall tongues), small fast licks ride over the big slow body (turbulence cascade), tongues pinch off toward the top, a white-hot core, and the whole flame flickers at ~11 Hz. `loop` renders twice the duration and crossfades it into a seamless loop that still rises. `alpha_cut` is the hard cut on the alpha (colour keeps a soft curve). `edge_fade` (0..0.5) feathers the sides and base so a narrow tongue never shows the comp border.","params":{"width":384,"height":576,"duration":0.67,"fps":24,"hot":"FFF4C0","mid":"FF7A14","cool":"C02A08","scale":40,"rise":420,"lick":0.5,"flicker":0.35,"speed":500,"contrast":70,"body":0.5,"taper":1.6,"flame_height":1.25,"threshold":0.2,"softness":0.55,"alpha_cut":0.3,"core":0.7,"turbulence":30,"glow":1.0,"loop":true,"seed":1,"edge_fade":0}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "fire";
var hot = AEFX.rgb(P.hot), mid = AEFX.rgb(P.mid), cool = AEFX.rgb(P.cool);
var drifting = P.rise > 0, looped = P.loop && drifting;
var DD = looped ? 2 * D : D;                      // a drifting source runs twice as long and is crossfaded into the loop

// 1. grey flame shape: rising stretched noise (+ fast licks) x a tall soft body x a height falloff, thresholded
var lum = AEFX.comp(name + (looped ? "_src" : "_luma"), W, H, P.fps, DD);
lum.layers.addSolid([0, 0, 0], "black", W, H, 1);
function noiseLayer(nm, scaleK, revs, riseK, opacity, blend) {
  var n = lum.layers.addSolid([0, 0, 0], nm, W, H, 1);
  var fn = AEFX.fx(n, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", 0);
  AEFX.set(fn, "Uniform Scaling", 0);
  AEFX.set(fn, "Scale Width", P.scale * scaleK);
  AEFX.set(fn, "Scale Height", P.scale * scaleK * 3.5);     // tall streaks read as tongues of flame
  AEFX.set(fn, "Complexity", 4); AEFX.set(fn, "Random Seed", P.seed + (nm === "lick" ? 11 : 0));
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0);
  if (drifting) {                                 // hot gas rises: the pattern streams upward (AE y points down)
    ev.setValueAtTime(DD, 360 * revs * DD / D);
    AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] - time * " + (P.rise * riseK) + "]";
  } else if (P.loop) { AEFX.set(fn, "Cycle Evolution", 1); AEFX.set(fn, "Cycle (in Revolutions)", 1); ev.setValueAtTime(D, 360); }
  else { ev.setValueAtTime(D, 720); AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] + time * " + P.speed + "]"; }
  if (blend) n.blendingMode = blend;
  if (opacity < 100) n.opacity.setValue(opacity);
  return n;
}
noiseLayer("noise", 1.0, 1, 1.0, 100, null);
if (P.lick > 0) noiseLayer("lick", 0.45, 2, 1.7, 100 * P.lick, BlendingMode.SCREEN);   // small, fast, rises faster
var body = lum.layers.addSolid([1, 1, 1], "body", W, H, 1);
var r = AEFX.fx(body, "ADBE Ramp");
AEFX.set(r, "ADBE Ramp-0001", [W / 2, H * 0.9]); AEFX.set(r, "ADBE Ramp-0002", [1, 1, 1, 1]);
AEFX.set(r, "ADBE Ramp-0003", [W / 2 + W * P.body, H * 0.9]); AEFX.set(r, "ADBE Ramp-0004", [0, 0, 0, 1]); AEFX.set(r, "ADBE Ramp-0005", 2);
body.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([W / 2, H * 0.9]);
body.position.setValue([W / 2, H * 0.9]);
body.scale.setValue([100, 100 * P.taper * 2.2]);
body.blendingMode = BlendingMode.ADD;
body.opacity.setValue(P.core * 100);
var tp = lum.layers.addSolid([1, 1, 1], "height", W, H, 1);       // flames die out toward the top: tongues pinch off
var rp = AEFX.fx(tp, "ADBE Ramp");
AEFX.set(rp, "ADBE Ramp-0001", [W / 2, H * (1 - P.flame_height)]); AEFX.set(rp, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(rp, "ADBE Ramp-0003", [W / 2, H * 0.9]); AEFX.set(rp, "ADBE Ramp-0004", [1, 1, 1, 1]); AEFX.set(rp, "ADBE Ramp-0005", 1);
tp.blendingMode = BlendingMode.MULTIPLY;
var luma = looped ? AEFX.loopify(lum, name + "_luma", D) : lum;
// threshold and shake go AFTER the loop crossfade: blending two noise fields flattens their contrast, and the
// threshold is what re-cuts the flat blend into sharp tongues
var th = luma.layers.addSolid([1, 1, 1], "threshold", W, H, 1); th.adjustmentLayer = true;
var lv = AEFX.fx(th, "ADBE Easy Levels2");
AEFX.set(lv, "Input Black", P.threshold); AEFX.set(lv, "Input White", P.threshold + P.softness);
var shake = luma.layers.addSolid([1, 1, 1], "shake", W, H, 1); shake.adjustmentLayer = true;
var td = AEFX.fx(shake, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.turbulence); AEFX.set(td, "Size", W * 0.2);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 360);
if (P.loop) { AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1); }

// 2. colour it by brightness (white-hot core), the same brightness is its alpha, flicker
var comp = AEFX.comp(name, W, H, P.fps, D);
var glow = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); glow.adjustmentLayer = true;
var gf = AEFX.fx(glow, "ADBE Glo2");
gf.property("Glow Threshold").setValue(35); gf.property("Glow Radius").setValue(W * 0.09 * P.glow); gf.property("Glow Intensity").setValue(0.8 * P.glow);
var matte = comp.layers.add(luma); matte.name = "alpha_from_brightness";
// the alpha gets a HARD curve and the colour a soft one: thin gas vanishes, what remains is opaque and coloured
// (a soft alpha turns every mid-grey into a dim brown wash over the background)
var la = AEFX.fx(matte, "ADBE Easy Levels2"); AEFX.set(la, "Input Black", P.alpha_cut); AEFX.set(la, "Input White", 0.72);
var col = comp.layers.add(luma); col.name = "colour";
col.moveAfter(matte);
var lc = AEFX.fx(col, "ADBE Easy Levels2"); AEFX.set(lc, "Gamma", 1.3);      // widen the hot zone before colouring
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", hot); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", cool);
col.setTrackMatte(matte, TrackMatteType.LUMA);
if (P.flicker > 0) { col.opacity.setValue(100 - 25 * P.flicker); col.opacity.expression = "wiggle(11, " + (25 * P.flicker) + ")"; }
if (P.edge_fade > 0) {                      // feather the sides and round off the base
  var fm = col.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var fs = new Shape(), ex = W * P.edge_fade;
  fs.vertices = [[ex, -H], [W - ex, -H], [W - ex, H * 0.95], [ex, H * 0.95]]; fs.closed = true;
  fm.property("ADBE Mask Shape").setValue(fs);
  fm.property("ADBE Mask Feather").setValue([ex * 1.6, H * 0.08]);
}
return AEFX.done(comp);
