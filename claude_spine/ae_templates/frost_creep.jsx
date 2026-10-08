/*TEMPLATE {"name":"frost_creep","doc":"Realistic hoarfrost creeping over a ROUND surface (a coin or medallion face) from its edge and freezing it solid. A frost DENSITY precomp (a mottled frosted film + sharp inverted Turbulent-Sharp crystal veins + fine veins + ice grain, ADD-stacked, plus a radial 'rim density' so frost is thickest at the rim) becomes alpha by luminance (Shift Channels, Take Alpha From = Luminance) and is filled with `color`, so thin frost stays see-through and the face shows under it. A growth matte (Gradient Wipe over a hidden map precomp: a ramp from the start edge + two noises for a ragged front) reveals it, slowing as it spreads (ease-out), with a soft glinting line riding the advancing front. Everything is circle-masked to the face. Transparent: mode=\"alpha\", one-shot (the last frame is the frozen face: hold it). radius: the face radius as a fraction of size (the defaults are a 560 px comp over a 524 px face). grow: [start, end] of the growth in seconds. from: bottom | top | left | right | rim (rim = inward from the whole edge). density: frosted-film strength, veins / grain: crystal-vein and grain strength, front: glint opacity (0 = none); all 1 = the tuned look. seed shifts every noise. In Spine: make the comp size equal the face size so 1 comp px = 1 unit (or set scale), parent the sequence to the FACE bone (it narrows with the coin's spin), clip it to the face disc, and put a mirrored twin (scaleX -1) on the back face.","params":{"size":560,"radius":0.4678571429,"duration":1.8,"fps":30,"grow":[0.05,1.5],"from":"bottom","color":"E2F2FF","density":1.0,"veins":1.0,"grain":1.0,"front":1.0,"seed":0}} */
var W = P.size, H = P.size, D = P.duration, F = P.fps, k = W / 560, name = P.comp || "frost_creep";
var R = W * P.radius, G0 = P.grow[0], G1 = P.grow[1], LUMA = 5;      // Shift Channels: 5 = Luminance
if (!(G1 > G0)) throw new Error("frost_creep: grow must be [start, end] with end > start");

function solidFx(comp, nm, fx) { var L = comp.layers.addSolid([0, 0, 0], nm, W, H, 1, D); return [L, AEFX.fx(L, fx)]; }
function circleMask(layer, r, feather) {
  var m = layer.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var s = new Shape(), cx = W / 2, cy = H / 2, t = 0.5523 * r;
  s.vertices = [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]];
  s.inTangents = [[-t, 0], [0, -t], [t, 0], [0, t]];
  s.outTangents = [[t, 0], [0, t], [-t, 0], [0, -t]];
  s.closed = true;
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([feather, feather]);
}
// Transition Completion 1 (nothing frozen) -> 0 (all frozen) over the growth window, slowing as it spreads
function growKeys(gw) {
  var tc = AEFX.find(gw, "Transition Completion");
  if (G0 > 0) tc.setValuesAtTimes([0, G0, G1], [1, 1, 0]); else tc.setValuesAtTimes([0, G1], [1, 0]);
  var n = tc.numKeys;
  if (n === 3) tc.setTemporalEaseAtKey(2, [new KeyframeEase(0, 10)], [new KeyframeEase(0, 10)]);
  tc.setTemporalEaseAtKey(n, [new KeyframeEase(0, 75)], [new KeyframeEase(0, 75)]);
}

// 01_SOURCE: the growth map (dark = freezes first): a ramp from the start edge + two noises for a ragged front
var M = AEFX.comp(name + "_map", W, H, F, D);
var rp = solidFx(M, "ramp", "ADBE Ramp")[1];
var ends = {bottom: [[W / 2, H], [W / 2, 0]], top: [[W / 2, 0], [W / 2, H]], left: [[0, H / 2], [W, H / 2]],
            right: [[W, H / 2], [0, H / 2]]};
if (P.from === "rim") {            // radial: white centre, black at the rim, so the whole edge freezes first
  AEFX.set(rp, "ADBE Ramp-0005", 2);
  AEFX.set(rp, "ADBE Ramp-0001", [W / 2, H / 2]); AEFX.set(rp, "ADBE Ramp-0002", [1, 1, 1, 1]);
  AEFX.set(rp, "ADBE Ramp-0003", [W / 2, H / 2 - R]); AEFX.set(rp, "ADBE Ramp-0004", [0, 0, 0, 1]);
} else {
  var e = ends[P.from];
  if (!e) throw new Error("frost_creep: from must be bottom, top, left, right or rim, not " + P.from);
  AEFX.set(rp, "ADBE Ramp-0001", e[0]); AEFX.set(rp, "ADBE Ramp-0002", [0, 0, 0, 1]);
  AEFX.set(rp, "ADBE Ramp-0003", e[1]); AEFX.set(rp, "ADBE Ramp-0004", [1, 1, 1, 1]);
}
var nb = solidFx(M, "noise_big", "ADBE Fractal Noise");
AEFX.set(nb[1], "Contrast", 120); AEFX.set(nb[1], "Scale", 70 * k); AEFX.set(nb[1], "Complexity", 5);
AEFX.set(nb[1], "Random Seed", 11 + P.seed);
nb[0].blendingMode = BlendingMode.OVERLAY; nb[0].opacity.setValue(70);
var nf = solidFx(M, "noise_fine", "ADBE Fractal Noise");
AEFX.set(nf[1], "Fractal Type", 1); AEFX.set(nf[1], "Contrast", 140); AEFX.set(nf[1], "Scale", 22 * k);
AEFX.set(nf[1], "Complexity", 4); AEFX.set(nf[1], "Random Seed", 23 + P.seed);
nf[0].blendingMode = BlendingMode.OVERLAY; nf[0].opacity.setValue(30);

// 02_CORE: frost DENSITY on black (white = thick frost); the shot turns it into alpha, so the face shows through thin frost
var T = AEFX.comp(name + "_ice", W, H, F, D);
function noiseLayer(nm, type, invert, contrast, bright, scale, cx, seed, inB, inW, outW, blend, op) {
  var a = solidFx(T, nm, "ADBE Fractal Noise"), f = a[1];
  AEFX.set(f, "Fractal Type", type); AEFX.set(f, "Invert", invert); AEFX.set(f, "Contrast", contrast);
  AEFX.set(f, "Brightness", bright); AEFX.set(f, "Scale", scale * k); AEFX.set(f, "Complexity", cx);
  AEFX.set(f, "Random Seed", seed + P.seed);
  var lv = AEFX.fx(a[0], "ADBE Easy Levels2");
  AEFX.set(lv, "Input Black", inB); AEFX.set(lv, "Input White", inW); AEFX.set(lv, "Output White", Math.min(1, outW));
  a[0].blendingMode = blend;
  a[0].opacity.setValue(Math.max(0, Math.min(100, op)));
  return a[0];
}
noiseLayer("film", 1, 0, 90, -10, 42, 7, 4, 0.05, 0.85, 0.8 * P.density, BlendingMode.NORMAL, 100);   // frosted film
// frost is thickest at the rim, where it starts and where the metal is coldest
var rim = solidFx(T, "rim_density", "ADBE Ramp"), rr = rim[1];
AEFX.set(rr, "ADBE Ramp-0005", 2); AEFX.set(rr, "ADBE Ramp-0001", [W / 2, H / 2]); AEFX.set(rr, "ADBE Ramp-0002", [0, 0, 0, 1]);
AEFX.set(rr, "ADBE Ramp-0003", [W / 2, H / 2 - (R + 6 * k)]); AEFX.set(rr, "ADBE Ramp-0004", [1, 1, 1, 1]);
var rl = AEFX.fx(rim[0], "ADBE Easy Levels2"); AEFX.set(rl, "Input Black", 0.45); AEFX.set(rl, "Gamma", 0.7);
rim[0].blendingMode = BlendingMode.ADD; rim[0].opacity.setValue(70);
noiseLayer("veins", 4, 1, 170, -20, 60, 8, 31, 0.5, 0.9, 1.0, BlendingMode.ADD, 100 * P.veins);       // hoarfrost veins
noiseLayer("veins_fine", 4, 1, 150, -25, 22, 6, 57, 0.6, 0.95, 0.8, BlendingMode.ADD, 80 * P.veins);
noiseLayer("grain", 1, 0, 300, -60, 5, 2, 8, 0.6, 0.8, 0.7, BlendingMode.ADD, 60 * P.grain);          // ice grain

// the shot: map (hidden) -> growth matte (Gradient Wipe) -> ice through the matte, a glinting growth front
var comp = AEFX.comp(name, W, H, F, D);
var mapL = comp.layers.add(M); mapL.name = "01_SOURCE_map"; mapL.enabled = false;
var ice = comp.layers.add(T); ice.name = "02_CORE_ice";
AEFX.set(AEFX.fx(ice, "ADBE Shift Channels"), "Take Alpha From", LUMA);
AEFX.set(AEFX.fx(ice, "ADBE Fill"), "Color", AEFX.rgb(P.color));

var matte = comp.layers.addSolid([1, 1, 1], "02_CORE_growth_matte", W, H, 1, D);
var gw = AEFX.fx(matte, "ADBE Gradient Wipe");
AEFX.set(gw, "Gradient Layer", mapL.index);
AEFX.set(gw, "Transition Softness", 0.07);            // 0..1, not percent (so is Transition Completion)
AEFX.set(gw, "Invert Gradient", 1);
growKeys(gw);
matte.moveBefore(ice);
ice.setTrackMatte(matte, TrackMatteType.ALPHA);
var masked = [ice, matte];

// 05_LIGHTING: glints along the advancing front: the edges of a duplicated, tighter wipe. Its alpha comes from its
// luminance too, or it exports as an opaque BLACK plate.
if (P.front > 0) {
  var front = comp.layers.addSolid([1, 1, 1], "05_LIGHTING_front", W, H, 1, D);
  var gw2 = AEFX.fx(front, "ADBE Gradient Wipe");
  AEFX.set(gw2, "Gradient Layer", mapL.index); AEFX.set(gw2, "Transition Softness", 0.02);
  AEFX.set(gw2, "Invert Gradient", 1);
  growKeys(gw2);
  AEFX.fx(front, "ADBE Find Edges");
  AEFX.fx(front, "ADBE Invert");
  AEFX.set(AEFX.fx(front, "ADBE Gaussian Blur 2"), "Blurriness", 7 * k);
  AEFX.set(AEFX.fx(front, "ADBE Easy Levels2"), "Input White", 0.45);
  var ftn = AEFX.fx(front, "ADBE Tint");
  AEFX.set(ftn, "Map Black To", [0, 0, 0]); AEFX.set(ftn, "Map White To", AEFX.rgb("E8F8FF"));
  AEFX.set(AEFX.fx(front, "ADBE Shift Channels"), "Take Alpha From", LUMA);
  var fo = Math.min(100, P.front * 55);
  var t1 = Math.min(0.15, G1 / 2), t2 = Math.max(G1 - 0.1, t1 + 0.01);
  AEFX.keys(front.opacity, [[0, 0], [t1, fo], [t2, fo * 40 / 55], [t2 + 0.25, 0]], false);
  masked.push(front);
}
// 07_FINISH: everything inside the face disc (the face centre is the comp centre)
for (var i = 0; i < masked.length; i++) circleMask(masked[i], R, 3 * k);
return AEFX.done(comp, '"mode":"alpha","seq_mode":"once","face_radius":' + R);
