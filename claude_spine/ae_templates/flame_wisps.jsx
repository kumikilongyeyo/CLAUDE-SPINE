/*TEMPLATE {"name":"flame_wisps","doc":"Anamorphic flame wisps flying OUT of a centre to both sides, for a spin-start flare or a lens burst: two fractal-noise fields stretched into thin strands (`strand` px tall, `stretch` x wider) drift outward at `speed` px/s, the left half a mirrored copy of a second seed so the sides differ, torn into curls by a drifting turbulent displace (`curl`, `curl_size`), shaped by a feathered flat ellipse (`spread` of the width, `thick` of the height) as an ALPHA matte on its own layer (Fractal Noise overwrites alpha), flaring in over 3 frames, growing fast then crawling (drag) and fading out, with a soft glow. The noise comps are 1.5x wider than the output so the growth never shows their ends. Coloured once at the end (black -> color -> core); the defaults (808080 / FFFFFF) render it GREY, the intended use: import tintable and play ONE frame set as several tinted copies (the fx_recipe anamorphic_burst plays it as orange, mirrored orange, violet and pink; set color/core to bake one colour instead). Additive on black (mode=\"additive\"), one-shot.","params":{"width":768,"height":192,"duration":0.9,"fps":30,"color":"808080","core":"FFFFFF","seed":11,"speed":380,"strand":16,"stretch":14,"contrast":145,"brightness":-42,"spread":0.6,"thick":0.24,"curl":16,"curl_size":34,"glow":1.0}} */
var W = P.width, H = P.height, D = P.duration, FPS = P.fps, NAME = P.comp || "flame_wisps";
var WW = Math.round(W * 1.5);                       // noise comps are wider than the output, so scaling never shows their ends
// 1) noise drifting to the RIGHT; the left half is a mirrored copy of a SECOND noise (other seed), so the two
//    sides differ like the clip's
function noiseComp(tag, seed) {
var src = AEFX.comp(NAME + "_src" + tag, WW, H, FPS, D);
src.layers.addSolid([0, 0, 0], "black", WW, H, 1);
var nl = src.layers.addSolid([0, 0, 0], "wisp_noise", WW, H, 1);
var fn = AEFX.fx(nl, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1);
AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", P.contrast);
AEFX.set(fn, "Brightness", P.brightness);
AEFX.set(fn, "Uniform Scaling", 0);
AEFX.set(fn, "Scale Width", P.strand * P.stretch);
AEFX.set(fn, "Scale Height", P.strand);
AEFX.set(fn, "Complexity", 4);
AEFX.set(fn, "Random Seed", seed);
var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 140);
AEFX.find(fn, "Offset Turbulence").expression = "[value[0] + time * " + P.speed + ", value[1]]";
// curls: displace that also drifts outward
var td = AEFX.fx(nl, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.curl);
AEFX.set(td, "Size", P.curl_size);
AEFX.set(td, "Complexity", 2);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 90);
var toff = AEFX.find(td, "Offset (Turbulence)");
if (toff) toff.expression = "[value[0] + time * " + (P.speed * 0.8) + ", value[1]]";
return src;
}
var srcR = noiseComp("R", P.seed), srcL = noiseComp("L", P.seed + 5);
// 2) mirrored pair: right half as rendered, left half flipped (so both sides flow OUT of the centre)
var pair = AEFX.comp(NAME + "_pair", WW, H, FPS, D);
function half(flip) {
  var l = pair.layers.add(flip ? srcL : srcR);
  l.name = flip ? "left" : "right";
  if (flip) l.scale.setValue([-100, 100]);
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var s = new Shape();
  // the mask is in the layer's own space: the flipped copy keeps the same (right-hand) mask, mirrored on screen
  s.vertices = [[WW / 2, -10], [WW + 10, -10], [WW + 10, H + 10], [WW / 2, H + 10]];
  s.closed = true;
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([W * 0.06, 0]);
  l.blendingMode = BlendingMode.ADD;
  return l;
}
half(false); half(true);
// 3) the envelope: wide flat soft ellipse (alpha matte on its own solid; the matte layer is disabled)
var comp = AEFX.comp(NAME, W, H, FPS, D);
var env = comp.layers.addSolid([1, 1, 1], "envelope", W, H, 1);
var em = env.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
var es = new Shape();
var rx = W * 0.5 * P.spread, ry = H * P.thick, cx = W / 2, cy = H / 2, k = 0.5523;
es.vertices = [[cx - rx, cy], [cx, cy - ry], [cx + rx, cy], [cx, cy + ry]];
es.inTangents = [[0, ry * k], [-rx * k, 0], [0, -ry * k], [rx * k, 0]];
es.outTangents = [[0, -ry * k], [rx * k, 0], [0, ry * k], [-rx * k, 0]];
es.closed = true;
em.property("ADBE Mask Shape").setValue(es);
em.property("ADBE Mask Feather").setValue([rx * 0.75, ry * 0.9]);
var w = comp.layers.add(pair);
w.name = "wisps";
w.moveAfter(env);
w.setTrackMatte(env, TrackMatteType.ALPHA);
env.enabled = false;
// grows outward fast then crawls (drag), flares in over 3 frames, fades out
AEFX.keys(w.scale, [[0, [70, 85]], [0.12, [95, 100]], [0.35, [110, 103]], [D, [124, 105]]], false);
AEFX.keys(w.opacity, [[0, 0], [3 / FPS, 100], [0.3, 85], [D * 0.75, 30], [D, 0]], false);
// a soft bloom on the strands (comp-sized adjustment layer, so nothing clips)
var adj = comp.layers.addSolid([1, 1, 1], "bloom", W, H, 1);
adj.adjustmentLayer = true;
var g = AEFX.fx(adj, "ADBE Glo2");
g.property("Glow Threshold").setValue(35);
g.property("Glow Radius").setValue(H * 0.12);
g.property("Glow Intensity").setValue(0.8 * P.glow);
// colour once at the end: black -> color -> core (two-tone, so Spine can retint one frame set: import tintable)
var tt = AEFX.fx(adj, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(P.core)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
return AEFX.done(comp, '"mode":"additive","seq_mode":"once","tintable":true');
