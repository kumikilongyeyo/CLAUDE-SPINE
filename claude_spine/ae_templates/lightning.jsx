/*TEMPLATE {"name":"lightning","doc":"A forking bolt between two points with real (exaggerated) strike physics: a thin, jittering STEPPED LEADER feels its way across for `lead` seconds, then the RETURN STROKE: the channel snaps bright and wide with a flash of air-glow around the channel and heavy branching, the branches die first while the channel dims, then `restrikes` more strokes hit the same channel (new fork pattern each) before it fades. Positions are fractions of the comp. Additive.","params":{"width":512,"height":256,"duration":0.6,"fps":24,"start":[0.05,0.5],"end":[0.95,0.5],"color":"7FB8FF","core":"FFFFFF","segments":22,"amplitude":0.35,"branching":0.3,"bolt_width":0.03,"lead":0.08,"restrikes":2,"flash":0.9,"seed":3,"glow":1.0}} */
var W = P.width, H = P.height, D = P.duration, comp = AEFX.comp(P.comp || "lightning", W, H, P.fps, D);
var rnd = AEFX.rng(P.seed + 5), lead = P.lead;
var strikes = [lead];
for (var i = 0; i < P.restrikes; i++) strikes.push(Math.min(D - 0.08, strikes[strikes.length - 1] + 0.11 + rnd() * 0.1));
var l = comp.layers.addSolid([0, 0, 0], "bolt", W, H, 1);
var lt = AEFX.fx(l, "ADBE Lightning");
AEFX.set(lt, "Start point", [W * P.start[0], H * P.start[1]]);
var ex0 = W * P.start[0] + (W * P.end[0] - W * P.start[0]) * 0.12, ey0 = H * P.start[1] + (H * P.end[1] - H * P.start[1]) * 0.12;
AEFX.keys(AEFX.find(lt, "End point"), [[0, [ex0, ey0]], [lead * 0.999, [W * P.end[0], H * P.end[1]]]], false);   // the leader feels its way across
AEFX.set(lt, "Segments", P.segments);
AEFX.set(lt, "Amplitude", P.amplitude * 100);
AEFX.set(lt, "Core Width", 0.16);
var oc = AEFX.rgb(P.color); oc.push(1); AEFX.set(lt, "Outside Color", oc);
var ic = AEFX.rgb(P.core); ic.push(1); AEFX.set(lt, "Inside Color", ic);
AEFX.set(lt, "Speed", 1);
// the fork pattern: jitters every frame during the leader, then holds one shape per stroke
var ks = "[" + strikes.join(",") + "]";
AEFX.find(lt, "Random Seed").expression =
  "var t = time, s = " + P.seed + "; if (t < " + lead + ") { s + Math.floor(t * " + P.fps + ") } else { var ks = " + ks +
  "; var i = 0; for (var j = 0; j < ks.length; j++) if (t >= ks[j]) i = j; s + 100 + i * 7 }";
var wmax = Math.max(1, W * P.bolt_width);
var wk = [[0, wmax * 0.3], [lead - 0.001, wmax * 0.35]], bk = [[0, 0.04], [lead - 0.001, 0.04]], ok = [[0, 0], [lead * 0.4, 20], [lead - 0.001, 42]], fk = [[0, 0]];
for (var si = 0; si < strikes.length; si++) {
  var t0 = strikes[si], nxt = si + 1 < strikes.length ? strikes[si + 1] : D;
  var hold = Math.max(0.03, Math.min(0.18, nxt - t0 - 0.01));
  wk.push([t0, wmax], [t0 + hold * 0.4, wmax * 0.7], [nxt - 0.001, wmax * 0.5]);                 // channel narrows as it cools
  bk.push([t0, P.branching * (si === 0 ? 1.6 : 1.1)], [t0 + hold * 0.5, 0.05], [nxt - 0.001, 0.03]);  // branches die first
  ok.push([t0, 100], [t0 + hold * 0.35, si === 0 ? 55 : 48], [nxt - 0.001, si + 1 < strikes.length ? 30 : 0]);
  fk.push([t0 - 0.001, 0], [t0, 25 * P.flash * (si === 0 ? 1 : 0.6)], [t0 + 0.06, 0]);
}
AEFX.keys(AEFX.find(lt, "Width"), wk, false);
AEFX.keys(AEFX.find(lt, "Branching"), bk, false);
AEFX.keys(l.opacity, ok, false);
var flash = l.duplicate(); flash.name = "flash";                              // the return stroke's air-glow: the bolt itself, blown wide
AEFX.fx(flash, "ADBE Gaussian Blur 2").property("Blurriness").setValue(H * 0.35);
flash.blendingMode = BlendingMode.ADD;
for (var kk = flash.opacity.numKeys; kk >= 1; kk--) flash.opacity.removeKey(kk);
AEFX.keys(flash.opacity, fk, false);
var g = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); g.adjustmentLayer = true;
var gf = AEFX.fx(g, "ADBE Glo2");
gf.property("Glow Threshold").setValue(55); gf.property("Glow Radius").setValue(H * 0.08 * P.glow);
var gi = gf.property("Glow Intensity"), gk = [[0, 0.5 * P.glow]];
for (var si = 0; si < strikes.length; si++) gk.push([strikes[si] - 0.001, 0.6 * P.glow], [strikes[si], 1.4 * P.glow], [strikes[si] + 0.1, 0.7 * P.glow]);
AEFX.keys(gi, gk, false);
return AEFX.done(comp, '"mode":"additive"');
