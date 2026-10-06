/*TEMPLATE {"name":"fire_aura","doc":"A ring of flame shooting OUTWARD from a hole, the classic power-up / punch aura (fists, a scatter, a character). Built from the fire template: a wide strip of rising fire with a thin body and tall tongues, mirrored so the wrap seam disappears, flipped so the tongues hang from a base line, squeezed into a square comp (Polar Coordinates works in the layer's own pixels and takes the SHORT side as the radius, so an unsqueezed strip wraps into a thin oval), then wrapped with Polar Coordinates (Rect to Polar) and glowed. Loops (the strip is a loopified fire). hot / mid / cool colour it (fire by default; F0FFFF / 3AA8FF / 1030B0 for an electric blue aura). Transparent background: mode=\"alpha\", seq_mode loop. In Spine show it at ~0.5-0.9 of its size around the subject, 256 px frames are plenty (max_size=256).","uses":["fire"],"params":{"size":512,"duration":0.67,"fps":24,"hot":"FFF4C0","mid":"FF7A14","cool":"C02A08","scale":24,"rise":420,"lick":0.6,"glow":0.6,"seed":1}} */
function merge(a, b) { var o = {}, k; for (k in a) o[k] = a[k]; for (k in b) o[k] = b[k]; return o; }
function byName(n) {
  for (var i = 1; i <= app.project.numItems; i++) { var it = app.project.item(i); if (it.name === n && it.layers) return it; }   // only comps have layers
  throw new Error("fire_aura: no comp " + n);
}
var name = P.comp || "fire_aura", D = P.duration, S = P.size;
// 1. the flame strip (tuned: a thin hot body so the tongues, not a solid band, fill the strip)
var r = eval("(" + AEFX.T_fire(merge(AEFX.D_fire, {
  comp: name + "_strip", width: 1024, height: 320, duration: D, fps: P.fps, hot: P.hot, mid: P.mid, cool: P.cool,
  scale: P.scale, rise: P.rise, lick: P.lick, seed: P.seed, core: 0.18, body: 0.06, threshold: 0.3, softness: 0.45,
  alpha_cut: 0.34, flame_height: 0.95, contrast: 80, loop: true})) + ")");
var strip = byName(r.comp);
// 2. mirror it side by side (right copy flipped: both joins match) and flip it upside down (tongues hang from the base)
var M = AEFX.comp(name + "_mirror", 2048, 480, P.fps, D);
var a = M.layers.add(strip); a.scale.setValue([100, -100]); a.position.setValue([512, 320]);
var b = M.layers.add(strip); b.scale.setValue([-100, -100]); b.position.setValue([1536, 320]);
// 3. squeeze into a square, 4. wrap round: Rect to Polar maps the strip's top row to the centre, its bottom to the rim
var Q = AEFX.comp(name + "_square", S, S, P.fps, D);
var q = Q.layers.add(M); q.scale.setValue([S / 2048 * 100, S / 480 * 100]); q.position.setValue([S / 2, S / 2]);
var comp = AEFX.comp(name, S, S, P.fps, D);
var l = comp.layers.add(Q);
var pc = AEFX.fx(l, "ADBE Polar Coordinates");
pc.property(1).setValue(1);          // interpolation is 0..1, not percent
pc.property(2).setValue(1);          // 1 = Rect to Polar
var g = AEFX.fx(l, "ADBE Glo2");
g.property("ADBE Glo2-0003").setValue(S * 0.047); g.property("ADBE Glo2-0004").setValue(P.glow);
return AEFX.done(comp, '"mode":"alpha","seq_mode":"loop"');
