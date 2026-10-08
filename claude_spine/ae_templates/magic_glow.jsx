/*TEMPLATE {"name":"magic_glow","doc":"A magical aura: a breathing glow (soft halo, body, white-hot core) with wisps of energy flowing OUT of it (fractal noise streaming outward, wrapped round the centre with Polar Coordinates, swirling back and forth) and motes of light rising and twinkling round it. Built entirely in grey and coloured once at the end (black -> color -> core), so the render is two-tone: import it with tintable=True and one frame set plays in any colour. Additive on black (mode=\"additive\"); loops exactly (the energy is rendered twice as long and crossfaded, motes and breathing run on whole cycles).","params":{"size":512,"duration":2.0,"fps":24,"color":"8A3CFF","core":"FFFFFF","radius":0.3,"energy":1.0,"flow":110,"swirl":25,"breathe":0.18,"motes":26,"mote_size":5,"glow":1.0,"seed":3}} */
var S = P.size, D = P.duration, name = P.comp || "magic_glow", C = S / 2, R = S * P.radius;
var DD = 2 * D;
// 1. energy wisps on a strip: x = angle round the centre, y = distance from it (top row = centre). The noise
//    streams DOWN the strip (= outward) and is stretched along y, so it reads as wisps leaving the aura.
var src = AEFX.comp(name + "_wisp_src", 1024, 256, P.fps, DD);
src.layers.addSolid([0, 0, 0], "black", 1024, 256, 1);
function wisp(nm, sx, sy, speed, op, seedK) {
  var n = src.layers.addSolid([0, 0, 0], nm, 1024, 256, 1);
  var fn = AEFX.fx(n, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 9);                 // Dynamic Twist: curling filaments
  AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", 190); AEFX.set(fn, "Brightness", -46);
  AEFX.set(fn, "Uniform Scaling", 0); AEFX.set(fn, "Scale Width", sx); AEFX.set(fn, "Scale Height", sy);
  AEFX.set(fn, "Complexity", 4); AEFX.set(fn, "Random Seed", P.seed + seedK);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(DD, 360 * DD / D);
  AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] + time * " + speed + "]";
  if (op < 100) { n.blendingMode = BlendingMode.SCREEN; n.opacity.setValue(op); }
  return n;
}
wisp("wisp_big", 70, 150, P.flow, 100, 0);
wisp("wisp_fine", 30, 90, P.flow * 1.6, 55, 7);
var band = src.layers.addSolid([1, 1, 1], "band", 1024, 256, 1);  // strongest just outside the aura, gone at the rim
var br = AEFX.fx(band, "ADBE Ramp");
AEFX.set(br, "ADBE Ramp-0001", [512, 256 * 0.55]); AEFX.set(br, "ADBE Ramp-0002", [1, 1, 1, 1]);
AEFX.set(br, "ADBE Ramp-0003", [512, 256]); AEFX.set(br, "ADBE Ramp-0004", [0, 0, 0, 1]);
band.blendingMode = BlendingMode.MULTIPLY;
var inner = src.layers.addSolid([1, 1, 1], "inner", 1024, 256, 1);
var ir = AEFX.fx(inner, "ADBE Ramp");
AEFX.set(ir, "ADBE Ramp-0001", [512, 256 * 0.18]); AEFX.set(ir, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(ir, "ADBE Ramp-0003", [512, 256 * 0.5]); AEFX.set(ir, "ADBE Ramp-0004", [1, 1, 1, 1]);
inner.blendingMode = BlendingMode.MULTIPLY;
var strip = AEFX.loopify(src, name + "_wisp", D);
// mirror side by side so the wrap has no seam, squeeze into a square, wrap round the centre
var M = AEFX.comp(name + "_mirror", 2048, 256, P.fps, D);
var ma = M.layers.add(strip); ma.position.setValue([512, 128]);
var mb = M.layers.add(strip); mb.scale.setValue([-100, 100]); mb.position.setValue([1536, 128]);
var Q = AEFX.comp(name + "_square", S, S, P.fps, D);
var sq = Q.layers.add(M); sq.scale.setValue([S / 2048 * 100, S / 256 * 100]); sq.position.setValue([C, C]);
// Polar Coordinates works in the layer's OWN pixels, so it goes on the already-squeezed square, one comp up
var PQ = AEFX.comp(name + "_polar", S, S, P.fps, D);
var q = PQ.layers.add(Q);
var pc = AEFX.fx(q, "ADBE Polar Coordinates");
pc.property(1).setValue(1); pc.property(2).setValue(1);          // interpolation 0..1; 1 = Rect to Polar
var tw = AEFX.fx(q, "ADBE Twirl");                                 // the wisps swirl back and forth (exact loop)
AEFX.set(tw, "ADBE Twirl-0002", 50); AEFX.set(tw, "ADBE Twirl-0003", [C, C]);
AEFX.find(tw, "ADBE Twirl-0001").expression = "Math.sin(time * 2 * Math.PI / " + D + ") * " + P.swirl;

// 2. the grey light: breathing glow + energy + motes, bloomed
var G = AEFX.comp(name + "_luma", S, S, P.fps, D);
G.layers.addSolid([0, 0, 0], "black", S, S, 1);
function breathe(nm, rad, op, phase) {
  var g = AEFX.radialGlow(G, nm, [1, 1, 1], C, C, rad, S * 0.03);
  var k = P.breathe;
  g.matte.scale.expression = "var s = 100 * (1 + " + k + " * Math.sin(2 * Math.PI * time / " + D + " + " + phase + ")); [s, s]";
  g.fill.opacity.setValue(op);
  return g;
}
breathe("halo", R * 1.6, 22, 0);
breathe("body", R * 0.9, 36, 0.4);
breathe("core", R * 0.28, 85, 0.8);
var en = G.layers.add(PQ); en.name = "energy"; en.blendingMode = BlendingMode.ADD;
en.opacity.setValue(Math.min(100, 85 * P.energy));
var rnd = AEFX.rng(P.seed * 7 + 1);
for (var i = 0; i < P.motes; i++) {
  var l = AEFX.shape(G, "mote" + i);
  var e = AEFX.ellipse(l, P.mote_size * (0.5 + rnd()), [1, 1, 1]);
  var ph = rnd(), a = rnd() * 2 * Math.PI, r0 = R * (0.6 + 0.7 * rnd()), rise = S * (0.18 + 0.2 * rnd());
  var sway = S * 0.02 * (0.5 + rnd()), tw2 = 3 + Math.floor(rnd() * 4);
  var head = "var D = " + D + ", ph = " + ph.toFixed(4) + ", t = ((time / D) + ph) % 1; ";
  // whole cycles per loop (rise once, twinkle tw2 times), so the loop is exact
  l.position.expression = head + "[" + C + " + Math.cos(" + a.toFixed(4) + ") * " + r0.toFixed(1) + " * (1 + 0.5 * t) + " +
    sway.toFixed(1) + " * Math.sin(2 * Math.PI * (2 * t + ph)), " + C + " + Math.sin(" + a.toFixed(4) + ") * " +
    (r0 * 0.7).toFixed(1) + " - " + rise.toFixed(1) + " * t]";
  l.opacity.expression = head + "Math.max(0, 100 * Math.sin(Math.PI * t) * (0.55 + 0.45 * Math.sin(2 * Math.PI * (" + tw2 + " * t + ph))))";
}
var gl = G.layers.addSolid([1, 1, 1], "bloom", S, S, 1); gl.adjustmentLayer = true;
var gf = AEFX.fx(gl, "ADBE Glo2");
gf.property("Glow Threshold").setValue(55); gf.property("Glow Radius").setValue(S * 0.035 * P.glow);
gf.property("Glow Intensity").setValue(0.5 * P.glow);

// 3. colour once: black -> color -> core. Additive frames then lie on ONE colour line (two-tone, tintable).
var comp = AEFX.comp(name, S, S, P.fps, D);
var col = comp.layers.add(G); col.name = "colour";
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(P.core)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","tintable":true');
