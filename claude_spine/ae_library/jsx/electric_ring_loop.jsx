// electric_ring_loop (ref "electric_sphere", 085830 top-left): a wobbly electric ring is born at the centre every
// 8 frames, grows fast then slows (r 7 -> 66 over 16 frames), breaks into dashes and fades. Seamless 0.96 s loop
// (3 births per loop; the wobble is keyed by ring AGE through Temporal Phase, so t=0 and t=0.96 match exactly).
function BUILD(V) {
  var S = 2.6, W = 150 * S, H = 154 * S, cx = 76 * S, cy = 78 * S;
  var name = "el_electric_ring_v" + V;
  var c = FX.comp(name, W, H, 25, 0.96);
  var CORE = FX.rgb("DCE6FF"), BLU = FX.rgb("6F8EFF"), DEEP = FX.rgb("2238C0");
  var P = 0.32, LIFE = 0.66, seeds = [11, 47, 83];
  var age = [[0, 7], [2, 15], [3, 20], [5, 30], [7, 36], [9, 45], [11, 52], [13, 59], [15, 64], [16.5, 66]];
  for (var b = -2; b <= 2; b++) {
    var t0 = b * P, sd = seeds[((b % 3) + 3) % 3];
    var l = FX.shape(c, "ring_" + (b + 2));
    var g = FX.group(l, "ellipse", { size: [14 * S, 14 * S], stroke: CORE, width: 1.0 * S, wigglePoints: 2, wiggle: [5 * S, 2.6, 0, 15], seed: sd });
    l.position.setValue([cx, cy]);
    var sk = [], wk = [];
    for (var i = 0; i < age.length; i++) {
      var tt = t0 + age[i][0] * 0.04, d = 2 * age[i][1] * S;
      sk.push([tt, [d, d]]);
      wk.push([tt, (1.0 + age[i][1] * 0.12) * S]);           // the wobble grows with the ring
    }
    FX.keys(g.size, sk, false);
    FX.keys(g.wSize, wk, false);
    // wobble evolves with age (not comp time): temporal phase keyed per ring
    var wig = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Filter - Roughen");
    FX.keys(wig.property("ADBE Vector Temporal Phase"), [[t0, 0], [t0 + LIFE, 1500]], false);
    l.rotation.setValue(sd * 7);
    FX.keys(l.opacity, [[t0 - 0.001, 0], [t0, 100], [t0 + 0.36, 85], [t0 + 0.52, 75], [t0 + LIFE, 0]], false);
    // break-up into dashes from age 11
    var st = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Dashes").addProperty("ADBE Vector Stroke Dash 1");
    st = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Dashes").addProperty("ADBE Vector Stroke Gap 1");
    st = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group").property("ADBE Vector Graphic - Stroke");
    var ds = st.property("ADBE Vector Stroke Dashes");
    FX.keys(ds.property("ADBE Vector Stroke Dash 1"), [[t0 + 0.42, 400 * S], [t0 + 0.48, 60 * S], [t0 + 0.56, 14 * S], [t0 + LIFE, 3 * S]], false);
    FX.keys(ds.property("ADBE Vector Stroke Gap 1"), [[t0 + 0.42, 0], [t0 + 0.48, 6 * S], [t0 + 0.56, 10 * S], [t0 + LIFE, 16 * S]], false);
    FX.keys(st.property("ADBE Vector Stroke Width"), [[t0, 1.2 * S], [t0 + 0.2, 0.85 * S], [t0 + LIFE, 0.7 * S]], false);
  }
  var g1 = FX.adj(c, "glow_tight"); FX.glow(g1, 2.5 * S, 1.4, 35, BLU, CORE);
  var g2 = FX.adj(c, "glow_wide"); FX.glow(g2, 7 * S, 1.8, 20, BLU, DEEP);
  return FX.done(c);
}
