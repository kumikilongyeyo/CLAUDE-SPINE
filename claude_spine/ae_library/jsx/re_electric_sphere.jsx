// re_electric_sphere: realistic version of el_electric_ring_v5, still a seamless 0.96 s loop. The exact comp's
// wobbly rings become crackling plasma: jagged Turbulent-Displaced filaments (evolution cycled over the loop),
// Advanced Lightning arcs riding each ring (conductivity keyed to loop time), a plasma-lamp glow at the birth point
// and blue-white bloom. Everything time-varying repeats exactly every 0.96 s.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "el_electric_ring_v5", S = 2.6, D = 0.96, P = 0.32;
  RE.purge("re_electric_sphere_v");
  var tag = "re_electric_sphere_v" + V;
  var src = RE.findComp(SRC), W = src.width, H = src.height, cx = 76 * S, cy = 78 * S;
  var CORE = FX.rgb("F2F6FF"), PALE = FX.rgb("B4C8FF"), BLU = FX.rgb("5C80FF"), DEEP = FX.rgb("2034C0");
  var pR = RE.only(SRC, tag + "_rings", function (n) { return n.indexOf("ring_") === 0; });
  var c = RE.comp(tag, W, H, D);

  // loop-safe turbulent displace: evolution runs a whole number of cycles over D
  function crackle(l, amount, size, revs, seed) {
    var td = FX.fx(l, "ADBE Turbulent Displace");
    FX.set(td, "Displacement", 1); FX.set(td, "Amount", amount); FX.set(td, "Size", size); FX.set(td, "Complexity", 3);
    FX.set(td, "Cycle Evolution", 1); FX.set(td, "Cycle (in Revolutions)", revs); FX.set(td, "Random Seed", seed);
    FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 360 * revs]], false);
    FX.find(td, "Evolution").expression = "var t = time % " + D + "; linear(t, 0, " + D + ", 0, " + (360 * revs) + ")";
    return td;
  }
  // brightness flicker along a layer: luma matte from loop-cycled noise (each call makes its own noise solid)
  function flicker(l, revs) {
    var n = FX.noise(c, l.name + "_flicker", { type: 6, noise: 3, contrast: 230, brightness: 25, scale: 12 * S, complexity: 2, seed: 41 });
    FX.set(n.fx, "Cycle Evolution", 1); FX.set(n.fx, "Cycle (in Revolutions)", revs);
    FX.find(n.fx, "Evolution").expression = "linear(time % " + D + ", 0, " + D + ", 0, " + (360 * revs) + ")";
    l.setTrackMatte(n.layer, TrackMatteType.LUMA);
  }
  // 1. plasma glow at the birth point (photo filaments, stem masked away), loop-periodic flicker
  var pl = RE.tex(c, RE.R + "electric_01.png", "plasma_core", { pos: [cx, cy] });
  pl.anchorPoint.setValue([384, 455]);
  RE.tint(pl, BLU);
  var m = pl.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var sh = new Shape(), R = 300, k = 0.5523, ax = 384, ay = 455;
  sh.vertices = [[ax, ay - R], [ax + R, ay], [ax, ay + R], [ax - R, ay]];
  sh.inTangents = [[-R * k, 0], [0, -R * k], [R * k, 0], [0, R * k]];
  sh.outTangents = [[R * k, 0], [0, R * k], [-R * k, 0], [0, -R * k]]; sh.closed = true;
  m.property("ADBE Mask Shape").setValue(sh); m.property("ADBE Mask Feather").setValue([200, 200]);
  pl.scale.setValue([16, 16]);
  pl.rotation.expression = "(time % " + D + ") / " + D + " * 360";      // one full turn per loop
  pl.opacity.expression = "var a = time % " + P + "; 8 + 75 * Math.exp(-a / 0.08) + 6 * Math.sin(2 * Math.PI * 9 * (time % " + D + ") / " + D + ")";

  // 2. plasma body: rings softened + blue bloom
  RE.light(c, pR, "ring_bloom_deep", DEEP, 10 * S, 75);
  var bb = RE.light(c, pR, "ring_bloom", BLU, 2.5 * S, 60);
  crackle(bb, 10, 6 * S, 6, 3);
  // 2b. plasma-lamp filaments as the ring material: the photo, turning once per loop, seen only through the rings
  var pt = RE.tex(c, RE.R + "electric_01.png", "ring_plasma_tex", { pos: [cx, cy] });
  pt.anchorPoint.setValue([384, 455]);
  RE.tint(pt, PALE);
  pt.scale.setValue([62, 62]);
  pt.rotation.expression = "-(time % " + D + ") / " + D + " * 360";
  pt.opacity.setValue(85);
  var ptm = c.layers.add(pR); ptm.name = "ring_plasma_tex_matte"; FX.blur(ptm, 4 * S);
  FX.matte(pt, ptm, false);
  // 3. jagged filaments: two displaced copies (fine crackle + wilder branches) and the hot core
  var fA = RE.light(c, pR, "arc_main", PALE, 0, 100);
  crackle(fA, 16, 2 * S, 8, 11);
  var fB = RE.light(c, pR, "arc_branch", PALE, 0, 60);
  crackle(fB, 30, 1.6 * S, 10, 29);
  var fC = RE.light(c, pR, "arc_core", CORE, 0, 100);
  crackle(fC, 16, 2 * S, 8, 11);
  flicker(fA, 5); flicker(fC, 5);
  var tr = FX.fx(fC, "ADBE Simple Choker"); FX.set(tr, "Choke Matte", 1.2);

  // 4. Advanced Lightning arcs riding the rings: 3 per ring, angles fixed per birth seed so ring b and b+3 match
  var angs = [[20, 150, 260], [70, 190, 310], [110, 230, 350]];
  for (var b = 0; b < 5; b++) {
    var sd = ((b - 2) % 3 + 3) % 3;
    for (var j = 0; j < 3; j++) {
      var a0 = angs[sd][j], span = 28 + j * 6;
      var l = FX.solid(c, "arc_r" + b + "_" + j, [0, 0, 0]);
      var lg = FX.fx(l, "ADBE Lightning 2");
      FX.set(lg, "Lightning Type", 2);
      var rad = 'var L = comp("' + SRC + '").layer("ring_' + b + '"); var r = L.content(1).content(1).size.value[0] / 2;';
      FX.find(lg, "Origin").expression = rad + "var a = degreesToRadians(" + a0 + "); [" + cx + " + Math.cos(a) * r, " + cy + " + Math.sin(a) * r]";
      FX.find(lg, "Contextual Control").expression = rad + "var a = degreesToRadians(" + (a0 + span) + "); [" + cx + " + Math.cos(a) * r, " + cy + " + Math.sin(a) * r]";
      FX.find(lg, "Conductivity State").expression = "Math.floor((time % " + D + ") * 25 + 0.001) * 11.3 + " + (sd * 7 + j * 3);
      FX.set(lg, "Core Radius", 1.1); FX.set(lg, "Core Opacity", 100); FX.set(lg, "Core Color", CORE);
      FX.set(lg, "Glow Radius", 9); FX.set(lg, "Glow Opacity", 60); FX.set(lg, "Glow Color", BLU);
      FX.set(lg, "Turbulence", 1.4); FX.set(lg, "Forking", 0.3); FX.set(lg, "Decay", 0.4); FX.set(lg, "Complexity", 5);
      l.opacity.expression = 'var L = comp("' + SRC + '").layer("ring_' + b + '"); var r = L.content(1).content(1).size.value[0] / 2;' +
                             'L.transform.opacity.value * linear(r, ' + (10 * S) + ', ' + (24 * S) + ', 0, 0.8)';
      l.blendingMode = BlendingMode.ADD;
    }
  }
  // 5. bloom
  var g1 = FX.adj(c, "bloom_tight"); FX.glow(g1, 2 * S, 0.6, 45, PALE, BLU);
  var g2 = FX.adj(c, "bloom_wide"); FX.glow(g2, 9 * S, 1.0, 30, BLU, DEEP);
  return FX.done(c);
}
