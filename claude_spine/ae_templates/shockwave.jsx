/*TEMPLATE {"name":"shockwave","doc":"Expanding ring with a soft flash at the centre. Impact, landing, reveal.","params":{"size":512,"duration":0.7,"fps":24,"color":"FFC040","core_color":"FFFFFF","width":0.07,"rings":2,"flash":true,"glow":1.0}} */
var W = P.size, comp = AEFX.comp(P.comp || "shockwave", W, W, P.fps, P.duration);
var col = AEFX.rgb(P.color), core = AEFX.rgb(P.core_color), D = P.duration;
for (var i = 0; i < P.rings; i++) {
  var l = AEFX.shape(comp, "ring" + i), t0 = D * 0.14 * i;
  var e = AEFX.ellipse(l, W * 0.1, null, i === 0 ? col : core, W * P.width);
  l.position.setValue([W / 2, W / 2]);
  AEFX.keys(e.size, [[t0, [W * 0.08, W * 0.08]], [D, [W * 0.92, W * 0.92]]], false);
  // fast start, easing out; the ring thins as it spreads
  var ez = new KeyframeEase(0, 85), ez0 = new KeyframeEase(0, 0.1);
  e.size.setTemporalEaseAtKey(1, [ez0, ez0], [ez, ez]);
  e.size.setTemporalEaseAtKey(2, [ez, ez], [ez0, ez0]);
  AEFX.keys(e.stroke, [[t0, W * P.width * (i ? 0.55 : 1)], [D, W * P.width * 0.1]], true);
  AEFX.keys(l.opacity, [[t0, 0], [t0 + D * 0.06, 100], [D * 0.5, 80], [D, 0]], true);
  var g = AEFX.fx(l, "ADBE Glo2");
  g.property("Glow Threshold").setValue(25); g.property("Glow Radius").setValue(W * 0.05 * P.glow); g.property("Glow Intensity").setValue(1.1 * P.glow);
}
if (P.flash) {
  var f = AEFX.radialGlow(comp, "flash", core, W / 2, W / 2, W * 0.34, W * 0.03);
  AEFX.keys(f.matte.scale, [[0, [35, 35]], [D * 0.3, [100, 100]]], true);
  AEFX.keys(f.fill.opacity, [[0, 100], [D * 0.35, 0]], true);
}
return AEFX.done(comp);
