/*TEMPLATE {"name":"fire","doc":"A soft painterly column of flame: turbulent noise shaped into tongues, coloured hot-to-cool, with a glow. Torch, burning symbol, power-up. `loop` makes the noise cycle seamlessly (no upward drift) so it can sit in a Spine loop.","params":{"width":384,"height":576,"duration":0.67,"fps":24,"hot":"FFD860","mid":"FF6A10","cool":"D01808","scale":40,"speed":500,"contrast":70,"body":0.5,"taper":1.6,"flame_height":1.25,"threshold":0.2,"softness":0.8,"core":0.6,"turbulence":30,"glow":1.0,"loop":true,"seed":1}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "fire";
var hot = AEFX.rgb(P.hot), mid = AEFX.rgb(P.mid), cool = AEFX.rgb(P.cool);

// 1. grey flame shape: stretched noise + a tall soft body, thresholded so only tongues near the body's edge survive
var lum = AEFX.comp(name + "_luma", W, H, P.fps, D);
var noise = lum.layers.addSolid([0, 0, 0], "noise", W, H, 1);
var fn = AEFX.fx(noise, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1);
AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", P.contrast);
AEFX.set(fn, "Brightness", 0);
AEFX.set(fn, "Uniform Scaling", 0);
AEFX.set(fn, "Scale Width", P.scale);
AEFX.set(fn, "Scale Height", P.scale * 3);       // tall streaks read as tongues of flame
AEFX.set(fn, "Complexity", 4);
AEFX.set(fn, "Random Seed", P.seed);
var ev = AEFX.find(fn, "Evolution");
ev.setValueAtTime(0, 0);
if (P.loop) { AEFX.set(fn, "Cycle Evolution", 1); AEFX.set(fn, "Cycle (in Revolutions)", 1); ev.setValueAtTime(D, 360); }
else { ev.setValueAtTime(D, 360 * 2); AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] + time * " + P.speed + "]"; }
var body = lum.layers.addSolid([1, 1, 1], "body", W, H, 1);
var r = AEFX.fx(body, "ADBE Ramp");
AEFX.set(r, "ADBE Ramp-0001", [W / 2, H * 0.9]); AEFX.set(r, "ADBE Ramp-0002", [1, 1, 1, 1]);
AEFX.set(r, "ADBE Ramp-0003", [W / 2 + W * P.body, H * 0.9]); AEFX.set(r, "ADBE Ramp-0004", [0, 0, 0, 1]); AEFX.set(r, "ADBE Ramp-0005", 2);
body.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([W / 2, H * 0.9]);
body.position.setValue([W / 2, H * 0.9]);
body.scale.setValue([100, 100 * P.taper * 2.2]);          // stretch the round falloff into a tall ellipse
body.blendingMode = BlendingMode.ADD;
body.opacity.setValue(P.core * 100);
var tp = lum.layers.addSolid([1, 1, 1], "height", W, H, 1);       // flames die out towards the top
var rp = AEFX.fx(tp, "ADBE Ramp");
AEFX.set(rp, "ADBE Ramp-0001", [W / 2, H * (1 - P.flame_height)]); AEFX.set(rp, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(rp, "ADBE Ramp-0003", [W / 2, H * 0.9]); AEFX.set(rp, "ADBE Ramp-0004", [1, 1, 1, 1]); AEFX.set(rp, "ADBE Ramp-0005", 1);
tp.blendingMode = BlendingMode.MULTIPLY;
var th = lum.layers.addSolid([1, 1, 1], "threshold", W, H, 1); th.adjustmentLayer = true;
var lv = AEFX.fx(th, "ADBE Easy Levels2");
AEFX.set(lv, "Input Black", P.threshold); AEFX.set(lv, "Input White", P.threshold + P.softness);
var shake = lum.layers.addSolid([1, 1, 1], "shake", W, H, 1); shake.adjustmentLayer = true;
var td = AEFX.fx(shake, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.turbulence); AEFX.set(td, "Size", W * 0.2);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 360);
if (P.loop) { AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1); }

// 2. colour it by brightness, and use the same brightness as its alpha
var comp = AEFX.comp(name, W, H, P.fps, D);
var glow = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); glow.adjustmentLayer = true;
var gf = AEFX.fx(glow, "ADBE Glo2");
gf.property("Glow Threshold").setValue(35); gf.property("Glow Radius").setValue(W * 0.09 * P.glow); gf.property("Glow Intensity").setValue(0.8 * P.glow);
var matte = comp.layers.add(lum); matte.name = "alpha_from_brightness";
var col = comp.layers.add(lum); col.name = "colour";
col.moveAfter(matte);
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", hot); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", cool);
col.setTrackMatte(matte, TrackMatteType.LUMA);
return AEFX.done(comp);
