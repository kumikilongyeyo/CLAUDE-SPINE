/*TEMPLATE {"name":"win_aura","doc":"Slot symbol win aura (from a pirate-slot payline win: toxic-green smoke round each winning symbol). A smooth glow blob carries the light; large soft smoke rises through it, a faint edge veil wraps it and a hot core sits behind the subject. Three comps for Spine: <comp>_in (the flare: the aura licks in, bursts up toward the core colour, settles; ends exactly on loop frame 0), <comp>_loop (an exact loop: drifting smoke crossfaded with AEFX.loopify) and <comp>_out (starts on loop frame 0, darkens, tears apart and dissolves); <comp> itself is the preview in -> loop -> out. Colour is three params: color (body), edge (outer veil), core (hot centre, flare); leave edge/core empty to derive them from color, so ONE param recolours it. art = the subject PNG (optional): its silhouette, blurred, becomes the glow that hugs the shape and the flare flash; without art the core is an ellipse. Draw the import BEHIND the symbol and play it additive (mode=\"additive\"); scale = the subject's size in the comp (the default 640 comp fits a ~300 x 390 px symbol).","params":{"size":640,"duration":1.2,"intro":0.45,"outro":0.55,"fps":30,"color":"4ED82A","edge":"4FE0B0","core":"D8FF4A","radius":0.24,"aspect":1.2,"rise":200,"smoke":1.0,"flare":1.0,"art":"","art_scale":1.0,"glow":1.0,"seed":11}} */
var S = P.size, L = P.duration, TI = P.intro, TO = P.outro, name = P.comp || "win_aura";
var C = S / 2, RX = S * P.radius, RY = RX * P.aspect;
function mix(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]; }
function mul(a, k) { return [Math.min(1, a[0] * k), Math.min(1, a[1] * k), Math.min(1, a[2] * k)]; }
var WHITE = [1, 1, 1], BLACK = [0, 0, 0];
var GLOW = AEFX.rgb(P.color);
// edge / core default to colours derived from the body, so `color` alone recolours the whole aura
var EDGE = P.edge ? AEFX.rgb(P.edge) : mix(GLOW, WHITE, 0.35);
var CORE = P.core ? AEFX.rgb(P.core) : mix(GLOW, WHITE, 0.4);

// 1. the light, drifting, built 2*L long (loopify crossfades it into an exact L loop). Opaque black base.
var DD = 2 * L;
var src = AEFX.comp(name + "_src", S, S, P.fps, DD);
src.layers.addSolid([0, 0, 0], "black", S, S, 1);
function ellipseMask(layer, rx, ry, feather) {
  var m = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var s = new Shape(), k = 0.5523, cy = C + S * 0.015;
  s.vertices = [[C, cy - ry], [C + rx, cy], [C, cy + ry], [C - rx, cy]];
  s.inTangents = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]];
  s.outTangents = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]];
  s.closed = true;
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([feather, feather]);
}
// base: a smooth blob with NO noise. It carries most of the light (noise alone reads as crunchy veins).
var base = src.layers.addSolid(GLOW, "02_CORE_base", S, S, 1);
ellipseMask(base, RX, RY, RX * 1.1);
base.blendingMode = BlendingMode.ADD; base.opacity.setValue(75);
// smoke: Fractal Noise overwrites the layer's alpha, so the soft shape is a separate matte layer (feathered
// ellipse, torn by Turbulent Displace for wispy edges), never a mask on the noise itself.
var rnd = AEFX.rng(P.seed);
function smoke(nm, rx, ry, feather, scale, hi, mid, rise, bright, op) {
  var s = src.layers.addSolid([0, 0, 0], nm, S, S, 1);
  var fn = AEFX.fx(s, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 4); AEFX.set(fn, "Noise Type", 3);          // Turbulent Soft, Soft Linear
  AEFX.set(fn, "Contrast", 105); AEFX.set(fn, "Brightness", bright);       // >~150 clips to white
  AEFX.set(fn, "Scale", scale); AEFX.set(fn, "Complexity", 3);
  AEFX.set(fn, "Random Seed", Math.floor(rnd() * 1000));
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(DD, 300 * DD);
  AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] - time * " + rise + "]";   // rises
  var tt = AEFX.fx(s, "ADBE Tritone");
  AEFX.set(tt, "Highlights", hi); AEFX.set(tt, "Midtones", mid); AEFX.set(tt, "Shadows", BLACK);
  s.blendingMode = BlendingMode.ADD; s.opacity.setValue(Math.min(100, op));
  var mt = src.layers.addSolid([1, 1, 1], nm + "_matte", S, S, 1);
  ellipseMask(mt, rx, ry, feather);
  var td = AEFX.fx(mt, "ADBE Turbulent Displace");
  AEFX.set(td, "Amount", 60 * S / 640); AEFX.set(td, "Size", 55 * S / 640);
  var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(DD, 260 * DD);
  mt.moveBefore(s);
  s.setTrackMatte(mt, TrackMatteType.ALPHA);
  mt.enabled = false;
  return s;
}
var K = S / 640;
smoke("03_SECONDARY_edge", RX * 1.27, RY * 1.2, RX * 1.4, 210 * K, EDGE, mul(EDGE, 0.45), P.rise * 0.6 * K, -40, 55 * P.smoke);
smoke("02_CORE_body", RX, RY, RX * 1.07, 150 * K, mix(GLOW, CORE, 0.6), mul(GLOW, 0.6), P.rise * 0.9 * K, -38, 100 * P.smoke);
smoke("02_CORE_hot", RX * 0.63, RY * 0.65, RX * 0.73, 110 * K, mix(CORE, WHITE, 0.6), CORE, P.rise * 1.3 * K, -22, 28);
// the glow that hugs the subject: its silhouette, filled and blurred (or an ellipse without art)
var hug = null;
if (P.art) {
  // a blur clips at the layer's own bounds, so the PNG goes into a comp-sized precomp and the blur goes on that
  var silc = AEFX.comp(name + "_silhouette", S, S, P.fps, DD);
  var sil = silc.layers.add(AEFX.imp(P.art));
  sil.scale.setValue([118 * P.art_scale, 118 * P.art_scale]); sil.position.setValue([C, C]);
  hug = src.layers.add(silc);
  AEFX.set(AEFX.fx(hug, "ADBE Fill"), "Color", mix(GLOW, CORE, 0.7));
  var hb = AEFX.fx(hug, "ADBE Box Blur2"); AEFX.set(hb, "Blur Radius", S * 0.06); AEFX.set(hb, "Iterations", 3);
} else {
  hug = src.layers.addSolid(mix(GLOW, CORE, 0.7), "hug", S, S, 1);
  ellipseMask(hug, RX * 0.55, RY * 0.6, RX * 0.6);
}
hug.name = "02_CORE_hug"; hug.blendingMode = BlendingMode.ADD; hug.opacity.setValue(40);
var fin = src.layers.addSolid([1, 1, 1], "07_FINISH_bloom", S, S, 1); fin.adjustmentLayer = true;
var gf = AEFX.fx(fin, "ADBE Glo2");
gf.property("Glow Threshold").setValue(80); gf.property("Glow Radius").setValue(40 * K * P.glow);
gf.property("Glow Intensity").setValue(0.3 * P.glow);

// 2. the loop
var loop = AEFX.loopify(src, name + "_loop", L);

// 3. intro: the loop's LAST TI seconds (so it hands over on loop frame 0), licking in, flaring toward the core
//    colour and stretching upward, then settling. The flare is the same light tinted to the core, added on top.
var cin = AEFX.comp(name + "_in", S, S, P.fps, TI);
function loopLayer(comp, nm, start) {
  var l = comp.layers.add(loop); l.name = nm; l.startTime = start;
  l.anchorPoint.setValue([C, C + RY * 0.9]); l.position.setValue([C, C + RY * 0.9]);   // grows from its base
  return l;
}
var li = loopLayer(cin, "01_SOURCE_aura", TI - L);
var lit = Math.min(0.1, TI * 0.22), pk = Math.min(TI * 0.38, 0.17), st = TI * 0.95;
AEFX.keys(li.opacity, [[0, 0], [lit, 90], [pk, 100]], false);
AEFX.keys(li.scale, [[0, [70, 60]], [pk, [112, 124]], [st, [100, 100]]], true);
var fl = loopLayer(cin, "05_LIGHTING_flare", TI - L);
fl.blendingMode = BlendingMode.ADD;
var ft = AEFX.fx(fl, "ADBE Tint");
AEFX.set(ft, "Map Black To", BLACK); AEFX.set(ft, "Map White To", mix(CORE, WHITE, 0.25));
AEFX.keys(fl.opacity, [[0, 0], [lit, 35 * P.flare], [pk, Math.min(100, 65 * P.flare)], [pk + 0.06, Math.min(100, 52 * P.flare)], [st, 0]], true);
AEFX.keys(fl.scale, [[0, [80, 70]], [pk, [114, 130]], [st, [104, 110]]], true);
if (P.art) {   // the subject flashes with light at the burst (in front of the art: import this layer separately if needed)
  var fa = cin.layers.add(AEFX.imp(P.art)); fa.name = "06_FINISH_art_flash";
  fa.scale.setValue([100 * P.art_scale, 100 * P.art_scale]); fa.position.setValue([C, C]);
  AEFX.set(AEFX.fx(fa, "ADBE Fill"), "Color", mix(CORE, WHITE, 0.4));
  fa.blendingMode = BlendingMode.ADD;
  AEFX.keys(fa.opacity, [[0, 0], [pk, 55 * P.flare], [st, 0]], true);
  fa.enabled = false;          // off by default: the aura renders alone; switch on for an all-in-one preview
}

// 4. outro: from loop frame 0, the light dies first (exposure down), the smoke tears and drifts up, then fades
var cout = AEFX.comp(name + "_out", S, S, P.fps, TO);
var lo = loopLayer(cout, "01_SOURCE_aura", 0);
var ex = AEFX.fx(lo, "ADBE Exposure2");
AEFX.keys(AEFX.find(ex, "Exposure"), [[0, 0], [TO * 0.55, -1.6], [TO, -3]], true);
var dt = AEFX.fx(lo, "ADBE Turbulent Displace");
AEFX.keys(AEFX.find(dt, "Amount"), [[0, 0], [TO, 90 * K]], true); AEFX.set(dt, "Size", 45 * K);
AEFX.keys(lo.opacity, [[0, 100], [TO * 0.45, 85], [TO, 0]], true);
AEFX.keys(lo.scale, [[0, [100, 100]], [TO, [88, 92]]], true);
AEFX.keys(lo.position, [[0, [C, C + RY * 0.9]], [TO, [C, C + RY * 0.9 - S * 0.04]]], true);

// 5. preview: in -> loop -> out
var comp = AEFX.comp(name, S, S, P.fps, TI + L + TO);
var a1 = comp.layers.add(cin); a1.startTime = 0;
var a2 = comp.layers.add(loop); a2.startTime = TI;
var a3 = comp.layers.add(cout); a3.startTime = TI + L;
a1.outPoint = TI; a2.inPoint = TI; a2.outPoint = TI + L; a3.inPoint = TI + L;
return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","comps":{"in":"' + cin.name + '","loop":"' + loop.name +
  '","out":"' + cout.name + '"},"intro":' + TI + ',"loop_s":' + L + ',"outro":' + TO);
