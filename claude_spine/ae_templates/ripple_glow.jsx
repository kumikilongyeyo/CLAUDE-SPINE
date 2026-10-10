/*TEMPLATE {"name":"ripple_glow","doc":"An energy rim that sends glowing waves OUTWARD, like a charged multiplier orb or a powered-up frame: a thin white-hot rim line that wobbles (looping turbulent displacement), rings of light that leave the rim, ease out as they travel `travel` of the half-size, widen, soften and fade, and a soft halo that swells each time a wave leaves. `shape` circle (orbs, coins, medallions) or rect (cells, frames, buttons: `aspect` = width / height, `corner` = roundness as a fraction of the short side). `radius` = the rim as a fraction of the half-size (circle; put it on the subject's edge, the comp centre is the subject centre); a rect rim fills the comp minus the travel. `waves` leave per loop (evenly spaced, each lives the whole loop: 1 = one pulse per `duration`, as the reference orb at ~1 s). `wave` = wave brightness (0.5 subtle, 1.5 punchy), `wobble` = how far the rim and waves are torn (0 = clean geometric rings), `wobble_size` the size of the bumps. Built in grey and coloured once (black -> color -> core), so the render is two-tone: import it tintable and one frame set plays in any colour. Additive on black (mode=\"additive\"); loops exactly.","params":{"size":512,"duration":1.0,"fps":30,"shape":"circle","aspect":1.0,"corner":0.16,"color":"3FA8FF","core":"FFFFFF","radius":0.52,"travel":0.36,"waves":1,"wave":1.0,"wave_width":0.03,"rim_width":0.014,"wobble":9,"wobble_size":0.09,"halo":1.0,"breathe":0.6,"glow":1.0,"seed":3}} */
var D = P.duration, name = P.comp || "ripple_glow", RECT = P.shape === "rect";
if (!RECT && P.shape !== "circle") throw new Error("shape must be circle or rect, not " + P.shape);
var asp = RECT ? Math.max(0.2, Math.min(5, P.aspect)) : 1;
var W = asp >= 1 ? P.size : Math.round(P.size * asp), H = asp >= 1 ? Math.round(P.size / asp) : P.size;
W += W % 2; H += H % 2;
var S2 = Math.min(W, H) / 2, N = Math.max(1, Math.round(P.waves));
var TR = P.travel * S2;                                    // how far a wave travels, px
// rim size (the shape's full width / height) before any wave offset
var BW, BH;
if (RECT) { var m = S2 * (P.travel + 0.12); BW = W - 2 * m; BH = H - 2 * m; }
else { var rr = Math.min(P.radius, 0.97 - P.travel) * S2; BW = BH = 2 * rr; }
if (BW <= 8 || BH <= 8) throw new Error("travel too large for this size: nothing left for the rim");
var RND = RECT ? Math.min(BW, BH) / 2 * Math.min(1, P.corner * 2) : 0;

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
// grow a ring by d px all round (d an expression); a rect's corners grow with it so the offset stays even
function grow(o, d, head) {
  head = head || "";
  o.size.expression = head + "var d = " + d + "; [" + BW + " + 2 * d, " + BH + " + 2 * d]";
  if (RECT) o.round.expression = head + "var d = " + d + "; " + RND + " + d";
}
// looping turbulence: the evolution turns once per loop and Cycle Evolution closes it
function tear(l, amount, size, seed, offset) {
  if (P.wobble <= 0) return null;
  var td = AEFX.fx(l, "ADBE Turbulent Displace");
  AEFX.set(td, "Amount", amount); AEFX.set(td, "Size", size);
  AEFX.set(td, "Complexity", 3); AEFX.set(td, "Random Seed", seed);
  var ev = AEFX.find(td, "Evolution"); ev.setValueAtTime(0, offset); ev.setValueAtTime(D, offset + 360);
  AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1);
  return td;
}
function blur(l, px) { var b = AEFX.fx(l, "ADBE Gaussian Blur 2"); b.property("Blurriness").setValue(px); return b; }
// pulse 1 when a wave leaves the rim, falling off before the next (N per loop)
var PULSE = "var D = " + D + ", N = " + N + ", u = (time / D * N) % 1, pls = Math.max(Math.pow(1 - u, 2.2), Math.pow(Math.max(0, (u - 0.85) / 0.15), 2)); ";
var WS = P.wobble_size * S2 * 2;

// 1. halo: a wide soft band on the rim that swells with every wave
var halo = ring("halo", S2 * 0.12);
grow(halo, S2 * 0.03);
blur(halo.layer, S2 * 0.1);
halo.layer.opacity.expression = PULSE + "Math.min(100, " + (24 * P.halo) + " * (1 - " + P.breathe + " * 0.6 + " + P.breathe + " * pls))";

// 2. the waves: leave the rim, ease out (fast then crawling), widen, soften and fade
for (var k = 0; k < N; k++) {
  var head = "var D = " + D + ", t = ((time / D) + " + (k / N).toFixed(5) + ") % 1, e = 1 - Math.pow(1 - t, 2.4); ";
  var wv = ring("wave" + k, S2 * P.wave_width);
  grow(wv, "e * " + TR.toFixed(2), head);
  wv.width.expression = head + "value * (1 + 1.6 * t)";
  wv.layer.opacity.expression = head + "Math.min(100, " + (85 * P.wave) + " * Math.min(1, t / 0.06) * Math.pow(1 - t, 1.8))";
  var wtd = tear(wv.layer, P.wobble, WS, P.seed + 13 + k, 120 * k);
  if (wtd) AEFX.find(wtd, "Amount").expression = head + "value * (0.8 + 1.4 * e)";   // torn more as it spreads
  var wb = blur(wv.layer, 1);
  wb.property("Blurriness").expression = head + (S2 * 0.008).toFixed(2) + " + " + (S2 * 0.07).toFixed(2) + " * e";
  var wg = ring("wave" + k + "_body", S2 * P.wave_width * 4);                       // the soft light around it
  grow(wg, "e * " + TR.toFixed(2), head);
  wg.layer.opacity.expression = head + "Math.min(100, " + (22 * P.wave) + " * Math.min(1, t / 0.06) * Math.pow(1 - t, 2))";
  tear(wg.layer, P.wobble * 1.3, WS * 1.3, P.seed + 29 + k, 60 + 120 * k);
  blur(wg.layer, S2 * 0.06);
}

// 3. the rim: a soft thick band, the torn line, a hair line out of step, and a white-hot thread
var rg = ring("rim_glow", S2 * P.rim_width * 4);
tear(rg.layer, P.wobble * 0.8, WS, P.seed, 0);
blur(rg.layer, S2 * 0.035);
rg.layer.opacity.expression = PULSE + "30 + 30 * pls";
var r1 = ring("rim", S2 * P.rim_width * 2);
tear(r1.layer, P.wobble, WS, P.seed, 0);
r1.layer.opacity.expression = PULSE + "80 + 20 * pls";
var r2 = ring("rim_hair", S2 * P.rim_width);
tear(r2.layer, P.wobble * 1.2, WS * 0.8, P.seed + 7, 200);
r2.layer.opacity.setValue(70);
var r3 = ring("rim_hot", S2 * P.rim_width * 0.6);
tear(r3.layer, P.wobble * 0.9, WS * 1.1, P.seed + 3, 90);

var bl = G.layers.addSolid([1, 1, 1], "bloom", W, H, 1); bl.adjustmentLayer = true;
var gf = AEFX.fx(bl, "ADBE Glo2");
gf.property("Glow Threshold").setValue(80); gf.property("Glow Radius").setValue(S2 * 0.05 * P.glow);
gf.property("Glow Intensity").setValue(0.35 * P.glow);

// 4. colour once: black -> color -> core, so the frames lie on one colour line (two-tone, tintable)
var comp = AEFX.comp(name, W, H, P.fps, D);
var col = comp.layers.add(G); col.name = "colour";
var tt = AEFX.fx(col, "ADBE Tritone");
AEFX.set(tt, "Highlights", AEFX.rgb(P.core)); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
return AEFX.done(comp, '"mode":"additive","seq_mode":"loop","tintable":true,"rim":[' + BW + ',' + BH + '],"travel":' + TR.toFixed(1));
