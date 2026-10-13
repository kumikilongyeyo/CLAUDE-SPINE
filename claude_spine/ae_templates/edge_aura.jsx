/*TEMPLATE {"name": "edge_aura", "doc": "Lime energy hugging a subject's silhouette (from a fantasy slot SPIN button while it spins): a tight hot hug and a halo built from the silhouette, soft noise tongues streaked radially outward through a ragged band just outside the outline, and thin electric veins, flickering on whole cycles; an EXACT loop (rendered twice the duration and crossfaded). art = the subject's silhouette PNG (alpha = shape, centred; each art px becomes art_scale comp px); without art a generic spiked medallion. Colour: color (body) and light (tongues / veins); two-tone, import tintable. Additive on black (mode=\"additive\"), seq_mode loop; key its alpha in Spine (the reference: in over 0.07 s, hold, fade out over ~0.9 s, ~0.7 alpha) and pair it with fx_recipe silhouette_halo for the wide soft falloff. Draw it BEHIND the subject.", "params": {"size": 640, "duration": 1.0, "fps": 30, "color": "34F07C", "light": "A8FFB4", "art": "", "art_scale": 2.0, "halo": 11, "hug": 3, "reach": 112, "tongues": 0.9, "veins": 0.6, "seed": 9}} */
// ---- shared by energy_burst / edge_aura: the subject's silhouette as a comp-sized precomp, filled / blurred copies,
// and Fractal Noise shaped by a torn silhouette matte (Fractal Noise overwrites alpha, so the shape is a matte layer)
function SIL_comp(nm, S, K, art, fps, dur) {
  var c = AEFX.comp(nm, S, S, fps, dur);
  if (art) {
    var l = c.layers.add(AEFX.imp(art));
    l.scale.setValue([100 * K, 100 * K]); l.position.setValue([S / 2, S / 2]);
  } else {                      // a generic spiked medallion: frame r 80, four diagonal spikes to 116 (art px)
    var sh = c.layers.addShape(); sh.name = "medallion";
    var root = sh.property("ADBE Root Vectors Group");
    var g = root.addProperty("ADBE Vector Group");
    g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Ellipse");
    var i;
    for (i = 0; i < 4; i++) g.property("ADBE Vectors Group").addProperty("ADBE Vector Shape - Group");
    g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Fill");
    var cc = sh.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
    cc.property("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size").setValue([160 * K, 160 * K]);
    var n = 0;
    for (i = 1; i <= cc.numProperties; i++) {
      var pr = cc.property(i);
      if (pr.matchName !== "ADBE Vector Shape - Group") continue;
      var a = (45 + 90 * n) * Math.PI / 180; n++;
      var s = new Shape();
      s.vertices = [[Math.cos(a - 0.36) * 70 * K, Math.sin(a - 0.36) * 70 * K], [Math.cos(a) * 116 * K, Math.sin(a) * 116 * K],
                    [Math.cos(a + 0.36) * 70 * K, Math.sin(a + 0.36) * 70 * K]];
      s.closed = true;
      pr.property("ADBE Vector Shape").setValue(s);
    }
    cc.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue([1, 1, 1]);
    sh.position.setValue([S / 2, S / 2]);
  }
  return c;
}
function SIL_layer(comp, silc, nm, pct, color, blur, op) {
  var l = comp.layers.add(silc); l.name = nm;
  l.scale.setValue([pct, pct]);
  AEFX.set(AEFX.fx(l, "ADBE Fill"), "Color", color);
  if (blur > 0) { var b = AEFX.fx(l, "ADBE Box Blur2"); AEFX.set(b, "Blur Radius", blur); AEFX.set(b, "Iterations", 3); }
  l.blendingMode = BlendingMode.ADD; l.opacity.setValue(op);
  return l;
}
function SIL_noise(comp, silc, o) {
  var S = comp.width, D = comp.duration;
  var s = comp.layers.addSolid([0, 0, 0], o.nm, S, S, 1);
  var fn = AEFX.fx(s, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", o.ftype); AEFX.set(fn, "Noise Type", 3);
  if (o.invert) AEFX.set(fn, "Invert", 1);
  AEFX.set(fn, "Contrast", o.contrast); AEFX.set(fn, "Brightness", o.bright);   // contrast > ~150 whites out
  AEFX.set(fn, "Scale", o.scale); AEFX.set(fn, "Complexity", o.cx);
  AEFX.set(fn, "Random Seed", o.seed);
  var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(D, o.evo * D);
  if (o.rise) AEFX.find(fn, "Offset Turbulence").expression =
    "[value[0] + Math.sin(time*1.7)*" + o.drift + ", value[1] - time*" + o.rise + "]";
  if (o.levels) {
    var lv = AEFX.fx(s, "ADBE Pro Levels2");
    AEFX.set(lv, "Input Black", o.levels[0]); AEFX.set(lv, "Input White", o.levels[1]);
  }
  if (o.zoom) {                 // radial streaks out of the centre: tongues of light
    var rb = AEFX.fx(s, "CC Radial Fast Blur");
    AEFX.set(rb, "Center", [S / 2, S / 2]); AEFX.set(rb, "Amount", o.zoom);
    try { AEFX.set(rb, "Zoom", 2); } catch (e) {}
  }
  var tt = AEFX.fx(s, "ADBE Tritone");
  AEFX.set(tt, "Highlights", o.hi); AEFX.set(tt, "Midtones", o.mid); AEFX.set(tt, "Shadows", [0, 0, 0]);
  s.blendingMode = BlendingMode.ADD; s.opacity.setValue(Math.min(100, o.op));
  var mt = comp.layers.add(silc); mt.name = o.nm + "_matte";
  mt.scale.setValue([o.mpct, o.mpct]);
  AEFX.set(AEFX.fx(mt, "ADBE Fill"), "Color", [1, 1, 1]);
  var mb = AEFX.fx(mt, "ADBE Box Blur2"); AEFX.set(mb, "Blur Radius", o.mblur); AEFX.set(mb, "Iterations", 3);
  var td = AEFX.fx(mt, "ADBE Turbulent Displace");
  AEFX.set(td, "Amount", o.tear); AEFX.set(td, "Size", o.tearSize);
  var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, o.tearEvo * D);
  mt.moveBefore(s);
  s.setTrackMatte(mt, TrackMatteType.ALPHA);
  mt.enabled = false;
  return s;
}
function MUL(a, k) { return [Math.min(1, a[0] * k), Math.min(1, a[1] * k), Math.min(1, a[2] * k)]; }

var S = P.size, K = P.art_scale, fps = P.fps, L = P.duration, name = P.comp || "edge_aura";
var BODY = AEFX.rgb(P.color), LIGHT = AEFX.rgb(P.light);
var DD = 2 * L;
var silc = SIL_comp(name + "_sil", S, K, P.art, fps, DD);
var src = AEFX.comp(name + "_src", S, S, fps, DD);
src.layers.addSolid([0, 0, 0], "black", S, S, 1);
SIL_layer(src, silc, "02_CORE_halo", 100, MUL(BODY, 0.7), P.halo * K, 100);
SIL_layer(src, silc, "02_CORE_hug", 100, BODY, P.hug * K, 100);
SIL_noise(src, silc, { nm: "03_SECONDARY_tongues", ftype: 4, contrast: 125, bright: -16, scale: 14 * K, cx: 3, seed: P.seed,
  evo: 900, zoom: 30, hi: LIGHT, mid: MUL(BODY, 0.6), op: 100 * P.tongues, mpct: P.reach, mblur: 5 * K, tear: 7 * K,
  tearSize: 6 * K, tearEvo: 900, rise: 0, drift: 0 });
SIL_noise(src, silc, { nm: "04_DETAIL_veins", ftype: 8, invert: true, contrast: 140, bright: -12, scale: 18 * K, cx: 3,
  seed: P.seed + 5, evo: 1200, levels: [0.66, 0.96], zoom: 22, hi: LIGHT, mid: MUL(LIGHT, 0.5), op: 100 * P.veins,
  mpct: P.reach * 1.05, mblur: 7 * K, tear: 8 * K, tearSize: 6 * K, tearEvo: 1200, rise: 0, drift: 0 });
var fl = src.layers.addSolid([1, 1, 1], "05_LIGHTING_flicker", S, S, 1); fl.adjustmentLayer = true;
var ex = AEFX.fx(fl, "ADBE Exposure2");
AEFX.find(ex, "Exposure").expression = "0.15*Math.sin(time*2*Math.PI*" + (5 / L) + ")*Math.sin(time*2*Math.PI*" + (3 / L) + "+1.3)";
var loop = AEFX.loopify(src, name, L);
return AEFX.done(loop, '"mode":"additive","seq_mode":"loop"');
