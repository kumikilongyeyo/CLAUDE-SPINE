// electric_star: a knot of wiggly electric bolts at the centre (f2..f5) explodes into ~11 squiggles that fly out
// to r~80 (ease out), curling and shortening, then wink out (f13) leaving faint sparks. Blue-white core, blue glow.
function BUILD(V) {
  var S = 2.4, W = 226 * S, H = 207 * S, cx = 109 * S, cy = 108 * S;
  var name = "es_electric_star_v" + V;
  var c = FX.comp(name, W, H, 25, 0.96);
  var f = FX.gt("electric_star");
  var CORE = FX.rgb("C9D7FF"), BLU = FX.rgb("6E8CFF"), DEEP = FX.rgb("2A3CC8");
  var rnd = FX.rng(21);
  // a squiggle: polyline of n points along +x, perpendicular jitter, smooth tangents
  function squiggle(len, n, amp) {
    var v = [], it = [], ot = [];
    for (var i = 0; i < n; i++) {
      var x = len * i / (n - 1) - len / 2, y = (i === 0 || i === n - 1) ? 0 : (rnd() * 2 - 1) * amp;
      v.push([x, y]);
      var tx = len / (n - 1) * 0.35; it.push([-tx, 0]); ot.push([tx, 0]);
    }
    return { v: v, it: it, ot: ot };
  }
  function bolt(nm, len, n, amp, wid) {
    var l = FX.shape(c, nm), sq = squiggle(len, n, amp);
    var g = FX.group(l, "path", { points: sq.v, inT: sq.it, outT: sq.ot, stroke: CORE, width: wid, taper: [30, 30], wiggle: [amp * 0.35, 3, 6, 40], seed: Math.floor(rnd() * 999) });
    return { l: l, g: g };
  }
  // 1. the knot: 8 short bolts tangled around the centre (f2..f5)
  for (var i = 0; i < 8; i++) {
    var a = rnd() * 360, ar = a * Math.PI / 180, r = (6 + rnd() * 14) * S;
    var b = bolt("knot" + i, (12 + rnd() * 10) * S, 5, 4 * S, 1.8 * S);
    b.l.position.setValue([cx + Math.cos(ar) * r, cy + Math.sin(ar) * r]);
    b.l.rotation.setValue(a + 90 + (rnd() - 0.5) * 60);
    FX.keys(b.l.scale, [[f(1.6), [40, 40]], [f(3), [100, 100]], [f(5), [120, 120]]], false);
    FX.keys(b.l.opacity, [[f(1.5), 0], [f(1.7), 100], [f(5), 100], [f(6), 0]], false);
    FX.keys(b.l.position, [[f(1.6), [cx + Math.cos(ar) * r * 0.4, cy + Math.sin(ar) * r * 0.4]], [f(5.5), [cx + Math.cos(ar) * r * 2.2, cy + Math.sin(ar) * r * 2.2]]], "out");
  }
  // 2. the flying squiggles: 11 around, each a bolt oriented roughly ALONG its ray with a curl, flying r 18 -> 82
  var N = 11;
  for (var k = 0; k < N; k++) {
    var ak = k * 360 / N + (rnd() - 0.5) * 14, akr = ak * Math.PI / 180;
    var r1 = (74 + rnd() * 10) * S, t1 = f(12 + rnd() * 2);
    var bb = bolt("ray" + k, (22 + rnd() * 8) * S, 6, 7 * S, 1.5 * S);
    FX.keys(bb.l.position, [[f(2.6), [cx + Math.cos(akr) * 16 * S, cy + Math.sin(akr) * 16 * S]], [f(4), [cx + Math.cos(akr) * 36 * S, cy + Math.sin(akr) * 36 * S]], [f(8), [cx + Math.cos(akr) * r1 * 0.82, cy + Math.sin(akr) * r1 * 0.82]], [t1, [cx + Math.cos(akr) * r1, cy + Math.sin(akr) * r1]]], "out");
    bb.l.rotation.setValue(ak + (rnd() - 0.5) * 90);
    FX.keys(bb.l.scale, [[f(2.6), [70, 70]], [f(5), [110, 110]], [f(9), [80, 80]], [t1, [40, 40]]], false);
    FX.keys(bb.l.opacity, [[f(2.8), 0], [f(3.2), 100], [t1 - 0.1, 100], [t1, 0]], false);
    // a small companion fleck that trails each squiggle
    var fl = FX.shape(c, "fleck" + k);
    FX.group(fl, "ellipse", { size: [2 * S, 2 * S], fill: CORE });
    FX.keys(fl.position, [[f(5), [cx + Math.cos(akr + 0.2) * 30 * S, cy + Math.sin(akr + 0.2) * 30 * S]], [f(16), [cx + Math.cos(akr + 0.2) * (r1 + 14 * S), cy + Math.sin(akr + 0.2) * (r1 + 14 * S)]]], "out");
    FX.keys(fl.opacity, [[f(5), 0], [f(5.3), 70], [f(11), 40], [f(13.5), 0]], false);
  }
  // 3. light: tight white-blue + wide deep blue
  var g1 = FX.adj(c, "glow_tight"); FX.glow(g1, 3 * S, 1.0, 40, BLU, BLU);
  var g2 = FX.adj(c, "glow_wide"); var gl2 = FX.glow(g2, 9 * S, 1.6, 25, BLU, DEEP);
  FX.keys(FX.find(gl2, "Glow Intensity"), [[f(2), 1.6], [f(5), 1.4], [f(10), 0.9], [f(14), 0.5]], false);
  return FX.done(c);
}
