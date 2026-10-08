// aqua_impact (085842): f9 tiny white star spark, f10 white 3-spike starburst, f11-f13 a teal cel water blob with
// dark-outlined holes inside a spiky white electric starburst (blue glow), f14 the starburst breaks into shards,
// f15-f18 the blob becomes a broken ring of teal droplets with white sparkle dots out to r~80, gone by f22.
// PROCEDURAL: only sizes, timing and colours are measured from the reference. Lump, hole, spike, spark, strand and
// droplet layouts come from a seeded RNG; nothing is traced.
// Densities: A0 = blob silhouette (blurred seeded lumps + noise) that turns into a ring (lumps minus shrunken lumps,
// + seeded strands/droplets); Hd = seeded holes + late erosion; A = A0 - Hd; Sd = starburst (jagged star + seeded
// spikes, shattered at f14). Lumps = vector cel lumps (internal shading) inside A.
// Glow = Glow effect on a white copy of the starburst, BEHIND the cel body. Body is cut by the holes once.
function BUILD(V) {
  var S = 3, W = 160 * S, H = 138 * S, cx = 71 * S, cy = 66 * S;
  var D = 1.0, fps = 25, tag = "aq_aqua_impact_v" + V;
  var f = FX.gt("aqua_impact");
  var WHITE = FX.rgb("FBFCFB"), TEAL = FX.rgb("50B3B4"), SHADE = FX.rgb("0E6567"), MID = FX.rgb("21858A"), CYAN = FX.rgb("67C4E0"),
      DARK = FX.rgb("06171C"), VIOLET = FX.rgb("3E4EBE"), GLOW = FX.rgb("5F86D8"), DEEP = FX.rgb("21407C");
  var rnd = FX.rng(4211);
  function P(x, y) { return [x * S, y * S]; }
  function D2R(a) { return a * Math.PI / 180; }
  // blob growth (measured size over time): scale keys about the centre
  var BS = [[f(10.2), [0, 0]], [f(10.5), [40, 40]], [f(10.8), [86, 86]], [f(11), [96, 94]], [f(12), [100, 98]], [f(13), [101, 99]],
            [f(14), [118, 100]], [f(14.5), [124, 104]], [f(15), [126, 106]], [f(17), [132, 110]], [f(21), [136, 114]]];
  var BP = [[f(13), [cx, cy]], [f(15), [cx - 2 * S, cy + 1 * S]], [f(19), [cx - 4 * S, cy]]];
  // ellipse keyed in GIF px: keys [[n, x, y, w, h], ...]
  function ell(d, name, keys, blur) {
    var l = FX.shape(d, name);
    var g = FX.group(l, "ellipse", { size: [10, 10], fill: [1, 1, 1] });
    var sk = [], pk = [];
    for (var i = 0; i < keys.length; i++) {
      sk.push([f(keys[i][0]), [Math.max(0.1, keys[i][3] * S), Math.max(0.1, keys[i][4] * S)]]);
      pk.push([f(keys[i][0]), P(keys[i][1], keys[i][2])]);
    }
    FX.keys(g.size, sk, false); FX.keys(l.position, pk, false);
    if (blur) FX.blur(l, blur);
    return l;
  }
  // seeded lumps of the blob (GIF px, relative to centre, at scale 100): [dx, dy, r]
  var LU = [[0, 1, 17]];
  for (var li = 0; li < 8; li++) {
    var la = D2R(li * 45 + (rnd() - 0.5) * 24), ld = 19 + rnd() * 8;
    LU.push([Math.cos(la) * ld * 1.05, Math.sin(la) * ld, 9.5 + rnd() * 3.5]);
  }
  var la2 = D2R(rnd() * 360); LU.push([Math.cos(la2) * 9, Math.sin(la2) * 9, 10 + rnd() * 2]);
  function lumpShape(d, nm, col) {
    var b = FX.shape(d, nm);
    for (var i = 0; i < LU.length; i++) {
      var g = FX.group(b, "ellipse", { size: [LU[i][2] * 2 * S, LU[i][2] * 2 * S], fill: col });
      g.xf.property("ADBE Vector Position").setValue([LU[i][0] * S, LU[i][1] * S]);
    }
    b.position.setValue([cx, cy]);
    return b;
  }
  function scaled(keys, k) { var o = []; for (var i = 0; i < keys.length; i++) o.push([keys[i][0], [keys[i][1][0] * k, keys[i][1][1] * k]]); return o; }

  // ring phase (f14.5+): the lumpy outline becomes a band (lumps minus shrunken lumps) + seeded strands and droplets
  function RING(d) {
    var RS = [[f(14), [118, 100]], [f(14.5), [124, 104]], [f(15), [126, 106]], [f(17), [132, 110]], [f(21), [136, 114]]];
    var ro = lumpShape(d, "ring_out", [1, 1, 1]);
    FX.keys(ro.scale, RS, false); FX.keys(ro.position, BP, false);
    FX.keys(ro.opacity, [[f(14), 0], [f(14.5), 100]], false);
    FX.blur(ro, 5 * S);
    var ri = lumpShape(d, "ring_in", [0, 0, 0]);
    var K = [[14, 0.8], [15, 0.86], [17, 0.89], [19, 0.91], [21, 0.93]], rik = [];
    for (var i = 0; i < K.length; i++) {
      var base = RS[Math.min(RS.length - 1, i)][1];
      rik.push([f(K[i][0]), [base[0] * K[i][1], base[1] * K[i][1]]]);
    }
    FX.keys(ri.scale, rik, false); FX.keys(ri.position, BP, false);
    FX.keys(ri.opacity, [[f(14), 0], [f(14.5), 100]], false);
    FX.blur(ri, 5 * S);
    // strands across the inside + droplets on the band (seeded), riding the same scale
    var st = FX.shape(d, "strands");
    for (var k = 0; k < 2; k++) {
      var a0 = rnd() * 360, a1 = a0 + (k === 0 ? 110 + rnd() * 20 : 55 + rnd() * 20), rr = 33, bend = (k === 0 ? 8 : 5) * (rnd() < 0.5 ? -1 : 1);
      var p0 = [Math.cos(D2R(a0)) * rr * S, Math.sin(D2R(a0)) * rr * S], p2 = [Math.cos(D2R(a1)) * rr * S, Math.sin(D2R(a1)) * rr * S];
      var mx = (p0[0] + p2[0]) / 2, my = (p0[1] + p2[1]) / 2, ml = Math.sqrt(mx * mx + my * my) || 1;
      var p1 = [mx - mx / ml * Math.abs(bend) * S * 0.6 + (-(p2[1] - p0[1]) / (rr * 2 * S)) * bend * S, my - my / ml * Math.abs(bend) * S * 0.6 + ((p2[0] - p0[0]) / (rr * 2 * S)) * bend * S], w = 4 + rnd() * 1.2;
      var tx = (p2[0] - p0[0]) * 0.22, ty = (p2[1] - p0[1]) * 0.22;
      var g = FX.group(st, "path", { points: [p0, p1, p2], inT: [[0, 0], [-tx, -ty], [0, 0]], outT: [[0, 0], [tx, ty], [0, 0]], closed: false, stroke: [1, 1, 1], width: w * S / 1.25 });
      FX.keys(g.strokeW, [[f(14.5), w * S / 1.25], [f(17), w * 0.8 * S / 1.25], [f(19), w * 0.62 * S / 1.25], [f(21), w * 0.42 * S / 1.25], [f(22), w * 0.15 * S / 1.25]], false);
    }
    for (var j = 0; j < 7; j++) {
      var da = D2R(rnd() * 360), dr = 30 + rnd() * 5, ds = (4 + rnd() * 3) / 1.25;
      var dg = FX.group(st, "ellipse", { size: [ds * S, ds * S * (0.8 + rnd() * 0.4)], fill: [1, 1, 1] });
      dg.xf.property("ADBE Vector Position").setValue([Math.cos(da) * dr * S, Math.sin(da) * dr * S]);
    }
    st.position.setValue([cx, cy]);
    FX.keys(st.scale, RS, false); FX.keys(st.position, BP, false);
    FX.keys(st.opacity, [[f(14), 0], [f(14.5), 100]], false);
    FX.blur(st, 2 * S);
  }

  // Hd: seeded holes (white = hole), measured growth (~6 px at f11, ~10 at f12, ~20 at f14) + late erosion noise
  var Hd = FX.density(tag + "_H", W, H, fps, D, function (d) {
    var GROW = [[10.4, 0], [10.8, 1.1], [12, 1.5], [13, 1.6], [14, 2.6]], DR = [[10.4, 1], [13, 1.05], [14, 1.3]];
    for (var i = 0; i < 4; i++) {
      var a = D2R(i * 100 + 20 + (rnd() - 0.5) * 40), dist = (i === 3 ? 4 : 9 + rnd() * 9), s0 = (i === 3 ? 3.5 : 6.5 + rnd() * 3), asp = 0.6 + rnd() * 0.9;
      var keys = [];
      for (var k = 0; k < GROW.length; k++) {
        var n = GROW[k][0], dr = dist * DR[Math.min(DR.length - 1, Math.max(0, k - 2))][1];
        keys.push([n, 71 + Math.cos(a) * dr * 1.1, 66 + Math.sin(a) * dr, s0 * GROW[k][1] * Math.sqrt(asp) * 1.15, s0 * GROW[k][1] / Math.sqrt(asp)]);
      }
      var hl = ell(d, "h" + i, keys, 1.5 * S);
      hl.rotation.setValue(rnd() * 180);
      FX.keys(hl.opacity, [[f(14), 100], [f(14.5), 0]], false);
    }
    var n2 = FX.noise(d, "erode", { type: 1, noise: 4, contrast: 220, brightness: -22, scale: 7 * S, complexity: 1, seed: 33, evo: [[0, 0], [D, 90]] });
    n2.layer.blendingMode = BlendingMode.ADD;
    FX.keys(n2.layer.opacity, [[f(14.4), 0], [f(15), 40], [f(17), 60], [f(19), 85], [f(21), 100]], false);
  });

  // A0: blob silhouette (metaball lumps) that hands over to the ring; A = A0 minus holes
  var A0 = FX.density(tag + "_A0", W, H, fps, D, function (d) {
    var b = lumpShape(d, "blob", [1, 1, 1]);
    FX.keys(b.scale, BS, false); FX.keys(b.position, BP, false);
    FX.keys(b.opacity, [[f(14), 100], [f(14.5), 0]], false);
    FX.blur(b, 5 * S);
    RING(d);
    var n = FX.noise(d, "lobes", { type: 1, noise: 4, contrast: 140, brightness: -30, scale: 10 * S, complexity: 2, seed: 7, evo: [[0, 0], [D, 120]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(35);
  });
  var A = FX.density(tag + "_A", W, H, fps, D, function (d) {
    var a0 = d.layers.add(A0); a0.name = "blob";
    var h = d.layers.add(Hd); h.name = "holes"; h.blendingMode = BlendingMode.SUBTRACT;
  });

  // lumps: vector cel lumps (shade body + offset teal + spec) that give the blob its internal structure
  var Lm = FX.comp(tag + "_lumps", W, H, fps, D, "fxlib_density");
  var lb = FX.shape(Lm, "lumps");
  for (var q2 = 0; q2 < LU.length; q2++) {
    var r = LU[q2][2], ox = LU[q2][0] * S, oy = LU[q2][1] * S;
    var sp = FX.group(lb, "ellipse", { size: (q2 % 3 === 0) ? [r * 0.4 * S, r * 0.2 * S] : [0.1, 0.1], fill: WHITE });
    sp.xf.property("ADBE Vector Position").setValue([ox - r * 0.42 * S, oy - r * 0.5 * S]);
    sp.xf.property("ADBE Vector Rotation").setValue(-35);
    var tl = FX.group(lb, "ellipse", { size: [r * 1.86 * S, r * 1.8 * S], fill: TEAL });
    tl.xf.property("ADBE Vector Position").setValue([ox - r * 0.1 * S, oy - r * 0.14 * S]);
    var bs = FX.group(lb, "ellipse", { size: [r * 2 * S, r * 2 * S], fill: MID });
    bs.xf.property("ADBE Vector Position").setValue([ox, oy]);
  }
  lb.position.setValue([cx, cy]);
  FX.keys(lb.scale, BS, false); FX.keys(lb.position, BP, false);

  // Sd: electric starburst = jagged star + seeded long spikes (measured length range); shattered at f14
  var Sd = FX.density(tag + "_S", W, H, fps, D, function (d) {
    var s = FX.shape(d, "rim");
    FX.group(s, "star", { points: 26, r1: 48 * S, r2: 38 * S, fill: [1, 1, 1], wiggle: [4 * S, 10, 4, 20] });
    s.position.setValue([cx, cy]);
    FX.keys(s.scale, [[f(10.2), [0, 0]], [f(10.5), [40, 40]], [f(10.8), [84, 82]], [f(11), [96, 90]], [f(12), [100, 94]], [f(13), [100, 94]], [f(14), [110, 100]]], false);
    FX.keys(s.rotation, [[f(10.5), 0], [f(14), 8]], false);
    FX.blur(s, 0.8 * S);
    var spk = FX.shape(d, "spikes"), rot0 = rnd() * 36;
    for (var i = 0; i < 10; i++) {
      var ang = D2R(rot0 + i * 36 + (rnd() - 0.5) * 22), len = (i % 3 === 0) ? 64 + rnd() * 8 : 50 + rnd() * 10, hw = 2.5 + rnd() * 1.2, rb = 34;
      var ux = Math.cos(ang), uy = Math.sin(ang);
      FX.group(spk, "path", { points: [[(ux * rb - uy * hw) * S, (uy * rb + ux * hw) * S], [ux * len * S, uy * len * 0.95 * S], [(ux * rb + uy * hw) * S, (uy * rb - ux * hw) * S]], closed: true, fill: [1, 1, 1] });
    }
    spk.position.setValue([cx, cy]);
    FX.keys(spk.scale, [[f(10.2), [0, 0]], [f(10.5), [40, 40]], [f(10.8), [86, 86]], [f(11), [95, 95]], [f(12), [100, 100]], [f(13), [100, 100]], [f(14), [114, 114]]], false);
    FX.keys(spk.rotation, [[f(10.5), -2], [f(14), 4]], false);
    FX.blur(spk, 0.5 * S);
    // shatter: noise subtract + centre clear
    var n = FX.noise(d, "shatter", { type: 1, noise: 3, contrast: 260, brightness: 22, scale: 5 * S, complexity: 2, seed: 12, evo: [[0, 0], [D, 200]] });
    n.layer.blendingMode = BlendingMode.SUBTRACT;
    FX.keys(n.layer.opacity, [[f(13.1), 0], [f(13.6), 100]], false);
    var rr = FX.ramp(d, "clear", cx, cy, 10, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.SUBTRACT);
    FX.rampRadius(rr, cx, cy, [[f(13.1), 10 * S], [f(13.6), 50 * S]]);
    FX.keys(rr.layer.opacity, [[f(13.1), 0], [f(13.6), 100]], false);
  });

  // spark f9-f10: round core + seeded thin arms (3 long ~28 px as measured, 1 short)
  var sa0 = rnd() * 360;
  var arms = [[sa0, 27 + rnd() * 3], [sa0 + 115 + (rnd() - 0.5) * 30, 27 + rnd() * 3], [sa0 + 235 + (rnd() - 0.5) * 30, 27 + rnd() * 3], [sa0 + 55 + (rnd() - 0.5) * 20, 13 + rnd() * 3]];
  function spark(comp, nm, col) {
    var l = FX.shape(comp, nm);
    FX.group(l, "ellipse", { size: [12 * S, 12 * S], fill: col });
    for (var i = 0; i < arms.length; i++) {
      var ux = Math.cos(D2R(arms[i][0])), uy = Math.sin(D2R(arms[i][0])), hw = arms[i][1] > 20 ? 3.2 : 2.4, rb = 3;
      FX.group(l, "path", { points: [[(ux * rb - uy * hw) * S, (uy * rb + ux * hw) * S], [ux * arms[i][1] * S, uy * arms[i][1] * S], [(ux * rb + uy * hw) * S, (uy * rb - ux * hw) * S]], closed: true, fill: col });
    }
    l.position.setValue(P(71, 65));
    FX.keys(l.scale, [[f(8.85), [30, 30]], [f(9), [40, 40]], [f(10), [100, 100]], [f(10.7), [112, 112]]], false);
    FX.keys(l.opacity, [[f(8.84), 0], [f(8.86), 100], [f(10.5), 100], [f(10.9), 0]], false);
    return l;
  }

  // VZ: blue-violet zone between the white rim and the blob: dilated blob x radial streaks (polar noise)
  var ST = FX.density(tag + "_streak", W, H, fps, D, function (d) {
    var n = FX.noise(d, "rays", { type: 1, noise: 3, contrast: 260, brightness: -10, sw: 6, sh: 900, complexity: 1, seed: 19, evo: [[0, 0], [D, 300]] });
    var pc = FX.fx(n.layer, "ADBE Polar Coordinates");
    FX.set(pc, "Interpolation", 1); FX.set(pc, "Type of Conversion", 1);
  });
  var VZ = FX.density(tag + "_VZ", W, H, fps, D, function (d) {
    var a = d.layers.add(A0); a.name = "blob"; FX.blur(a, 7 * S);
    var lv = FX.fx(a, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0005").setValue(0.35);
    var st = d.layers.add(ST); st.name = "rays"; st.blendingMode = BlendingMode.MULTIPLY;
    st.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([W / 2, H / 2]); st.position.setValue([cx, cy]); st.scale.setValue([125, 125]);
  });

  // body: starburst + blob, cut by holes once
  var body = FX.comp(tag + "_body", W, H, fps, D, "fxlib_density");
  var wl = FX.cel(body, Sd, "white", 0.5, WHITE, 0.03);
  FX.keys(wl.opacity, [[f(14), 100], [f(14.5), 0]], false);
  var vi = FX.celIn(body, VZ, "violet", 0.3, VIOLET, 0.04, Sd, 0.5);
  FX.keys(vi.opacity, [[f(13), 100], [f(14), 0]], false);
  var cy1 = FX.celIn(body, A, "cyan", 0.36, CYAN, 0.03, Sd, 0.5);
  FX.keys(cy1.opacity, [[f(13), 100], [f(14), 0]], false);
  var TL = [[f(10.2), 0.5], [f(14), 0.5], [f(15), 0.55], [f(17), 0.64], [f(19), 0.7], [f(20), 0.75], [f(21), 0.82], [f(22), 1.0]];
  function off(keys, dd) { var o = []; for (var i = 0; i < keys.length; i++) o.push([keys[i][0], Math.min(1, keys[i][1] + dd)]); return o; }
  FX.cel(body, A, "outline", off(TL, -0.09), DARK, 0.02);
  FX.cel(body, A, "teal", TL, TEAL, 0.02);
  var ll = body.layers.add(Lm); ll.name = "lumps";
  var llm = FX.cel(body, A, "lumps_m", TL, [1, 1, 1], 0.02);
  FX.matte(ll, llm, false);
  FX.keys(ll.opacity, [[f(13.5), 42], [f(14.5), 0]], false);
  // shade crescent on the lower-right of every edge
  var sh = FX.cel(body, A, "shade", TL, SHADE, 0.02);
  var shm = FX.cel(body, A, "shade_m", TL, [1, 1, 1], 0.02); shm.position.setValue([W / 2 - 1.5 * S, H / 2 - 2 * S]);
  FX.matte(sh, shm, true);
  // cyan rim light up-left, white specular inset
  var hl = FX.cel(body, A, "rimlight", off(TL, 0.04), CYAN, 0.02);
  var hlm = FX.cel(body, A, "rimlight_m", off(TL, 0.04), [1, 1, 1], 0.02); hlm.position.setValue([W / 2 + 1.2 * S, H / 2 + 1.2 * S]);
  FX.matte(hl, hlm, true);
  var sp2 = FX.cel(body, A, "spec", off(TL, 0.16), WHITE, 0.02);
  var spm = FX.cel(body, A, "spec_m", off(TL, 0.16), [1, 1, 1], 0.02); spm.position.setValue([W / 2 + 1 * S, H / 2 + 1.4 * S]);
  FX.matte(sp2, spm, true);
  FX.keys(sp2.opacity, [[f(14), 100], [f(15), 0]], false);

  // glow source: white starburst + spark, Glow effect, behind the body
  var gs = FX.comp(tag + "_glowsrc", W, H, fps, D, "fxlib_density");
  var gw = FX.cel(gs, Sd, "white", 0.5, WHITE, 0.03);
  FX.keys(gw.opacity, [[f(14), 100], [f(14.5), 0]], false);
  var gcut = FX.cel(gs, A0, "blob_cut", 0.3, [1, 1, 1], 0.02); FX.matte(gw, gcut, true);
  spark(gs, "spark", WHITE);

  // sparkle dots (own comp with glow)
  var spc = FX.comp(tag + "_sparks", W, H, fps, D, "fxlib_density");
  var rnd = FX.rng(77);
  for (var k = 0; k < 46; k++) {
    var a = rnd() * Math.PI * 2, r0 = 20 + rnd() * 56, sz = 1.3 + rnd() * rnd() * 3.5;
    var drift = 1.03 + rnd() * 0.08;
    var dl = FX.shape(spc, "dot" + k);
    FX.group(dl, "ellipse", { size: [sz * S, sz * S], fill: WHITE });
    var t0 = f(13.6 + rnd() * 1.0), t1 = Math.max(f(16.8 + rnd() * 3.4), t0 + 0.2);
    FX.keys(dl.position, [[t0, P(70 + Math.cos(a) * r0 * 0.9, 66 + Math.sin(a) * r0 * 0.86)], [t1, P(70 + Math.cos(a) * r0 * drift, 66 + Math.sin(a) * r0 * 0.95 * drift)]], "out");
    FX.keys(dl.opacity, [[t0 - 0.01, 0], [t0, 100], [t1 - 0.12, 90], [t1, 0]], false);
  }
  var sg = FX.adj(spc, "glow"); FX.glow(sg, 4 * S, 3.2, 20, GLOW, DEEP);

  // final comp
  var c = FX.comp(tag, W, H, fps, D);
  var gl = c.layers.add(gs); gl.name = "glow";
  FX.glow(gl, 6 * S, 2.4, 20, GLOW, DEEP);
  var g2 = FX.fx(gl, "ADBE Glo2"); FX.set(g2, "Glow Threshold", 20); FX.set(g2, "Glow Radius", 2 * S); FX.set(g2, "Glow Intensity", 0.5);
  FX.set(g2, "Glow Colors", 2); FX.set(g2, "Color A", FX.rgb("B8D0FF")); FX.set(g2, "Color B", GLOW);
  var fl = FX.shape(c, "spark_flash"); FX.group(fl, "ellipse", { size: [26 * S, 26 * S], fill: FX.rgb("86AAF2") }); fl.position.setValue(P(71, 65));
  FX.blur(fl, 6 * S);
  FX.keys(fl.scale, [[f(8.7), [10, 10]], [f(9), [45, 45]], [f(10), [100, 100]], [f(11), [140, 140]]], false);
  FX.keys(fl.opacity, [[f(8.84), 0], [f(8.9), 100], [f(10.2), 100], [f(11), 0]], false);
  spark(c, "spark", WHITE);
  var bl = c.layers.add(body); bl.name = "body";
  FX.keys(bl.opacity, [[f(19), 100], [f(21), 85], [f(22.5), 0]], false);
  var cut = FX.cel(c, Hd, "hole_cut", 0.6, [1, 1, 1], 0.02);
  FX.matte(bl, cut, true);
  var sl = c.layers.add(spc); sl.name = "sparks";
  return FX.done(c);
}
