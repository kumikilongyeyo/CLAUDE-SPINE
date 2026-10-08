// re_electric_star: realistic version of es_electric_star_v4 (same size/timing; every bolt follows the exact comp's
// squiggle layers through expressions). Real branching Advanced Lightning bolts flying out, a plasma-lamp photo
// (electric_01) glowing at the core during the knot, blue-white bloom.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "es_electric_star_v4", S = 2.4, D = 0.96;
  RE.purge("re_electric_star_v");
  var tag = "re_electric_star_v" + V;
  var src = RE.findComp(SRC), W = src.width, H = src.height, cx = 109 * S, cy = 108 * S;
  var f = FX.gt("electric_star");
  var CORE = FX.rgb("EEF3FF"), PALE = FX.rgb("B8CCFF"), BLU = FX.rgb("5A7DFF"), DEEP = FX.rgb("2436C8");
  var rnd = FX.rng(5);
  var c = RE.comp(tag, W, H, D);

  // 1. plasma-lamp photo at the core while the knot forms, flickering, filaments only (stem masked away)
  for (var p = 0; p < 2; p++) {
    var pl = RE.tex(c, RE.R + "electric_01.png", "plasma_photo" + p, { pos: [cx, cy] });
    pl.anchorPoint.setValue([384, 455]);
    RE.tint(pl, p ? PALE : BLU);
    var m = pl.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var sh = new Shape(), R = 330, k = 0.5523, ax = 384, ay = 455;
    sh.vertices = [[ax, ay - R], [ax + R, ay], [ax, ay + R], [ax - R, ay]];
    sh.inTangents = [[-R * k, 0], [0, -R * k], [R * k, 0], [0, R * k]];
    sh.outTangents = [[R * k, 0], [0, R * k], [-R * k, 0], [0, -R * k]]; sh.closed = true;
    m.property("ADBE Mask Shape").setValue(sh); m.property("ADBE Mask Feather").setValue([220, 220]);
    pl.rotation.setValue(p * 150 + 20);
    FX.keys(pl.scale, [[f(1.4), [12, 12]], [f(3), [28, 28]], [f(5), [36, 36]], [f(7), [44, 44]]], false);
    FX.keys(pl.opacity, [[f(1.3), 0], [f(2), 100], [f(4.5), 100], [f(7.5), 0]], false);
    pl.opacity.expression = "value * (0.7 + 0.3 * Math.sin(time * 140 + " + (p * 2) + "))";
  }
  var core = RE.tex(c, RE.K + "light_01.png", "core_glow", { pos: [cx, cy] });
  RE.fill(core, BLU);
  FX.keys(core.scale, [[f(1.4), [10, 10]], [f(3), [30, 30]], [f(6), [40, 40]]], false);
  FX.keys(core.opacity, [[f(1.3), 0], [f(2.5), 50], [f(4), 25], [f(5), 0]], false);

  // 2. lightning bolts riding the exact layers. Strike type, origin/target along the bolt's radial direction.
  function bolt(layerName, lenMul, coreR, glowR, seed, extra) {
    var l = FX.solid(c, "bolt_" + layerName, [0, 0, 0]);
    var lg = FX.fx(l, "ADBE Lightning 2");
    FX.set(lg, "Lightning Type", 2);
    var ref = 'var L = comp("' + SRC + '").layer("' + layerName + '"); var p = L.transform.position.value;' +
              'var s = L.transform.scale.value[0] / 100; var h = ' + lenMul + ' * s / 2;' +
              'var v = [p[0] - ' + cx + ', p[1] - ' + cy + ']; var n = Math.sqrt(v[0]*v[0] + v[1]*v[1]) || 1;' +
              'var a = Math.atan2(v[1], v[0]) + ' + ((rnd() - 0.5) * 0.9) + '; var u = [Math.cos(a), Math.sin(a)];';
    FX.find(lg, "Origin").expression = ref + "[p[0] - u[0] * h, p[1] - u[1] * h]";
    FX.find(lg, "Contextual Control").expression = ref + "[p[0] + u[0] * h, p[1] + u[1] * h]";
    FX.find(lg, "Conductivity State").expression = "Math.floor(time * 25) * 13.7 + " + seed;
    FX.set(lg, "Core Radius", coreR); FX.set(lg, "Core Opacity", 100); FX.set(lg, "Core Color", CORE);
    FX.set(lg, "Glow Radius", glowR); FX.set(lg, "Glow Opacity", 45); FX.set(lg, "Glow Color", BLU);
    FX.set(lg, "Turbulence", extra.turb || 1.6); FX.set(lg, "Forking", extra.fork || 0.35); FX.set(lg, "Decay", 0.6);
    FX.set(lg, "Complexity", 6); FX.set(lg, "Min. Forkdistance", 30);
    l.opacity.expression = 'comp("' + SRC + '").layer("' + layerName + '").transform.opacity.value';
    l.blendingMode = BlendingMode.ADD;
    return l;
  }
  for (var i = 0; i < 8; i++) bolt("knot" + i, 26 * S, 1.0, 6, i * 31, { turb: 1.3, fork: 0.15 });
  for (var r = 0; r < 11; r++) bolt("ray" + r, 36 * S, 1.1, 7, 100 + r * 17, { turb: 1.2, fork: 0.3 });

  // 2b. discharge from the core while the knot bursts: 6 short strikes reaching out to the flying bolts
  for (var o = 0; o < 6; o++) {
    var oa = (o * 60 + rnd() * 40) * Math.PI / 180;
    var om = FX.solid(c, "core_discharge" + o, [0, 0, 0]);
    var og = FX.fx(om, "ADBE Lightning 2");
    FX.set(og, "Lightning Type", 2); FX.set(og, "Origin", [cx, cy]);
    FX.keys(FX.find(og, "Contextual Control"), [[f(2), [cx + Math.cos(oa) * 8 * S, cy + Math.sin(oa) * 8 * S]], [f(3.5), [cx + Math.cos(oa) * 28 * S, cy + Math.sin(oa) * 28 * S]],
                                               [f(5), [cx + Math.cos(oa) * 42 * S, cy + Math.sin(oa) * 42 * S]]], "out");
    FX.find(og, "Conductivity State").expression = "Math.floor(time * 25) * 9.1 + " + (o * 5);
    FX.set(og, "Core Radius", 0.8); FX.set(og, "Core Opacity", 100); FX.set(og, "Core Color", CORE);
    FX.set(og, "Glow Radius", 5); FX.set(og, "Glow Opacity", 45); FX.set(og, "Glow Color", BLU);
    FX.set(og, "Turbulence", 1.3); FX.set(og, "Forking", 0.25); FX.set(og, "Decay", 0.5); FX.set(og, "Complexity", 6); FX.set(og, "Min. Forkdistance", 30);
    FX.keys(om.opacity, [[f(2), 0], [f(2.6), 90], [f(4.2), 60], [f(5.5), 0]], false);
    om.blendingMode = BlendingMode.ADD;
  }
  // 3. flecks: tiny white-blue sparks (the exact flecks) with a blur trail
  var pF = RE.only(SRC, tag + "_flecks", function (n) { return n.indexOf("fleck") === 0; });
  for (var q = 1; q <= pF.numLayers; q++) pF.layer(q).motionBlur = true;
  pF.motionBlur = true; pF.shutterAngle = 270;
  RE.light(c, pF, "fleck_glow", BLU, 3 * S, 100);
  RE.light(c, pF, "fleck_core", CORE, 0, 100);

  // 4. a cold flash when the knot bursts (f2.6..f4)
  var fl = RE.tex(c, RE.K + "flare_01.png", "burst_flash", { pos: [cx, cy] });
  RE.fill(fl, PALE);
  FX.keys(fl.scale, [[f(2), [20, 20]], [f(3), [70, 70]], [f(5), [40, 40]]], false);
  FX.keys(fl.opacity, [[f(2), 0], [f(2.8), 90], [f(4), 50], [f(6), 0]], false);

  // 5. bloom: tight blue-white + wide deep blue, strongest on the knot
  var g1 = FX.adj(c, "bloom_tight"); FX.glow(g1, 2 * S, 0.45, 55, PALE, BLU);
  var g2 = FX.adj(c, "bloom_wide"); var gl2 = FX.glow(g2, 12 * S, 0.8, 35, BLU, DEEP);
  FX.keys(FX.find(gl2, "Glow Intensity"), [[f(2), 1.2], [f(5), 0.9], [f(10), 0.7], [f(14), 0.5]], false);
  return FX.done(c);
}
