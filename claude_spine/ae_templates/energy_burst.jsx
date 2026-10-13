/*TEMPLATE {"name": "energy_burst", "doc": "Energy-smoke burst round a button or symbol (from a fantasy slot SPIN button tap): a square-ish blob of churning cyan energy smoke shaped like the subject's silhouette blown up (`spread` / `wide` percent), torn at the edge, laced with thin bright veins streaked outward, that POPS in 2 frames, holds ~0.2 s, falls to a haze by 0.47 s, holds the haze (`plateau`) to 0.77 s and is gone by 1.2 s while contracting toward the subject. art = the subject's silhouette PNG (alpha = shape, centred; each art px becomes art_scale comp px); without art a generic spiked medallion (frame r 80, spikes to 116 art px). Colour: color (body) and light (smoke highlights); two-tone, import tintable (light/dark) to recolour without a re-render. Additive on black (mode=\"additive\"), one-shot: the peak is comp frame 2 (hit_ae = 2/fps). Draw it BEHIND the subject; at the reference it played at ~0.68 alpha.", "params": {"size": 768, "duration": 1.4, "fps": 30, "color": "00C8B4", "light": "50FFE6", "art": "", "art_scale": 2.0, "spread": 140, "wide": 165, "body": 0.6, "wide_body": 0.4, "smoke": 1.0, "veins": 0.75, "plateau": 0.4, "seed": 21}} */
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

var S = P.size, K = P.art_scale, fps = P.fps, D = P.duration, name = P.comp || "energy_burst";
var BODY = AEFX.rgb(P.color), LIGHT = AEFX.rgb(P.light);
var silc = SIL_comp(name + "_sil", S, K, P.art, fps, D);
var src = AEFX.comp(name + "_src", S, S, fps, D);
src.layers.addSolid([0, 0, 0], "black", S, S, 1);
// 1. the light: the silhouette blown up and blurred, a wide faint one and a nearer one
SIL_layer(src, silc, "02_CORE_wide", P.wide, MUL(BODY, P.wide_body), 40 * K, 100);
SIL_layer(src, silc, "02_CORE_body", P.spread, MUL(BODY, P.body), 18 * K, 100);
// 2. smoke: churning noise through the torn square matte (lumps and gaps carry the structure), rising a little
SIL_noise(src, silc, { nm: "03_SECONDARY_smoke", ftype: 4, contrast: 135, bright: -18, scale: 46 * K, cx: 4, seed: P.seed,
  evo: 420, hi: LIGHT, mid: MUL(BODY, 0.8), op: 100 * P.smoke, mpct: P.spread * 1.08, mblur: 12 * K, tear: 34 * K,
  tearSize: 22 * K, tearEvo: 400, rise: 30, drift: 12 });
// 3. veins: thin bright creases (inverted Turbulent Sharp), streaked outward from the centre
SIL_noise(src, silc, { nm: "04_DETAIL_veins", ftype: 8, invert: true, contrast: 130, bright: -10, scale: 34 * K, cx: 3,
  seed: P.seed + 17, evo: 700, levels: [0.62, 0.95], zoom: 18, hi: LIGHT, mid: MUL(LIGHT, 0.6), op: 100 * P.veins,
  mpct: P.spread * 1.02, mblur: 15 * K, tear: 25 * K, tearSize: 18 * K, tearEvo: 400, rise: 0, drift: 0 });
// 4. timing (measured): pop in 2 frames, hold, haze, out; scale 90 -> 100 at the pop, breathes, contracts to 91
var comp = AEFX.comp(name, S, S, fps, D);
var l = comp.layers.add(src);
var f = 1 / fps, H = 100 * P.plateau;
AEFX.keys(l.opacity, [[0, 0], [f, 35], [2 * f, 100], [0.2, 95], [0.27, 82], [0.37, 60], [0.47, H * 1.05], [0.77, H],
  [0.87, H * 0.78], [0.97, H * 0.6], [1.07, H * 0.2], [1.2, 0]], false);
AEFX.keys(l.scale, [[0, [90, 90]], [2 * f, [100, 100]], [0.4, [101, 101]], [0.8, [95, 95]], [1.2, [91, 91]]], true);
return AEFX.done(comp, '"mode":"additive","seq_mode":"once","hit_ae":' + (2 / fps));
