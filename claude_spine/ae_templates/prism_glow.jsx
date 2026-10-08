/*TEMPLATE {"name":"prism_glow","doc":"A white light glow made to be split into a spectrum in Spine: a breathing core, body and halo, a star of thin tapered rays that twinkle and turn slowly, an anamorphic horizontal streak and a faint lens ring. Rendered WHITE on black (mode=\"additive\"); import it with tintable=True, spectrum=0.05, spectrum_bands=6, spectrum_turn=2: Spine draws the one grey frame set as red / yellow / green / cyan / blue / magenta copies at slightly different sizes and angles, white where they overlap and rainbow fringes at every edge (real dispersion), so the spectrum costs no extra frames and can be any width. Without spectrum it is a plain white glow (tint it like any other). Loops exactly.","params":{"size":512,"duration":2.0,"fps":24,"color":"FFFFFF","rays":6,"ray_length":0.62,"ray_width":2.5,"turn":8,"streak":0.9,"ring":0.34,"breathe":0.12,"glow":1.0,"seed":2}} */
var S = P.size, D = P.duration, name = P.comp || "prism_glow", C = S / 2;
function falloff(c, nm, r, gamma) {          // multiply by a radial ramp: white at the centre, black at r
  var l = c.layers.addSolid([1, 1, 1], nm, S, S, 1);
  var rp = AEFX.fx(l, "ADBE Ramp");
  AEFX.set(rp, "ADBE Ramp-0001", [C, C]); AEFX.set(rp, "ADBE Ramp-0002", [1, 1, 1, 1]);
  AEFX.set(rp, "ADBE Ramp-0003", [C + r, C]); AEFX.set(rp, "ADBE Ramp-0004", [0, 0, 0, 1]); AEFX.set(rp, "ADBE Ramp-0005", 2);
  if (gamma) { var lv = AEFX.fx(l, "ADBE Easy Levels2"); AEFX.set(lv, "Gamma", gamma); }
  l.blendingMode = BlendingMode.MULTIPLY;
  return l;
}
// 1. the star: thin bars through the centre, twinkling on whole cycles, turning on a sine, tapered by a falloff
var rays = AEFX.comp(name + "_rays", S, S, P.fps, D);
rays.layers.addSolid([0, 0, 0], "black", S, S, 1);
var rnd = AEFX.rng(P.seed * 5 + 3);
for (var i = 0; i < P.rays; i++) {
  var isLong = i % 2 === 0;                                   // alternate long and short rays, like a real star filter
  var bar = AEFX.rect(rays, "ray" + i, S * (isLong ? 1.0 : 0.62), P.ray_width * (isLong ? 1 : 0.7), [1, 1, 1]);
  bar.position.setValue([C, C]);
  var a0 = 180 * i / P.rays, ph = rnd(), k = 1 + Math.floor(rnd() * 3);
  bar.rotation.expression = a0 + " + Math.sin(time * 2 * Math.PI / " + D + ") * " + P.turn;
  bar.opacity.expression = "100 * (0.7 + 0.3 * Math.sin(2 * Math.PI * (" + k + " * time / " + D + " + " + ph.toFixed(3) + ")))";
  var bl = AEFX.fx(bar, "ADBE Gaussian Blur 2"); bl.property("Blurriness").setValue(P.ray_width * 0.8);
}
falloff(rays, "taper", S * P.ray_length, 1.5);
// 2. the anamorphic streak: a long horizontal bar blurred sideways, brightest at the centre
var stk = AEFX.comp(name + "_streak", S, S, P.fps, D);
stk.layers.addSolid([0, 0, 0], "black", S, S, 1);
var sb = AEFX.rect(stk, "streak", S * 1.2, P.ray_width * 2, [1, 1, 1]); sb.position.setValue([C, C]);
var sbl = AEFX.fx(sb, "ADBE Gaussian Blur 2"); sbl.property("Blurriness").setValue(S * 0.06);
AEFX.set(sbl, "Blur Dimensions", 2);                         // horizontal only
var sbv = AEFX.fx(sb, "ADBE Gaussian Blur 2"); sbv.property("Blurriness").setValue(P.ray_width);
falloff(stk, "taper", S * 0.5, 0.7);
// 3. the grey light
var G = AEFX.comp(name + "_luma", S, S, P.fps, D);
G.layers.addSolid([0, 0, 0], "black", S, S, 1);
function breathe(nm, rad, op, phase) {
  var g = AEFX.radialGlow(G, nm, [1, 1, 1], C, C, rad, S * 0.02);
  g.matte.scale.expression = "var s = 100 * (1 + " + P.breathe + " * Math.sin(2 * Math.PI * time / " + D + " + " + phase + ")); [s, s]";
  g.fill.opacity.setValue(op);
}
breathe("halo", S * 0.4, 18, 0);
breathe("body", S * 0.15, 34, 0.5);
breathe("core", S * 0.045, 100, 1.0);
var rl = G.layers.add(rays); rl.blendingMode = BlendingMode.ADD;
var sl = G.layers.add(stk); sl.blendingMode = BlendingMode.ADD; sl.opacity.setValue(100 * Math.min(1, P.streak));
if (P.ring > 0) {                                            // a faint lens ring
  var rg = AEFX.shape(G, "ring");
  AEFX.ellipse(rg, S * P.ring * 2, null, [1, 1, 1], 1.5);
  rg.position.setValue([C, C]); rg.opacity.setValue(10);
  AEFX.fx(rg, "ADBE Gaussian Blur 2").property("Blurriness").setValue(3);
  rg.blendingMode = BlendingMode.ADD;
}
var gl = G.layers.addSolid([1, 1, 1], "bloom", S, S, 1); gl.adjustmentLayer = true;
var gf = AEFX.fx(gl, "ADBE Glo2");
gf.property("Glow Threshold").setValue(60); gf.property("Glow Radius").setValue(S * 0.03 * P.glow);
gf.property("Glow Intensity").setValue(0.6 * P.glow);
var comp = AEFX.comp(name, S, S, P.fps, D);
var col = comp.layers.add(G); col.name = "colour";
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", [1, 1, 1]); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","tintable":true,"spectrum":0.05,"spectrum_bands":6,"spectrum_turn":2');
