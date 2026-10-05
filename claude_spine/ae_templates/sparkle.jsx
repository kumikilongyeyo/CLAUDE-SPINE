/*TEMPLATE {"name":"sparkle","doc":"Four-point star glints that pop, spin and fade at random spots. Jewels, coins, wins.","params":{"size":512,"duration":1.2,"fps":24,"color":"FFE9A0","core_color":"FFFFFF","count":7,"min_star":0.06,"max_star":0.16,"spread":0.42,"pinch":0.18,"seed":7,"center_x":0.5,"center_y":0.5}} */
var W = P.size, comp = AEFX.comp(P.comp || "sparkle", W, W, P.fps, P.duration);
var col = AEFX.rgb(P.color), core = AEFX.rgb(P.core_color), D = P.duration, rnd = AEFX.rng(P.seed);
for (var i = 0; i < P.count; i++) {
  var l = AEFX.shape(comp, "star" + i);
  var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group").property("ADBE Vectors Group");
  var st = g.addProperty("ADBE Vector Shape - Star");
  var R = W * (P.min_star + (P.max_star - P.min_star) * rnd());
  st.property("ADBE Vector Star Type").setValue(1);
  st.property("ADBE Vector Star Points").setValue(4);
  st.property("ADBE Vector Star Outer Radius").setValue(R);
  st.property("ADBE Vector Star Inner Radius").setValue(R * P.pinch);
  var f = g.addProperty("ADBE Vector Graphic - Fill"); f.property("ADBE Vector Fill Color").setValue(i % 3 === 0 ? core : col);
  var ang = rnd() * Math.PI * 2, dist = Math.sqrt(rnd()) * W * P.spread;
  l.position.setValue([W * P.center_x + Math.cos(ang) * dist, W * P.center_y + Math.sin(ang) * dist]);
  var t0 = (D * 0.55) * rnd(), life = D * (0.3 + 0.2 * rnd()), t1 = t0 + life * 0.4, t2 = t0 + life;
  AEFX.keys(l.scale, [[t0, [0, 0]], [t1, [100, 100]], [t2, [0, 0]]], true);
  AEFX.keys(l.rotation, [[t0, -25], [t2, 35]], false);
  AEFX.keys(l.opacity, [[t0, 0], [t0 + 0.001, 100], [t2, 100]], false);
  var gl = AEFX.fx(l, "ADBE Glo2");
  gl.property("Glow Threshold").setValue(30); gl.property("Glow Radius").setValue(R * 1.1); gl.property("Glow Intensity").setValue(1.6);
  gl.property("Glow Colors").setValue(2); gl.property("Color A").setValue(col); gl.property("Color B").setValue(col);
}
return AEFX.done(comp);
