// teal_dome_splash (085836): a cel water dome. A thin arc appears at the top centre (~f9), grows into an umbrella
// with teardrop drips hanging off the lower rim (f16-f24), holes open through it (f20-f30), then it breaks into
// fragments around the sphere outline (f30-f40), gone ~f41. Teal fill, thin dark outline, darker teal on the
// lower edges, white specular streaks up-left.
// PROCEDURAL: only overall size/timing/colour are measured from the reference (sphere radius over time, rim depth,
// drip count/size range, hole growth rate). Drip and hole layouts come from a seeded RNG; drips sag, detach and fall
// with gravity; the break-up is noise erosion. Nothing is traced.
// Density A = sphere disc minus underside cuts (crescent early, arches between drips later), limited by a flat reveal
// (the dome's lower rim) + teardrop drips - holes - erosion; blurred so it merges like goo, then cel thresholds.
function BUILD(V) {
  var S = 3, W = 170 * S, H = 100 * S, D = 1.84, fps = 25, tag = "td_teal_dome_v" + V;
  var f = FX.gt("teal_dome_splash");
  var TEAL = FX.rgb("4FB1B2"), SHADE = FX.rgb("1B7174"), DARK = FX.rgb("082629"), WHITE = FX.rgb("F4FBFB");
  var rnd = FX.rng(1036);
  function P(x, y) { return [x * S, y * S]; }
  // piecewise-linear lookup in a [[n, v], ...] table
  function lin(T, n) {
    if (n <= T[0][0]) return T[0][1];
    for (var i = 1; i < T.length; i++) if (n <= T[i][0]) { var a = T[i - 1], b = T[i]; return a[1] + (b[1] - a[1]) * (n - a[0]) / (b[0] - a[0]); }
    return T[T.length - 1][1];
  }
  function ellKeys(layer, g, keys) {
    var sk = [], pk = [];
    for (var i = 0; i < keys.length; i++) {
      sk.push([f(keys[i][0]), [Math.max(0.1, keys[i][3] * S), Math.max(0.1, keys[i][4] * S)]]);
      pk.push([f(keys[i][0]), P(keys[i][1], keys[i][2])]);
    }
    FX.keys(g.size, sk, false); FX.keys(layer.position, pk, false);
  }
  function ell(d, name, keys, col, wig) {
    var l = FX.shape(d, name);
    var g = FX.group(l, "ellipse", { size: [10, 10], fill: col || [1, 1, 1], wiggle: wig, seed: wig ? Math.floor(rnd() * 900) : undefined });
    ellKeys(l, g, keys);
    return l;
  }

  // ---- measured envelopes (size/timing only) ----
  // sphere: centre x, centre y, radius (top stays near y~11 while it grows)
  var SX = [[8.7, 78], [12, 79], [15, 81], [16, 80], [24, 81], [28, 80]];
  var SY = [[8.7, 11], [9, 14.5], [10, 19.5], [11, 24], [12, 35], [14, 38], [15, 41], [16, 47], [19, 49], [22, 51], [24, 51], [28, 49], [32, 48.5]];
  var SR = [[8.7, 0], [9, 3.5], [10, 8.5], [11, 13], [12, 24], [14, 27], [15, 30], [16, 37], [19, 38], [22, 40], [24, 40], [28, 37], [32, 36]];
  // lower rim depth (y of the dome's lower edge) and the underside height between drips
  var YB = [[8.7, 11], [9, 15], [10, 15.5], [11, 17], [12, 19], [14, 22.5], [15, 25], [15.5, 28], [16, 29], [19, 34], [20, 41], [21, 45], [22, 50], [24, 55], [26, 60], [28, 70], [30, 84], [32, 100]];
  var UH = [[15.5, 20.5], [19, 22], [22, 33], [24, 40], [26, 46], [28, 52], [30, 58], [32, 66], [33, 90]];
  var AR = [[15.5, 0.36], [19, 0.4], [22, 0.46], [26, 0.5], [30, 0.5], [32, 0.35], [33, 0.02]];   // arch radius / gap

  // ---- drips: 4, roughly evenly spaced along the lower rim, seeded jitter ----
  var DRIPS = [];
  for (var k = 0; k < 4; k++) {
    var fx = -0.86 + k * 0.57 + (rnd() - 0.5) * 0.3;
    var inner = Math.abs(fx) < 0.6;
    DRIPS.push({ fx: fx, ts: 14.5 + rnd() * 0.7, td: inner ? 24.6 + rnd() * 1.4 : 26.4 + rnd() * 1.6,
                 L: inner ? 26 + rnd() * 8 : 14 + rnd() * 6, w: inner ? 12 + rnd() * 4 : 8 + rnd() * 2.5 });
  }

  // shell: sphere disc minus the underside cuts
  var sh = FX.comp(tag + "_shell", W, H, fps, D, "fxlib_density");
  FX.solid(sh, "black", [0, 0, 0]);
  var sk = []; for (var n = 8.7; n <= 33; n += 0.5) sk.push([n, lin(SX, n), lin(SY, n), lin(SR, n) * 2, lin(SR, n) * 2]);
  ell(sh, "disc", sk);
  // early crescent cut: a flatter circle just under the top -> thin arc with tapered tips
  var CR = [[8.7, 6], [9, 8], [10, 14], [11, 22], [12, 34], [14, 36], [15, 36], [15.5, 0.5]];
  var CT = [[8.7, 13], [9, 14], [10, 15], [11, 16], [12, 17.5], [14, 18.5], [15, 19.5], [15.5, 30]];
  var ck = []; for (var n2 = 8.7; n2 <= 15.3; n2 += 0.5) { var r0 = lin(CR, n2); ck.push([n2, lin(SX, n2), lin(CT, n2) + r0, r0 * 2, r0 * 2]); }
  ck.push([15.5, 80, 30, 0.2, 0.2]);
  ell(sh, "crescent_cut", ck, [0, 0, 0]);
  // arches between neighbouring drips (only for gaps wide enough)
  for (var a = 0; a < 2; a++) {
    var ak = [];
    for (var n3 = 15.5; n3 <= 33; n3 += 0.5) {
      var R3 = lin(SR, n3), cx3 = lin(SX, n3);
      var x1 = cx3 + DRIPS[a].fx * R3, x2 = cx3 + DRIPS[a + 1].fx * R3, gap = x2 - x1;
      var rr = gap > 18 ? gap * lin(AR, n3) * (a === 1 ? 0.68 : 0.48) : 0.3;
      var hy = Math.max(rr, (lin(YB, n3) - lin(UH, n3) + 4) / 2);
      ak.push([n3, (x1 + x2) / 2, lin(UH, n3) + hy, rr * 2, hy * 2]);
    }
    ell(sh, "arch" + a, ak, [0, 0, 0]);
  }

  var A = FX.density(tag + "_A", W, H, fps, D, function (d) {
    var s = d.layers.add(sh); s.name = "shell";
    var rv = FX.shape(d, "reveal");     // flat ellipse whose bottom edge is the lower rim
    var rk = []; for (var i = 0; i < YB.length; i++) rk.push([YB[i][0], 80, YB[i][1] - 60, 300, 120]);
    var rg = FX.group(rv, "ellipse", { size: [10, 10], fill: [1, 1, 1] }); ellKeys(rv, rg, rk);
    FX.matte(s, rv, false);
    // teardrop relative to the bulb centre (GIF px -> comp px); detached = pointy top
    function tear(bw, bh, L) {
      var sh2 = new Shape();
      bw = Math.max(bw, 0.05); bh = Math.max(bh, 0.05);
      var tw, nw, Lt;
      if (L <= bh * 0.35) { L = bh * 0.55; tw = 0.15; nw = bw * 0.18; Lt = L; }
      else { tw = bw * 0.6 + Math.min(1, bw / 4); nw = bw * 0.26; Lt = L + 3; }
      var v = [[-tw, -Lt], [-nw, -L * 0.45], [-bw / 2, 0], [0, bh / 2], [bw / 2, 0], [nw, -L * 0.45], [tw, -Lt]];
      var it = [[0, 0], [0, -L * 0.2], [0, -bh * 0.3], [-bw * 0.28, 0], [0, bh * 0.28], [0, L * 0.2], [tw * 0.6, L * 0.25]];
      var ot = [[-tw * 0.6, L * 0.25], [0, L * 0.2], [0, bh * 0.28], [bw * 0.28, 0], [0, -bh * 0.3], [0, -L * 0.2], [0, 0]];
      function sc(q) { var o = []; for (var i = 0; i < q.length; i++) o.push([q[i][0] * S, q[i][1] * S]); return o; }
      sh2.vertices = sc(v); sh2.inTangents = sc(it); sh2.outTangents = sc(ot); sh2.closed = true;
      return sh2;
    }
    // drips: sag (ease-in-out growth), detach at td, then fall with gravity and shrink
    for (var k = 0; k < DRIPS.length; k++) {
      var q = DRIPS[k], l = FX.shape(d, "drip" + k);
      var g = FX.group(l, "path", { points: [[0, 0], [1, 0], [0, 1]], closed: true, fill: [1, 1, 1] });
      var tk = [], vk = [], pk = [], yDet = 0, xDet = 0, wDet = 0;
      for (var n = q.ts - 0.2; n <= q.td + 5.2; n += 0.5) {
        var R = lin(SR, n), cx = lin(SX, n), x = cx + q.fx * R;
        var rim = Math.min(lin(YB, n), lin(SY, n) + Math.sqrt(Math.max(0, R * R - (x - cx) * (x - cx)))) - 1;
        var u = Math.max(0, Math.min(1, (n - q.ts) / (q.td - q.ts))), sag = u * (1.6 - 0.6 * u);
        var grow = Math.min(1, Math.max(0, (n - q.ts) / 2)), bw = q.w * Math.sqrt(grow), bh = bw * 1.08;
        var L = 2 + q.L * sag, by, Ltear;
        if (n <= q.td) { by = rim + L; Ltear = by - rim; yDet = by; xDet = x; wDet = bw; }
        else {
          var dt = n - q.td; by = yDet + 1.2 * dt + 0.45 * dt * dt; x = xDet;
          bw = wDet * Math.max(0, 1 - dt / 5); bh = bw * 1.3; Ltear = 0;
        }
        tk.push(f(n)); vk.push(tear(bw, bh, Ltear)); pk.push([f(n), P(x, by)]);
      }
      g.path.setValuesAtTimes(tk, vk);
      FX.keys(l.position, pk, false);
      FX.keys(l.opacity, [[f(q.ts - 0.2), 0], [f(q.ts), 100]], false);
    }
    // holes: two main ones (upper-left, right) + specks, seeded positions on the dome, measured growth rate
    function hole(nm, fxp, fyp, t0, sizes, aspect, sink) {
      var keys = [[t0 - 0.4, 0, 0]].concat(sizes), hk = [];
      for (var i = 0; i < keys.length; i++) {
        var n = keys[i][0], R = lin(SR, n), cx = lin(SX, n), cy = lin(SY, n);
        hk.push([n, cx + fxp * R, cy - R + (fyp + (sink || 0) * Math.max(0, n - t0)) * R, keys[i][1] * aspect, keys[i][2] / aspect]);
      }
      return ell(d, nm, hk, [0, 0, 0], [2.2 * S, 3, 2, 40]);
    }
    hole("hA", -0.3 + (rnd() - 0.5) * 0.1, 0.2 + rnd() * 0.04, 20, [[20, 9, 4], [22, 14, 6], [24, 21, 13], [26, 27, 23], [28, 29, 28], [30, 34, 34], [32, 38, 36], [34, 42, 40]], 1.0, 0.045);
    hole("hB", 0.42 + (rnd() - 0.5) * 0.1, 0.36 + rnd() * 0.04, 19, [[19, 4, 3], [20, 10, 6], [22, 19, 11], [24, 26, 15], [26, 31, 18], [28, 34, 18], [30, 36, 20], [32, 42, 24], [34, 46, 28]], 0.55, 0.05);
    hole("hC", 0.25 + rnd() * 0.15, 0.25, 16, [[16, 2, 2], [18, 2.5, 2.5], [19, 0, 0]], 1);
    hole("hD", -0.1 + rnd() * 0.1, 1.15, 27, [[28, 22, 14], [30, 30, 20], [32, 34, 24]], 1);
    hole("hE", -0.25 + rnd() * 0.1, 0.22, 29.5, [[30, 12, 6], [32, 16, 8]], 1);
    // late break-up: erosion noise + the lower middle clears
    var n4 = FX.noise(d, "erode", { type: 1, noise: 4, contrast: 220, brightness: -10, scale: 6 * S, complexity: 2, seed: 5, evo: [[0, 0], [D, 140]] });
    n4.layer.blendingMode = BlendingMode.SUBTRACT;
    FX.keys(n4.layer.opacity, [[f(27), 0], [f(29), 50], [f(30), 70], [f(32), 90], [f(35), 100]], false);
    ell(d, "core", [[31, 80, 72, 0, 0], [32, 80, 72, 20, 12], [34, 80, 70, 40, 26], [36, 80, 68, 50, 34]], [0, 0, 0]);
    var soft = FX.adj(d, "soft"); FX.blur(soft, 2.4 * S);
  });

  var TL = [[f(8.7), 0.5], [f(28), 0.5], [f(30), 0.56], [f(32), 0.64], [f(34), 0.72], [f(36), 0.8], [f(38), 0.88], [f(40), 0.95], [f(41.5), 1.0]];
  function off(keys, dd) { var o = []; for (var i = 0; i < keys.length; i++) o.push([keys[i][0], Math.min(1, keys[i][1] + dd)]); return o; }
  var c = FX.comp(tag, W, H, fps, D);
  FX.cel(c, A, "outline", off(TL, -0.1), DARK, 0.02);
  FX.cel(c, A, "teal", TL, TEAL, 0.02);
  // darker teal on lower edges: A minus A shifted up
  var shd = FX.cel(c, A, "shade", TL, SHADE, 0.02);
  var shm = FX.cel(c, A, "shade_m", TL, [1, 1, 1], 0.02); shm.position.setValue([W / 2 + 0.6 * S, H / 2 - 2.6 * S]);
  FX.matte(shd, shm, true);
  // white specular streaks up-left (inset band minus itself shifted down-right)
  var hl = FX.cel(c, A, "spec", off(TL, 0.14), WHITE, 0.02);
  var hlm = FX.cel(c, A, "spec_m", off(TL, 0.14), [1, 1, 1], 0.02); hlm.position.setValue([W / 2 + 1.9 * S, H / 2 + 2.3 * S]);
  FX.matte(hl, hlm, true);
  FX.keys(hl.opacity, [[f(30), 100], [f(33), 45], [f(36), 15]], false);
  return FX.done(c);
}
