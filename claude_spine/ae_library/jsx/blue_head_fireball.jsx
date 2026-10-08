// blue_head_fireball (085858), really a side IMPACT BLAST. f6 electric flash (orange-hot core, spiky white/blue
// outline, dashed streak to the right); f7 cyan hemispherical shell + big white fireball; f8-f11 cel fire puff grows
// to the right (white at the impact side, yellow lobes, red outlines, dark hollow); f12-f19 the fill erodes back into
// its red-orange OUTLINES (outer C arc + inner C arc), which then break into ember dots; faint dark smoke behind.
// Grey fields: O = outer silhouette (lobed head + cone back to the impact point), I = inner puff;
// A = 0.5*O + 0.5*I (blurred, turbulent-displaced) so the outer outline is the 0.25 contour and the inner one the 0.75
// contour; E = distance-from-the-outlines (|  |A-.5| - .25 | x4) + noise: the fill erodes back INTO the outlines;
// F = fragmentation of the outlines (left side first); Wf = white impact side.
function BUILD(V) {
  var S = 3, W = 136 * S, H = 124 * S;
  var D = 24 / 25, fps = 25, tag = "ib_blue_head_fireball_v" + V;
  // K(n): the render-frame time that the compare matches with GIF cycle frame n (GIF runs at ~24 fps)
  var R = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24];
  function K(n) {
    var a = Math.floor(n), fr = n - a;
    if (a >= R.length - 1) return (R[R.length - 1] + (n - R.length + 1)) / 25;
    if (a < 0) return n / 25;
    return (R[a] + (R[a + 1] - R[a]) * fr) / 25;
  }
  function P(x, y) { return [x * S, y * S]; }
  var WHITE = FX.rgb("FFFFF4"), YEL = FX.rgb("FFF27A"), ORA = FX.rgb("FF9A1E"), RED = FX.rgb("E8240E"),
      EMB = FX.rgb("FFC24A"), EMB2 = FX.rgb("FFE57A"), PLUM = FX.rgb("2D1E36"), TEAL = FX.rgb("2A8798"), RIM = FX.rgb("8FE8F4"),
      EBLUE = FX.rgb("5A78FF"), SMOKE = FX.rgb("2C2024");

  // cauliflower puff: a core disc plus lobe discs on a ring (GIF px at scale 100), blurred + displaced later
  function blobs(layer, core, angs, ring, radii) {
    FX.group(layer, "ellipse", { size: [core * 2 * S, core * 2 * S], fill: [1, 1, 1] });
    for (var q = 0; q < angs.length; q++) {
      var a = angs[q] * Math.PI / 180;
      var g = FX.group(layer, "ellipse", { size: [radii[q] * 2 * S, radii[q] * 2 * S], fill: [1, 1, 1] });
      g.xf.property("ADBE Vector Position").setValue([Math.cos(a) * ring * S, Math.sin(a) * ring * S]);
    }
  }
  // ---------------------------------------------------------------- O: outer silhouette (head + cone to the impact)
  var HK = [[6.4, 26, 58, 20, 30], [7, 38, 58, 64, 95], [8, 54, 56, 86, 84], [10, 64, 54, 97, 92], [12, 70, 51, 100, 94],
            [15, 72, 51, 103, 96], [19, 75, 50, 104, 97], [23, 77, 50, 105, 98]];
  var O = FX.density(tag + "_O", W, H, fps, D, function (d) {
    var cone = FX.shape(d, "cone"); cone.position.setValue([0, 0]);
    FX.keys(cone.opacity, [[K(6.3), 0], [K(6.4), 100]], "hold");
    var cg = FX.group(cone, "path", { points: [[14 * S, 58 * S], [26 * S, 50 * S], [26 * S, 66 * S]], closed: true, fill: [1, 1, 1] });
    var ct = [], cv = [];
    for (var i = 0; i < HK.length; i++) {
      var r = 36 * HK[i][4] / 100 * 0.82, s = new Shape();
      s.vertices = [[14 * S, 58 * S], [HK[i][1] * S, (HK[i][2] - r) * S], [HK[i][1] * S, (HK[i][2] + r) * S]]; s.closed = true;
      ct.push(K(HK[i][0])); cv.push(s);
    }
    cg.path.setValuesAtTimes(ct, cv);
    var head = FX.shape(d, "head");
    blobs(head, 22, [-120, -88, -57, -27, 3, 33, 63, 94, 124], 28, [9, 11, 11, 10, 11, 11, 10, 11, 9]);
    var pk = [], sk = [];
    for (var j = 0; j < HK.length; j++) { pk.push([K(HK[j][0]), P(HK[j][1], HK[j][2])]); sk.push([K(HK[j][0]), [HK[j][3], HK[j][4]]]); }
    FX.keys(head.position, pk, false); FX.keys(head.scale, sk, false);
    FX.keys(head.rotation, [[K(7), -10], [K(19), 8]], false);
    FX.keys(head.opacity, [[K(6.3), 0], [K(6.4), 100]], "hold");
  });
  // ---------------------------------------------------------------- I: inner puff
  var IK = [[7, 40, 58, 30, 40], [8, 50, 57, 50, 50], [10, 56, 57, 80, 85], [12, 60, 57, 92, 100], [15, 63, 58, 95, 102],
            [19, 66, 57, 97, 104], [23, 68, 57, 98, 105]];
  var I = FX.density(tag + "_I", W, H, fps, D, function (d) {
    var inn = FX.shape(d, "inner");
    blobs(inn, 12, [-78, -40, -2, 36, 74], 17, [7, 8, 8, 8, 7]);
    var pk = [], sk = [];
    for (var j = 0; j < IK.length; j++) { pk.push([K(IK[j][0]), P(IK[j][1], IK[j][2])]); sk.push([K(IK[j][0]), [IK[j][3], IK[j][4]]]); }
    FX.keys(inn.position, pk, false); FX.keys(inn.scale, sk, false);
    FX.keys(inn.rotation, [[K(7), 12], [K(19), -6]], false);
    FX.keys(inn.opacity, [[K(6.9), 0], [K(7), 100]], "hold");
  });
  function lobed(layer, seed, amt) {
    var td = FX.fx(layer, "ADBE Turbulent Displace");
    FX.set(td, "Amount", amt); FX.set(td, "Size", 5 * S); FX.set(td, "Complexity", 2);
    FX.set(td, "Random Seed", seed);
    FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 160]], false);
    FX.blur(layer, 2.6 * S);
  }
  // ---------------------------------------------------------------- A: two-plateau fire field
  var A = FX.density(tag + "_A", W, H, fps, D, function (d) {
    var lo = d.layers.add(O); lo.opacity.setValue(50); lobed(lo, 5, 35);
    var li = d.layers.add(I); li.opacity.setValue(50); li.blendingMode = BlendingMode.ADD; lobed(li, 9, 30);
  });
  // ---------------------------------------------------------------- AL: softer copy of A -> thicker outline bands
  var AL = FX.density(tag + "_AL", W, H, fps, D, function (d) { var la = d.layers.add(A); FX.blur(la, 2.2 * S); });
  // ---------------------------------------------------------------- Y: A + lobe-size noise -> yellow patches, orange between
  var Y = FX.density(tag + "_Y", W, H, fps, D, function (d) {
    d.layers.add(A);
    var n = FX.noise(d, "patch", { type: 1, noise: 4, contrast: 150, brightness: -10, scale: 6 * S, complexity: 1, seed: 12, evo: [[0, 0], [D, 150]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(40);
  });
  // ---------------------------------------------------------------- B: bead noise (where the ember lines are hot)
  var Bd = FX.density(tag + "_B", W, H, fps, D, function (d) {
    FX.noise(d, "beads", { type: 1, noise: 4, contrast: 190, brightness: 0, scale: 3 * S, complexity: 1, seed: 44, evo: [[0, 0], [D, 220]] });
  });
  // ---------------------------------------------------------------- Wf: white impact side
  var Wf = FX.density(tag + "_W", W, H, fps, D, function (d) {
    var r = FX.ramp(d, "white", 16 * S, 58 * S, 10);
    FX.rampRadius(r, 16 * S, 58 * S, [[K(6.5), 12 * S], [K(7), 42 * S], [K(8), 48 * S], [K(9), 42 * S], [K(10), 36 * S], [K(11), 24 * S], [K(12), 6], [K(13), 1]]);
    var n = FX.noise(d, "wn", { type: 1, noise: 4, contrast: 140, brightness: -20, scale: 7 * S, complexity: 1, seed: 3, evo: [[0, 0], [D, 90]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(25);
  });
  // ---------------------------------------------------------------- E: distance from the outlines + noise + hollow seed
  var E = FX.density(tag + "_E", W, H, fps, D, function (d) {
    var la = d.layers.add(A); FX.blur(la, 5 * S);
    var g1 = FX.solid(d, "half", [0.5, 0.5, 0.5]); g1.blendingMode = BlendingMode.DIFFERENCE;
    var g2 = FX.solid(d, "quarter", [0.25, 0.25, 0.25]); g2.blendingMode = BlendingMode.DIFFERENCE;
    var adj = FX.adj(d, "x4"); var lv = FX.fx(adj, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0005").setValue(0.25); lv.property("ADBE Pro Levels2-0008").setValue(0.5);
    var n = FX.noise(d, "holes", { type: 1, noise: 4, contrast: 120, brightness: 0, scale: 7 * S, complexity: 1, seed: 21, evo: [[0, 0], [D, 120]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(30);
    var r = FX.ramp(d, "seed", 50 * S, 57 * S, 10, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.ADD);
    FX.keys(FX.find(r.fx, "ADBE Ramp-0001"), [[K(7.5), P(50, 57)], [K(10), P(54, 57)], [K(14), P(58, 58)]], false);
    FX.keys(FX.find(r.fx, "ADBE Ramp-0003"), [[K(7.5), P(60, 57)], [K(8), P(68, 57)], [K(10), P(76, 57)], [K(14), P(90, 58)]], false);
    r.layer.opacity.setValue(40);
  });
  // ---------------------------------------------------------------- F: outline fragmentation (left side first)
  var F = FX.density(tag + "_F", W, H, fps, D, function (d) {
    var n = FX.noise(d, "frag", { type: 1, noise: 4, contrast: 210, brightness: 0, scale: 2.5 * S, complexity: 1, seed: 33, evo: [[0, 0], [D, 200]] });
    n.layer.opacity.setValue(100);
    // the field brightens over time against a FIXED threshold (keyed Levels thresholds did not cut here before f19)
    FX.keys(FX.find(n.fx, "Brightness"), [[K(12), -70], [K(13), -40], [K(14), -22], [K(15), -12], [K(16), -4], [K(17), 3], [K(18), 10], [K(19), 18], [K(20), 28], [K(21), 38], [K(22), 50], [K(23), 70]], false);
    var r = FX.ramp(d, "leftfirst", 10 * S, 60 * S, 10, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.ADD, true, [85 * S, 60 * S]);
    FX.keys(r.layer.opacity, [[K(10), 0], [K(13), 35], [K(16), 55], [K(19), 60]], false);
  });

  // ---------------------------------------------------------------- solid fill (eroded by E)
  var solid = FX.comp(tag + "_solid", W, H, fps, D, "fxlib_density");
  FX.cel(solid, A, "red", 0.08, RED, 0.015);
  FX.cel(solid, A, "orange", 0.15, ORA, 0.015);
  FX.celIn(solid, Y, "yellow", 0.55, YEL, 0.015, A, 0.2);
  // ---------------------------------------------------------------- outlines (stay after the fill erodes)
  var lines = FX.comp(tag + "_lines", W, H, fps, D, "fxlib_density");
  var oR = FX.celIn(lines, AL, "out_red", 0.07, RED, 0.015, AL, 0.44, true);
  var cores = FX.comp(tag + "_cores", W, H, fps, D, "fxlib_density");
  var oC = FX.celIn(cores, AL, "out_core", 0.13, EMB, 0.015, AL, 0.37, true);
  var iR = FX.celIn(lines, AL, "in_red", 0.56, RED, 0.015, AL, 0.94, true);
  var iC = FX.celIn(cores, AL, "in_core", 0.63, EMB2, 0.015, AL, 0.87, true);
  var cl0 = lines.layers.add(cores); cl0.name = "hot_cores";
  FX.matte(cl0, FX.cel(lines, Bd, "beads", 0.36, [1, 1, 1], 0.02), false);
  FX.keys(oR.opacity, [[K(10), 0], [K(12), 100]], false);
  FX.keys(iR.opacity, [[K(8), 45], [K(10), 60], [K(12), 100]], false);
  FX.keys(oC.opacity, [[K(10), 0], [K(12), 100]], false);
  FX.keys(iC.opacity, [[K(10), 0], [K(12), 100]], false);

  // ---------------------------------------------------------------- body: hollow + solid + lines + white
  var body = FX.comp(tag + "_body", W, H, fps, D, "fxlib_density");
  var plum = FX.cel(body, A, "hollow", 0.13, PLUM, 0.02);
  FX.keys(plum.opacity, [[K(7.5), 90], [K(10.5), 85], [K(12.5), 30], [K(14), 0]], false);
  var sl = body.layers.add(solid); sl.name = "solid";
  var holes = FX.cel(body, E, "holes", [[K(7.5), 0.98], [K(8), 0.84], [K(9), 0.8], [K(10), 0.77], [K(11), 0.73], [K(12), 0.69], [K(13), 0.62], [K(14), 0.5], [K(15), 0.36], [K(16), 0.22], [K(17), 0.1], [K(18), 0.02]], [1, 1, 1], 0.015);
  FX.matte(sl, holes, true);
  FX.keys(sl.opacity, [[K(15), 100], [K(17), 0]], false);   // the fill's own rims must not outlive the ember lines
  var ll = body.layers.add(lines); ll.name = "lines";
  // fragmentation cuts the outlines inside the lines comp with a Silhouette Alpha layer on top
  var frag = FX.cel(lines, F, "frag", 0.6, [1, 1, 1], 0.015); frag.blendingMode = BlendingMode.SILHOUETE_ALPHA;
  var ltd = FX.fx(ll, "ADBE Turbulent Displace"); FX.set(ltd, "Amount", 45); FX.set(ltd, "Size", 3 * S);
  FX.keys(FX.find(ltd, "Evolution"), [[0, 0], [D, 200]], false);
  FX.keys(ll.opacity, [[K(18), 100], [K(20), 70], [K(22), 30], [K(23), 0]], false);
  FX.celIn(body, Wf, "white", 0.3, WHITE, 0.04, A, 0.12);

  // ---------------------------------------------------------------- main comp
  var c = FX.comp(tag, W, H, fps, D);
  // faint dark smoke puffs behind/right of the fire
  var sm = FX.shape(c, "smoke");
  var sp = [[104, 30, 13], [112, 46, 14], [114, 64, 15], [109, 82, 13], [98, 94, 11], [82, 98, 9]];
  for (var i = 0; i < sp.length; i++) {
    var g = FX.group(sm, "ellipse", { size: [sp[i][2] * 2 * S, sp[i][2] * 2 * S], fill: SMOKE });
    g.xf.property("ADBE Vector Position").setValue(P(sp[i][0] - 68, sp[i][1] - 62));
  }
  sm.position.setValue(P(68, 62));
  FX.blur(sm, 4 * S);
  FX.keys(sm.position, [[K(8), P(60, 62)], [K(14), P(68, 62)], [K(22), P(74, 60)]], false);
  FX.keys(sm.scale, [[K(8), [60, 70]], [K(13), [95, 95]], [K(22), [108, 108]]], false);
  FX.keys(sm.opacity, [[K(8), 0], [K(11), 50], [K(18), 60], [K(21), 35], [K(23), 0]], false);

  // cyan hemispherical shell: circle minus an ellipse offset to the right, bright rim on the outer edge
  var sh = FX.shape(c, "shell");
  var rim = FX.group(sh, "ellipse", { size: [89 * S, 89 * S], stroke: RIM, width: 2 * S, trim: true });
  rim.tStart.setValue(57); rim.tEnd.setValue(93);
  var root = sh.property("ADBE Root Vectors Group");
  var grp = root.addProperty("ADBE Vector Group"); var gc = grp.property("ADBE Vectors Group");
  var e1 = gc.addProperty("ADBE Vector Shape - Ellipse"); e1.property("ADBE Vector Ellipse Size").setValue([90 * S, 90 * S]);
  var e2 = gc.addProperty("ADBE Vector Shape - Ellipse"); e2.property("ADBE Vector Ellipse Size").setValue([74 * S, 104 * S]);
  e2.property("ADBE Vector Ellipse Position").setValue([10 * S, 0]);
  var mg = gc.addProperty("ADBE Vector Filter - Merge"); mg.property("ADBE Vector Merge Type").setValue(3);
  var fl = gc.addProperty("ADBE Vector Graphic - Fill"); fl.property("ADBE Vector Fill Color").setValue(TEAL);
  sh.position.setValue(P(60, 58));
  FX.keys(sh.scale, [[K(6.6), [80, 80]], [K(7), [97, 97]], [K(10), [100, 100]], [K(14), [102, 102]]], "out");
  FX.keys(sh.opacity, [[K(6.6), 0], [K(7), 95], [K(10), 85], [K(12), 35], [K(13), 12], [K(13.6), 0]], false);

  // halo: blurred additive copies of the body behind it
  var h1 = c.layers.add(body); h1.name = "halo_wide"; FX.blur(h1, 9 * S); h1.blendingMode = BlendingMode.ADD; h1.opacity.setValue(85);
  var h2 = c.layers.add(body); h2.name = "halo_tight"; FX.blur(h2, 3 * S); h2.blendingMode = BlendingMode.ADD; h2.opacity.setValue(70);
  var bl = c.layers.add(body); bl.name = "body";

  // f6 flash: orange-hot core with an orange bloom
  var bloom = FX.shape(c, "core_bloom");
  FX.group(bloom, "ellipse", { size: [26 * S, 26 * S], fill: FX.rgb("FF5A10") });
  bloom.position.setValue(P(24, 59)); FX.blur(bloom, 6 * S); bloom.blendingMode = BlendingMode.ADD;
  FX.keys(bloom.opacity, [[K(5.5), 0], [K(5.8), 100], [K(6.6), 100], [K(7.2), 0]], false);
  var core = FX.shape(c, "core");
  FX.group(core, "ellipse", { size: [13 * S, 14 * S], fill: WHITE });
  FX.group(core, "ellipse", { size: [21 * S, 21 * S], fill: FX.rgb("FF7A20") });
  core.position.setValue(P(24, 59));
  FX.blur(core, 1 * S);
  FX.keys(core.opacity, [[K(5.5), 0], [K(5.8), 100], [K(6.5), 100], [K(6.9), 0]], false);

  // electric parts in their own comp with a blue glow (keeps the glow off the cel fire)
  var ec = FX.comp(tag + "_elec", W, H, fps, D, "fxlib_density");
  var el = FX.shape(ec, "electric");
  var pts = [[26, 44], [34, 33], [41, 38], [46, 34], [55, 39], [52, 47], [53, 53], [49, 58], [58, 61], [71, 70], [59, 67], [52, 65], [49, 75], [41, 73], [34, 82], [31, 73], [24, 67], [30, 60], [22, 54]];
  for (var q = 0; q < pts.length; q++) pts[q] = [(pts[q][0] - 38) * S, (pts[q][1] - 58) * S];
  var eg = FX.group(el, "path", { points: pts, closed: true, stroke: FX.rgb("F4F8FF"), width: 1.2 * S, fill: FX.rgb("141A48") });
  eg.fillO.setValue(15);
  el.position.setValue(P(38, 58));
  FX.keys(el.position, [[K(6), P(38, 58)], [K(7), P(50, 58)]], false);
  FX.keys(el.scale, [[K(5.5), [60, 60]], [K(6), [100, 100]], [K(7), [120, 118]]], "out");
  FX.keys(el.opacity, [[K(5.5), 0], [K(5.8), 100], [K(6.4), 100], [K(7), 45], [K(7.5), 0]], false);
  FX.keys(eg.fillO, [[K(6.4), 15], [K(7), 0]], false);
  var stk = FX.shape(ec, "streak");
  var segs = [[40, 62, 1.1], [66, 70, 0.9], [74, 77, 0.9], [81, 83, 0.9], [88, 108, 1.3]];
  for (var s2 = 0; s2 < segs.length; s2++) {
    FX.group(stk, "path", { points: [[(segs[s2][0] - 60) * S, 0], [(segs[s2][1] - 60) * S, 0]], stroke: FX.rgb("F4F8FF"), width: segs[s2][2] * S, taper: [30, 30] });
  }
  FX.keys(stk.position, [[K(5.8), P(58, 60)], [K(6), P(60, 60)], [K(7), P(66, 60)], [K(7.6), P(70, 60)]], false);
  FX.keys(stk.opacity, [[K(5.6), 0], [K(5.9), 100], [K(7), 100], [K(7.7), 0]], false);
  var rnd = FX.rng(11);
  var spk = FX.shape(ec, "sparks");
  for (var k = 0; k < 13; k++) {
    var px = k < 3 ? 104 + k * 4 : 32 + rnd() * 50, py = k < 3 ? 59 + (k % 2) * 3 : 28 + rnd() * 58;
    var sz = 0.9 + rnd() * 0.8;
    var gs = FX.group(spk, "ellipse", { size: [sz * 2 * S, sz * S], fill: FX.rgb("E8F6FF") });
    gs.xf.property("ADBE Vector Position").setValue(P(px - 68, py - 62));
  }
  spk.position.setValue(P(68, 62));
  FX.keys(spk.position, [[K(7.5), P(66, 62)], [K(13), P(72, 62)]], false);
  FX.keys(spk.opacity, [[K(7.4), 0], [K(7.8), 100], [K(11), 90], [K(13), 0]], false);
  var gA = FX.adj(ec, "glow_tight"); FX.glow(gA, 2 * S, 1.2, 40, FX.rgb("B8D4FF"), EBLUE);
  var gB = FX.adj(ec, "glow_wide"); FX.glow(gB, 7 * S, 1.6, 25, EBLUE, FX.rgb("2030C0"));
  var ecl = c.layers.add(ec); ecl.name = "electric"; ecl.blendingMode = BlendingMode.ADD;
  return FX.done(c);
}
