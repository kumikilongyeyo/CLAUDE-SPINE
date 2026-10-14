/*TEMPLATE {"name":"fire_strip","doc":"A straight strip of flame made of separate teardrop tongues (nested red, orange, yellow, white) that grow, sway and die out of phase, over a hot ember bed with rising sparks. Loops seamlessly. Meant to be bent along any path in Spine: ae_fx_along_path wraps it on a path mesh.","params":{"width":1024,"height":384,"duration":0.8,"fps":24,"tongues":15,"baseline":0.9,"tall":0.82,"wide":0.11,"sway":9,"lick":0.8,"embers":14,"cool":"D2200A","mid":"FF6A10","warm":"FFB020","hot":"FFF0A0","core":"FFFFFF","wobble":12,"glow":1.0,"seed":4,"end_fade":0.08}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "fire_strip";
var rnd = AEFX.rng(P.seed), by = H * P.baseline;
var comp = AEFX.comp(name, W, H, P.fps, D);
var TWO = Math.PI * 2;

function flameShape(w, h, tx) {
  var s = new Shape();
  s.vertices = [[-w / 2, 0], [tx, -h], [w / 2, 0], [0, w * 0.2]];
  s.inTangents = [[0, w * 0.14], [-w * 0.03, h * 0.45], [-w * 0.16, -h * 0.5], [w * 0.28, 0]];
  s.outTangents = [[w * 0.16, -h * 0.5], [w * 0.03, h * 0.45], [0, w * 0.14], [-w * 0.28, 0]];
  s.closed = true;
  return s;
}
// one tongue = four nested teardrops on a single layer (back to front: cool, mid, warm, hot, white core)
function tongue(i, x, w, h, tx, phase, k) {
  var l = AEFX.shape(comp, "tongue" + i);
  var tiers = [[P.cool, 1.0, 1.0, 0.9], [P.mid, 0.82, 0.76, 0.8], [P.warm, 0.62, 0.58, 0.55], [P.hot, 0.42, 0.4, 0.3], [P.core, 0.22, 0.2, 0.12]];
  var root = l.property("ADBE Root Vectors Group");
  for (var t = 0; t < tiers.length; t++) root.addProperty("ADBE Vector Group");
  for (t = 0; t < tiers.length; t++) {
    // addProperty puts the newest group on top, so the last one added (index 1) is the front-most
    var g = root.property(tiers.length - t).property("ADBE Vectors Group");
    g.addProperty("ADBE Vector Shape - Group");
    g.addProperty("ADBE Vector Graphic - Fill");
  }
  for (t = 0; t < tiers.length; t++) {
    var gg = root.property(tiers.length - t).property("ADBE Vectors Group");
    var tier = tiers[t];
    gg.property("ADBE Vector Shape - Group").property("ADBE Vector Shape").setValue(flameShape(w * tier[2], h * tier[1], tx * tier[2]));
    gg.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue(AEFX.rgb(tier[0]));
  }
  l.position.setValue([x, by]);
  var N = 12, rot = [], sc = [];
  for (var s = 0; s <= N; s++) {
    var tt = D * s / N, ph = TWO * (tt / D * k + phase);
    rot.push([tt, P.sway * Math.sin(ph) * (0.6 + 0.4 * Math.sin(ph * 0.5 + 1.3))]);
    var pulse = Math.pow(0.5 + 0.5 * Math.sin(TWO * (tt / D + phase * 0.7)), 1.4);          // grows, then dies, once per loop
    var env = 0.18 + 0.82 * pulse;
    var flick = 1 + 0.12 * Math.sin(TWO * (2 * tt / D + phase * 1.9));
    sc.push([tt, [100 * (0.82 + 0.3 * pulse), 100 * env * flick]]);
  }
  AEFX.keys(l.rotation, rot, true);
  AEFX.keys(l.scale, sc, true);
  return l;
}

// back row first (taller, dimmer in the middle), then the front row
var n = P.tongues, items = [];
for (var i = 0; i < n; i++) {
  var u = (i + 0.5) / n, x = W * (P.end_fade + (1 - 2 * P.end_fade) * (u + (rnd() - 0.5) * 0.5 / n));
  var edge = Math.min(1, Math.min(u, 1 - u) / P.end_fade * 0.45 + 0.35);          // shorter at both ends
  var h = H * P.tall * (0.55 + 0.45 * rnd()) * edge, w = W * P.wide * (0.7 + 0.6 * rnd());
  items.push({ x: x, w: w, h: h, tx: (rnd() - 0.5) * w * 0.7, ph: rnd(), k: rnd() < 0.5 ? 1 : 2 });
}
items.sort(function (a, b) { return b.h - a.h; });                               // tallest first = behind
var layers = [];
for (i = 0; i < items.length; i++) { var it = items[i]; layers.push(tongue(i, it.x, it.w, it.h, it.tx, it.ph, it.k)); }

// hot bed along the baseline
var bed = AEFX.shape(comp, "bed");
var bg = bed.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group").property("ADBE Vectors Group");
bg.addProperty("ADBE Vector Shape - Rect");
bg.addProperty("ADBE Vector Graphic - Fill");
var bc = bed.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
bc.property("ADBE Vector Shape - Rect").property("ADBE Vector Rect Size").setValue([W * (1 - 2 * P.end_fade), H * 0.1]);
bc.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue(AEFX.rgb(P.hot));
bed.position.setValue([W / 2, by]);
AEFX.fx(bed, "ADBE Gaussian Blur 2").property("Blurriness").setValue(H * 0.05);
AEFX.keys(bed.opacity, [[0, 85], [D / 2, 100], [D, 85]], true);

// sparks rising off the fire; every cycle starts and ends invisible, so the loop has no pop
for (var e = 0; e < P.embers; e++) {
  var sp = AEFX.shape(comp, "ember" + e);
  var eg = sp.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group").property("ADBE Vectors Group");
  eg.addProperty("ADBE Vector Shape - Ellipse");
  eg.addProperty("ADBE Vector Graphic - Fill");
  var ec = sp.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
  var er = H * (0.012 + 0.016 * rnd());
  ec.property("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size").setValue([er * 2, er * 2]);
  ec.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue(AEFX.rgb(rnd() < 0.5 ? P.warm : P.hot));
  var ex = W * (P.end_fade + (1 - 2 * P.end_fade) * rnd()), ph0 = rnd(), rise = H * (0.55 + 0.4 * rnd()), drift = (rnd() - 0.5) * W * 0.06;
  var pk = [], ok = [], N2 = 12;
  for (s = 0; s <= N2; s++) {
    var tt2 = D * s / N2, p = (tt2 / D + ph0) % 1;
    pk.push([tt2, [ex + drift * p + Math.sin(p * TWO * 2 + ph0 * 9) * W * 0.012, by - H * 0.1 - rise * p]]);
    ok.push([tt2, 100 * Math.sin(Math.PI * p) * (p < 0.08 ? p / 0.08 : 1)]);
  }
  AEFX.keys(sp.position, pk, false);
  AEFX.keys(sp.opacity, ok, false);
}

// organic wobble, then glow
var shake = comp.layers.addSolid([1, 1, 1], "wobble", W, H, 1); shake.adjustmentLayer = true;
var td = AEFX.fx(shake, "ADBE Turbulent Displace");
AEFX.set(td, "Amount", P.wobble); AEFX.set(td, "Size", H * 0.35); AEFX.set(td, "Complexity", 2);
var tev = AEFX.find(td, "Evolution"); tev.setValueAtTime(0, 0); tev.setValueAtTime(D, 360);
AEFX.set(td, "Cycle Evolution", 1); AEFX.set(td, "Cycle (in Revolutions)", 1);
var glow = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); glow.adjustmentLayer = true;
var gf = AEFX.fx(glow, "ADBE Glo2");
gf.property("Glow Threshold").setValue(55); gf.property("Glow Radius").setValue(H * 0.1 * P.glow); gf.property("Glow Intensity").setValue(0.65 * P.glow);
return AEFX.done(comp, '"mode":"alpha","baseline":' + P.baseline);
