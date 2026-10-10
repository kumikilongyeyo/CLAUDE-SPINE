/*TEMPLATE {"name":"ripple_glow","doc":"Soft smoky glowing ripples, like a charged multiplier orb in a slot: look \"smoke\" (default) = each wave is a soft band of evolving smoke (fractal noise inside a turbulence-torn, blurred ring) with a faint glow inside it, and the rim is a smoky halo that breathes as waves pass; look \"line\" = crisp glowing rings. `smoke` = smoke strength, `smoke_size` = the size of the smoke puffs (fraction of the half-size), `line` = how much of the thin ring line shows in the smoke look. Colour is bright, not white: black -> `color` -> `core` (a saturated blue to a bright cyan by default). Rings of light that form small at the CENTRE, expand outward through a softly glowing rim (a charged multiplier orb, a coin, a medallion, a powered-up cell) and fade, then the next one forms in the middle. Every wave in the loop is different (its own turbulent distortion, rotation, slight squash, end size and timing: `jitter` 0..1), each trails `echo` fainter ripple rings, a halo swells as a wave crosses the rim, and the rim line wobbles. origin \"center\" (default) or \"rim\" (waves leave the rim instead). `waves` per loop over `duration` with `life` seconds each (life <= duration; 3 waves / 3 s / 1.6 s = one a second, overlapping a little). `start` = the newborn ring's size as a fraction of the rim, `travel` = how far past the rim it goes (fraction of the half-size), `inner` = brightness while still inside the subject (keeps its art readable), `rim` = rim strength (0 = no rim). `shape` circle or rect (`aspect` = width / height, `corner` = roundness as a fraction of the short side). `radius` = the rim as a fraction of the half-size (put it on the subject's edge; the comp centre is the subject centre). `softness` 0..1 = soft edges and a gentle glow (blurred lines, lower peaks, wider falloff; 0 = crisp neon), `core` = the hottest colour (a bright colour by default, never white unless you ask), `wave` = wave brightness, `wobble` / `wobble_size` = the soft distortion (0 = clean rings). Built in grey and coloured once (black -> color -> core), so the render is two-tone: import it tintable and one frame set plays in any colour. Additive on black (mode=\"additive\"); loops exactly.","params":{"size":512,"duration":3.0,"fps":30,"shape":"circle","aspect":1.0,"corner":0.16,"look":"smoke","origin":"center","color":"2B8CFF","core":"70ECFF","radius":0.52,"travel":0.36,"start":0.08,"waves":3,"life":1.6,"jitter":1.0,"echo":1,"inner":0.8,"wave":1.35,"smoke":1.0,"smoke_size":0.25,"line":0.3,"wave_width":0.03,"rim":0.55,"rim_width":0.014,"wobble":9,"wobble_size":0.09,"softness":0.7,"halo":1.0,"breathe":0.6,"glow":1.0,"seed":3}} */
var D = P.duration, name = P.comp || "ripple_glow", RECT = P.shape === "rect", CENTER = P.origin !== "rim";
if (!RECT && P.shape !== "circle") throw new Error("shape must be circle or rect, not " + P.shape);
if (P.origin !== "center" && P.origin !== "rim") throw new Error("origin must be center or rim, not " + P.origin);
var asp = RECT ? Math.max(0.2, Math.min(5, P.aspect)) : 1;
var W = asp >= 1 ? P.size : Math.round(P.size * asp), H = asp >= 1 ? Math.round(P.size / asp) : P.size;
W += W % 2; H += H % 2;
var S2 = Math.min(W, H) / 2, N = Math.max(1, Math.round(P.waves));
var TR = P.travel * S2;                                    // how far past the rim a wave travels, px
var BW, BH;                                                // the rim's full width / height
if (RECT) { var m = S2 * (P.travel + 0.12); BW = W - 2 * m; BH = H - 2 * m; }
else { var rr = Math.min(P.radius, 0.97 - P.travel) * S2; BW = BH = 2 * rr; }
if (BW <= 8 || BH <= 8) throw new Error("travel too large for this size: nothing left for the rim");
var RREF = Math.min(BW, BH) / 2, RND = RECT ? RREF * Math.min(1, P.corner * 2) : 0;
var SO = Math.max(0, Math.min(1, P.softness)), JIT = Math.max(0, Math.min(1, P.jitter));
if (P.look !== "smoke" && P.look !== "line") throw new Error("look must be smoke or line, not " + P.look);
var SMOKE = P.look === "smoke", LINE = SMOKE ? P.line : 1;
var LIFE = Math.max(0.1, Math.min(D, P.life));
// a wave's size is progress p of the rim: p < 1 scales the rim down (inside), p > 1 grows it by (p - 1) * RREF all round
var P0 = CENTER ? Math.max(0.01, Math.min(0.95, P.start)) : 1, PEND = 1 + TR / RREF, EASE = 2.4;
var EC = (1 - P0) / (PEND - P0), TC = 1 - Math.pow(1 - EC, 1 / EASE);   // life fraction at which a wave crosses the rim

var G = AEFX.comp(name + "_luma", W, H, P.fps, D);
G.layers.addSolid([0, 0, 0], "black", W, H, 1);

// a stroked ring (ellipse or rounded rect) centred on the comp; everything is fetched by path after the adds
function ring(nm, strokeW) {
  var l = AEFX.shape(G, nm);
  var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
  g.property("ADBE Vectors Group").addProperty(RECT ? "ADBE Vector Shape - Rect" : "ADBE Vector Shape - Ellipse");
  g.property("ADBE Vectors Group").addProperty("ADBE Vector Graphic - Stroke");
  var cc = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
  var shp = cc.property(1), st = cc.property("ADBE Vector Graphic - Stroke");
  st.property("ADBE Vector Stroke Color").setValue([1, 1, 1]);
  st.property("ADBE Vector Stroke Width").setValue(strokeW);
  var o = { layer: l, width: st.property("ADBE Vector Stroke Width"),
            size: shp.property(RECT ? "ADBE Vector Rect Size" : "ADBE Vector Ellipse Size") };
  o.size.setValue([BW, BH]);
  if (RECT) { o.round = shp.property("ADBE Vector Rect Roundness"); o.round.setValue(RND); }
  l.position.setValue([W / 2, H / 2]);
  return o;
}
// size from progress p (head is an expression that defines p)
function sizeBy(o, head) {
  o.size.expression = head + "p < 1 ? [" + BW + " * p, " + BH + " * p] : [" + BW + " + 2 * (p - 1) * " + RREF + ", " + BH + " + 2 * (p - 1) * " + RREF + "]";
  if (RECT) o.round.expression = head + RND + " * Math.min(p, 1) + Math.max(0, p - 1) * " + RREF;
}
// looping turbulence: the evolution turns `revs` times per loop and Cycle Evolution closes it
function tear(l, amount, size, seed, offset, revs) {
  if (P.wobble <= 0) return null;
  revs = revs || 1;
  var td = AEFX.fx(l, "ADBE Turbulent Displace");
  AEFX.set(td, "Amount", amount); AEFX.set(td, "Size", size);
  AEFX.set(td, "Complexity", 3); AEFX.set(td, "Random Seed", seed);
  var ev = AEFX.find(td, "Evolution"); ev.setValueAtTime(0, offset); ev.setValueAtTime(D, offset + 360 * revs);
  AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", revs);
  return td;
}
function blur(l, px) { var b = AEFX.fx(l, "ADBE Gaussian Blur 2"); b.property("Blurriness").setValue(px); return b; }
var WS = P.wobble_size * S2 * 2;
// a band of evolving smoke: fractal noise seen through a blurred, turbulence-torn ring (luma track matte). head = the
// wave's expression head (empty: a fixed band on the rim); the smoke texture grows with the wave so it is pushed out
function smokeBand(nm, head, strokeW, blurExpr, opExpr, seed, ev, rot, sq, amtMul, revs) {
  var mt = ring(nm + "_matte", strokeW);
  if (head) { sizeBy(mt, head); mt.width.expression = head + "value * (0.5 + 1.5 * e)"; }
  else mt.size.setValue([BW + strokeW * 0.4, BH + strokeW * 0.4]);
  mt.layer.rotation.setValue(rot); mt.layer.scale.setValue([100 * sq, 100 / sq]);
  if (P.wobble > 0) tear(mt.layer, P.wobble * 2.2 * amtMul, WS * 1.4, seed + 3, ev, revs);
  var bb = blur(mt.layer, 1); bb.property("Blurriness").expression = blurExpr;
  var sm = G.layers.addSolid([0, 0, 0], nm, W, H, 1);
  var fn = AEFX.fx(sm, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
  AEFX.set(fn, "Contrast", 120); AEFX.set(fn, "Brightness", 24);
  AEFX.set(fn, "Scale", Math.max(8, S2 * P.smoke_size)); AEFX.set(fn, "Complexity", 5); AEFX.set(fn, "Random Seed", seed);
  var nev = AEFX.find(fn, "Evolution"); nev.setValueAtTime(0, ev); nev.setValueAtTime(D, ev + 360 * revs);
  AEFX.set(fn, "Cycle Evolution", 1); AEFX.set(fn, "Cycle (in Revolutions)", revs);
  if (head) sm.scale.expression = head + "var s = 100 * (0.8 + 0.5 * e); [s, s]";
  sm.opacity.expression = opExpr;
  sm.blendingMode = BlendingMode.ADD;
  mt.layer.moveBefore(sm);
  sm.setTrackMatte(mt.layer, TrackMatteType.LUMA);
  mt.layer.enabled = false;
  return sm;
}

// every wave its own: start time, life, end size, distortion, rotation, squash (seeded: same seed, same loop)
var rnd = AEFX.rng(P.seed * 13 + 5), WV = [];
function jit(a) { return (rnd() * 2 - 1) * a * JIT; }
for (var k = 0; k < N; k++) {
  WV.push({ t0: ((k / N + jit(0.35 / N)) % 1 + 1) % 1 * D, life: LIFE * (1 + jit(0.12)), pend: 1 + (PEND - 1) * (1 + jit(0.18)),
            amt: 1 + jit(0.35), rot: RECT ? (rnd() < 0.5 * JIT ? 180 : 0) : rnd() * 360 * JIT,   // a rect only flips (its distortion changes), never tilts
            sq: 1 + jit(0.05), seed: Math.floor(rnd() * 900) + 1, ev: rnd() * 360 });
}
// head: t = this wave's life fraction (>= 1 = not alive), e = ease-out, p = size progress
function headOf(w, lag) {
  return "var D = " + D + ", L = " + w.life.toFixed(4) + ", a = ((time - " + (w.t0 + lag).toFixed(4) + ") % D + D) % D, t = a / L, " +
         "e = 1 - Math.pow(1 - Math.min(t, 1), " + EASE + "), p = " + P0 + " + (" + w.pend.toFixed(4) + " - " + P0 + ") * e; ";
}
// opacity of a wave: fades in, fades out, dimmer while still inside the subject
function alive(peak, inTime, outPow) {
  return "t >= 1 ? 0 : Math.min(100, " + peak + " * Math.min(1, t / " + inTime + ") * Math.pow(1 - t, " + outPow + ") * " +
         "(" + P.inner + " + " + (1 - P.inner) + " * Math.min(1, Math.max(0, (p - " + P0 + ") / " + Math.max(0.001, 1 - P0) + "))))";
}

// 1. halo: a wide soft band on the rim that swells as each wave crosses it
var halo = ring("halo", S2 * 0.12);
halo.size.setValue([BW + S2 * 0.06, BH + S2 * 0.06]);
blur(halo.layer, S2 * (0.1 + 0.06 * SO));
var bumps = [];
for (var b = 0; b < N; b++) {
  var hc = WV[b].t0 + TC * WV[b].life;                    // when this wave crosses the rim
  bumps.push("Math.exp(-Math.pow(((((time - " + hc.toFixed(4) + ") % D + D) % D + D / 2) % D - D / 2) / " + (0.16 * WV[b].life).toFixed(4) + ", 2))");
}
var PULSE = "var D = " + D + ", pls = Math.min(1, " + bumps.join(" + ") + "); ";
halo.layer.opacity.expression = PULSE + "Math.min(100, " + (20 * P.halo) + " * (1 - " + P.breathe + " * 0.6 + " + P.breathe + " * pls))";

// 2. the waves: form small, ease out (fast then crawling), widen, soften and fade; each trails `echo` ripples
var WAVEPK = 85 * P.wave * (1 - 0.45 * SO), FADEIN = (CENTER ? 0.12 : 0.06) + 0.1 * SO;
var TRAINS = Math.max(0, Math.min(2, Math.round(P.echo)));
for (var k2 = 0; k2 < N; k2++) {
  var w = WV[k2];
  for (var r = 0; r <= TRAINS; r++) {
    var head = headOf(w, r * 0.12 * w.life), dim = r === 0 ? 1 : 0.45 / r;
    var wv = ring("wave" + k2 + (r ? "_echo" + r : ""), S2 * P.wave_width * (r ? 0.7 : 1));
    sizeBy(wv, head);
    wv.width.expression = head + "value * (0.6 + 2 * e)";
    wv.layer.opacity.expression = head + alive(WAVEPK * dim * LINE, FADEIN, 1.7);
    wv.layer.rotation.setValue(w.rot + (RECT ? 0 : 23 * r));
    wv.layer.scale.setValue([100 * w.sq, 100 / w.sq]);
    var wtd = tear(wv.layer, P.wobble * w.amt, WS * (r ? 0.8 : 1), w.seed + 7 * r, w.ev + 60 * r, 2);
    if (wtd) AEFX.find(wtd, "Amount").expression = head + "value * (0.4 + 1.6 * e)";   // torn more as it spreads
    var wb = blur(wv.layer, 1);
    wb.property("Blurriness").expression = head + (S2 * (0.008 + 0.022 * SO)).toFixed(2) + " + " + (S2 * (0.07 + 0.05 * SO)).toFixed(2) + " * e";
    if (r) continue;
    var wg = ring("wave" + k2 + "_body", S2 * P.wave_width * 4);                    // the soft light around it
    sizeBy(wg, head);
    wg.layer.opacity.expression = head + alive(22 * P.wave * (1 + 0.3 * SO), FADEIN, 2);
    wg.layer.rotation.setValue(w.rot);
    wg.layer.scale.setValue([100 * w.sq, 100 / w.sq]);
    tear(wg.layer, P.wobble * 1.3 * w.amt, WS * 1.3, w.seed + 29, w.ev + 90, 2);
    blur(wg.layer, S2 * (0.06 + 0.05 * SO));
    if (SMOKE && P.smoke > 0)
      smokeBand("wave" + k2 + "_smoke", head, S2 * 0.1,
                head + (S2 * 0.03).toFixed(2) + " + " + (S2 * 0.06).toFixed(2) + " * e",
                head + alive(100 * P.smoke, FADEIN, 1.5), w.seed + 50, w.ev, w.rot, w.sq, w.amt, 2);
  }
}

// 3. the rim: a soft thick band, the torn line, a hair line out of step, and a hot thread (all scaled by `rim`)
if (P.rim > 0) {
  var rg = ring("rim_glow", S2 * P.rim_width * (4 + 4 * SO));
  tear(rg.layer, P.wobble * 0.8, WS, P.seed, 0);
  blur(rg.layer, S2 * (0.035 + 0.05 * SO));
  rg.layer.opacity.expression = PULSE + "Math.min(100, (30 + 12 * pls) * " + ((1 - 0.5 * SO) * P.rim) + ")";
  if (SMOKE && P.smoke > 0)
    smokeBand("rim_smoke", "", S2 * 0.13, String((S2 * 0.05).toFixed(2)),
              PULSE + "Math.min(100, (55 + 30 * pls) * " + (P.rim * P.smoke) + ")", P.seed + 101, 0, 0, 1, 0.8, 1);
  var r1 = ring("rim", S2 * P.rim_width * 2);
  tear(r1.layer, P.wobble, WS, P.seed, 0);
  r1.layer.opacity.expression = PULSE + "Math.min(100, (" + (80 - 45 * SO) + " + 8 * pls) * " + (P.rim * LINE) + ")";
  if (SO > 0) blur(r1.layer, S2 * 0.012 * SO);
  var r2 = ring("rim_hair", S2 * P.rim_width);
  tear(r2.layer, P.wobble * 1.2, WS * 0.8, P.seed + 7, 200);
  r2.layer.opacity.setValue(Math.min(100, (70 - 35 * SO) * P.rim * LINE));
  if (SO > 0) blur(r2.layer, S2 * 0.008 * SO);
  var r3 = ring("rim_hot", S2 * P.rim_width * 0.6);
  tear(r3.layer, P.wobble * 0.9, WS * 1.1, P.seed + 3, 90);
  r3.layer.opacity.setValue(Math.min(100, (100 - 70 * SO) * P.rim * LINE));
  if (SO > 0) blur(r3.layer, S2 * 0.005 * SO);
}

var bl = G.layers.addSolid([1, 1, 1], "bloom", W, H, 1); bl.adjustmentLayer = true;
var gf = AEFX.fx(bl, "ADBE Glo2");
gf.property("Glow Threshold").setValue(80); gf.property("Glow Radius").setValue(S2 * (0.05 + 0.05 * SO) * P.glow);
gf.property("Glow Intensity").setValue((0.35 - 0.15 * SO) * P.glow);

// 4. colour once: black -> color -> core, so the frames lie on one colour line (two-tone, tintable)
var comp = AEFX.comp(name, W, H, P.fps, D);
var col = comp.layers.add(G); col.name = "colour";
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(P.core)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","tintable":true,"rim":[' + BW + ',' + BH + '],"travel":' + TR.toFixed(1));
