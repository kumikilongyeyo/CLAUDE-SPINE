/*TEMPLATE {"name":"lens_flare","doc":"An optical lens flare with a GHOST CHAIN (AE's own Lens Flare, no plug-in) that blooms and drifts: the hot source, then a line of coloured ghosts and rings through the comp centre. Ghosts fan out only when the source is OFF centre, so from_x/from_y default to the upper left; in Spine land the source on the blast with ae_fx_to_spine anchor=[from_x, from_y] (plus feather=0.2 so the halo never shows the comp edge) and hit_ae=2/fps (the peak is 2 frames in). lens 1 = 50-300mm zoom (most ghosts), 2 = 35mm prime, 3 = 105mm prime. Properties are set by display name (their indices differ between AE versions). Renders on black: mode=additive.","params":{"size":1024,"duration":0.9,"fps":30,"lens":1,"from_x":0.27,"from_y":0.3,"to_x":0.35,"to_y":0.36,"peak":118,"tint":"FFD6EE","tint_amount":18,"glow":0.6}} */
var S = P.size, D = P.duration, fps = P.fps;
var comp = AEFX.comp(P.comp || "lens_flare", S, S, fps, D);
var s = comp.layers.addSolid([0, 0, 0], "flare", S, S, 1);
var f = AEFX.fx(s, "ADBE Lens Flare");
AEFX.set(f, "Lens Type", P.lens);
AEFX.set(f, "Blend With Original", 0);
AEFX.keys(AEFX.find(f, "Flare Center"), [[0, [S * P.from_x, S * P.from_y]], [D, [S * P.to_x, S * P.to_y]]], false);
AEFX.keys(AEFX.find(f, "Flare Brightness"), [[0, 0], [2 / fps, P.peak], [6 / fps, P.peak * 0.8], [D * 0.55, P.peak * 0.45], [D, 0]], false);
var tint = AEFX.fx(s, "ADBE Tint");
tint.property("Map Black To").setValue([0, 0, 0]); tint.property("Map White To").setValue(AEFX.rgb(P.tint));
tint.property("Amount to Tint").setValue(P.tint_amount);
var g = AEFX.fx(s, "ADBE Glo2");
g.property("Glow Threshold").setValue(50); g.property("Glow Radius").setValue(S * 0.02); g.property("Glow Intensity").setValue(P.glow);
return AEFX.done(comp, '"mode":"additive","anchor":[' + P.from_x + ',' + P.from_y + ']');
