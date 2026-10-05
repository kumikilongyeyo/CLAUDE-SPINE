/*TEMPLATE {"name":"smoke_puff","doc":"A realistic puff of smoke with exaggerated physics: it BURSTS (fast expansion that drag brings to a crawl, exponent `burst`), RISES on its own heat, ROLLS as it slows (turbulence grows with time: the toroidal roll of a real puff), is LIT from above (dense top bright, underside shadowed) and ERODES from its thin parts first as it dilutes. Transparent background (mode=\"alpha\"), one-shot. Pair with fx_recipe recipe=puff options={lobes: false} for the flash and ring. Fire colours (light FFF3A0, mid FF7A1C, shadow 3A2018) turn it into an explosion fireball.","params":{"size":384,"duration":1.2,"fps":24,"light":"FAF7F2","mid":"C9C3BC","shadow":"5E5852","start_scale":14,"end_scale":122,"burst":4,"rise":0.2,"scale":120,"contrast":95,"turbulence":34,"erode":0.6,"shade":0.45,"opacity":96,"seed":2}} */
var W = P.size, D = P.duration, name = P.comp || "smoke_puff";
var hi = AEFX.rgb(P.light), mid = AEFX.rgb(P.mid), lo = AEFX.rgb(P.shadow);

// 1. density: a lumpy cumulus silhouette that bursts outward and rises, x billowing noise that scales with it, rolled
//    by turbulence that grows as the cloud slows, eroded as it dilutes
var lum = AEFX.comp(name + "_luma", W, W, P.fps, D);
lum.layers.addSolid([0, 0, 0], "black", W, W, 1);
var blob = AEFX.shape(lum, "blob");
var rnd = AEFX.rng(P.seed + 17);
AEFX.ellipse(blob, W * 0.52, [1, 1, 1], null, 0);
for (var lb = 0; lb < 6; lb++) {
  var ang = lb / 6 * Math.PI * 2 + (rnd() - 0.5) * 0.7, dist = W * (0.17 + 0.07 * rnd()), sz = W * (0.26 + 0.14 * rnd());
  AEFX.ellipse(blob, sz, [1, 1, 1], null, 0);
  var vg = blob.property("ADBE Root Vectors Group");
  vg.property(vg.numProperties).property("ADBE Vector Transform Group").property("ADBE Vector Position").setValue([Math.cos(ang) * dist, Math.sin(ang) * dist]);
}
// burst: v(q) = start + (end - start) * (1 - (1 - q)^burst): a blast that drag brings to a crawl; rise with buoyancy
var sk = [], pk = [], N = 14;
for (var k = 0; k <= N; k++) {
  var q = k / N, e = 1 - Math.pow(1 - q, P.burst), v = P.start_scale + (P.end_scale - P.start_scale) * e;
  sk.push([D * q, [v, v * 0.93]]);
  pk.push([D * q, [W / 2, W / 2 - W * P.rise * (1 - Math.pow(1 - q, 2))]]);
}
AEFX.keys(blob.scale, sk, false);
AEFX.keys(blob.position, pk, false);
AEFX.fx(blob, "ADBE Gaussian Blur 2").property("Blurriness").setValue(W * 0.07);
var noise = lum.layers.addSolid([0, 0, 0], "noise", W, W, 1);
var fn = AEFX.fx(noise, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", 0);
AEFX.set(fn, "Scale", P.scale); AEFX.set(fn, "Complexity", 4); AEFX.set(fn, "Random Seed", P.seed);
var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 220);
var sc = AEFX.find(fn, "Scale"); sc.setValueAtTime(0, P.scale * 0.45); sc.setValueAtTime(D, P.scale * 1.15);   // billows grow, never slide
noise.blendingMode = BlendingMode.MULTIPLY;
var roll = lum.layers.addSolid([1, 1, 1], "roll", W, W, 1); roll.adjustmentLayer = true;
var td = AEFX.fx(roll, "ADBE Turbulent Displace");
var ta = AEFX.find(td, "Amount"); ta.setValueAtTime(0, 2); ta.setValueAtTime(D * 0.45, P.turbulence); ta.setValueAtTime(D, P.turbulence * 1.35);
AEFX.set(td, "Size", W * 0.22); AEFX.set(td, "Complexity", 3);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 220);
var er = lum.layers.addSolid([1, 1, 1], "erode", W, W, 1); er.adjustmentLayer = true;
var lv = AEFX.fx(er, "ADBE Easy Levels2");
AEFX.set(lv, "Input Black", 0.04); AEFX.set(lv, "Input White", 0.66);
// erosion: Easy Levels cannot be keyframed on AE 2026, so the noise darkens over time and the fixed levels eat the thin
// parts first, which is how a diluting puff really thins out
var br = AEFX.find(fn, "Brightness");
br.setValueAtTime(0, 16); br.setValueAtTime(D * 0.35, 6); br.setValueAtTime(D, -100 * P.erode);

// 2. shading: the same density lit from above (top bright, underside dark)
var shade = AEFX.comp(name + "_shade", W, W, P.fps, D);
shade.layers.add(lum);
var light = shade.layers.addSolid([1, 1, 1], "light", W, W, 1);
var lr = AEFX.fx(light, "ADBE Ramp");
AEFX.set(lr, "ADBE Ramp-0001", [W / 2, W * 0.12]); AEFX.set(lr, "ADBE Ramp-0002", [1, 1, 1, 1]);
AEFX.set(lr, "ADBE Ramp-0003", [W / 2, W * 0.92]); AEFX.set(lr, "ADBE Ramp-0004", [1 - P.shade, 1 - P.shade, 1 - P.shade, 1]);
light.blendingMode = BlendingMode.MULTIPLY;

// 3. colour from the shaded density, alpha from the raw density
var comp = AEFX.comp(name, W, W, P.fps, D);
var matte = comp.layers.add(lum); matte.name = "alpha_from_density";
var col = comp.layers.add(shade); col.name = "colour"; col.moveAfter(matte);
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", hi); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", lo);
col.setTrackMatte(matte, TrackMatteType.LUMA);
matte.enabled = false;
col.opacity.setValue(P.opacity);
return AEFX.done(comp);
