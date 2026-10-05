/*TEMPLATE {"name":"smoke_puff","doc":"A realistic puff of smoke: a billowing noise cloud bursts out from the centre, rolls and swells, then erodes away from its thin parts (the way real smoke dissipates). Grey-white with soft self-shading. Transparent background (mode=\"alpha\"), one-shot. Clear a symbol, a landing, a reveal. Pair with fx_recipe recipe=puff options={lobes: false} for the flash and ring.","params":{"size":384,"duration":1.2,"fps":24,"light":"F7F4F0","mid":"C9C3BC","shadow":"6F6963","start_scale":18,"end_scale":120,"scale":120,"contrast":95,"turbulence":26,"erode":0.55,"opacity":95,"seed":2}} */
var W = P.size, D = P.duration, name = P.comp || "smoke_puff";
var hi = AEFX.rgb(P.light), mid = AEFX.rgb(P.mid), lo = AEFX.rgb(P.shadow);

// 1. grey smoke shape: a soft disc that grows, multiplied by billowing noise, eroded over time
var lum = AEFX.comp(name + "_luma", W, W, P.fps, D);
lum.layers.addSolid([0, 0, 0], "black", W, W, 1);
var blob = AEFX.shape(lum, "blob");
var rnd = AEFX.rng(P.seed + 17);
// a cumulus silhouette: a core disc plus lobes around it (one layer, so the lobes spread as the layer scales)
AEFX.ellipse(blob, W * 0.52, [1, 1, 1], null, 0);
for (var lb = 0; lb < 6; lb++) {
  var ang = lb / 6 * Math.PI * 2 + (rnd() - 0.5) * 0.7, dist = W * (0.17 + 0.07 * rnd()), sz = W * (0.26 + 0.14 * rnd());
  AEFX.ellipse(blob, sz, [1, 1, 1], null, 0);
  var vg = blob.property("ADBE Root Vectors Group");
  vg.property(vg.numProperties).property("ADBE Vector Transform Group").property("ADBE Vector Position").setValue([Math.cos(ang) * dist, Math.sin(ang) * dist]);
}
blob.position.setValue([W / 2, W / 2]);
// burst fast, then keep spreading slowly (linear keys sampled from an ease-out curve)
var sk = [];
for (var k = 0; k <= 8; k++) { var q = k / 8, e = 1 - Math.pow(1 - q, 3), v = P.start_scale + (P.end_scale - P.start_scale) * e; sk.push([D * q, [v, v * 0.93]]); }
AEFX.keys(blob.scale, sk, false);
AEFX.fx(blob, "ADBE Gaussian Blur 2").property("Blurriness").setValue(W * 0.07);
var noise = lum.layers.addSolid([0, 0, 0], "noise", W, W, 1);
var fn = AEFX.fx(noise, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", 0);
AEFX.set(fn, "Scale", P.scale); AEFX.set(fn, "Complexity", 4); AEFX.set(fn, "Random Seed", P.seed);
var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 200);
// the noise scales up with the cloud so billows grow instead of sliding
var sc = AEFX.find(fn, "Scale"); sc.setValueAtTime(0, P.scale * 0.45); sc.setValueAtTime(D, P.scale * 1.15);
noise.blendingMode = BlendingMode.MULTIPLY;
var roll = lum.layers.addSolid([1, 1, 1], "roll", W, W, 1); roll.adjustmentLayer = true;
var td = AEFX.fx(roll, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.turbulence); AEFX.set(td, "Size", W * 0.22); AEFX.set(td, "Complexity", 3);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 160);
var er = lum.layers.addSolid([1, 1, 1], "erode", W, W, 1); er.adjustmentLayer = true;
var lv = AEFX.fx(er, "ADBE Easy Levels2");
AEFX.set(lv, "Input Black", 0.04); AEFX.set(lv, "Input White", 0.66);
// erosion: Easy Levels cannot be keyframed on AE 2026, so the noise itself darkens over time; the fixed levels then eat
// the thin parts first, which is how real smoke thins out
var br = AEFX.find(fn, "Brightness");
br.setValueAtTime(0, 14); br.setValueAtTime(D * 0.4, 4); br.setValueAtTime(D, -100 * P.erode);

// 2. colour by density (dense = lit, thin = shadowed), alpha from the same density
var comp = AEFX.comp(name, W, W, P.fps, D);
var matte = comp.layers.add(lum); matte.name = "alpha_from_density";
var col = comp.layers.add(lum); col.name = "colour"; col.moveAfter(matte);
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", hi); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", lo);
col.setTrackMatte(matte, TrackMatteType.LUMA);
matte.enabled = false;
col.opacity.setValue(P.opacity);
return AEFX.done(comp);
