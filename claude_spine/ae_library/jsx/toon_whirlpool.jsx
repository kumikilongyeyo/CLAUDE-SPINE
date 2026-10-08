// toon_whirlpool (085849, one 158x88 panel of a full-screen cartoon WATER TRANSITION). Flat cel colours: cyan water,
// teal swirl bands, white foam, black hole. f0 black with a cyan corner; cyan sweeps in and the black hole (a disc
// on the right) shrinks while it drifts to the centre-left (f2-f14); cyan/teal spiral arms curl into it (f10-f26)
// so it reads as a black spiral; it closes to a crescent and a dot by f30; foam fades by f37; f38-f43 solid cyan.
// Built in panel units u (1 u = 1 GIF px of the 158x88 panel); S = comp px per u. All spirals are explicit polygons
// (a Twirl only bends what is inside its radius and smears the foam, so it was dropped in v3).
function BUILD(V) {
  var S = 960 / 158, W = 960, H = 540, fps = 25, D = 1.76, tag = "wp_toon_whirlpool_v" + V;
  var f = FX.gt("toon_whirlpool");
  var CYAN = FX.rgb("14D0D8"), TEAL = FX.rgb("0F8F9A"), WHITE = [1, 1, 1], BLACK = FX.rgb("070B0D");
  function P(x, y) { return [x * S, y * S]; }
  function kid(l, parent) { l.parent = parent; l.position.setValue([0, 0]); l.scale.setValue([100, 100]); l.rotation.setValue(0); return l; }
  function K(list, fn) { var o = []; for (var i = 0; i < list.length; i++) o.push([f(list[i][0]), fn(list[i])]); return o; }
  // closed spiral ribbon: centre line r0->r1 (u), angle a0->a1 (deg, + = clockwise on screen), width w (u) with
  // tapered ends (taper = fraction of the length at each end, tip width = tip).
  function ribbon(r0, r1, a0, a1, w, n, sq, tip, tapA, tapB, pw) {
    n = n || 28; sq = sq || 1; tip = tip || 0.15;
    var L = [], R = [];
    for (var i = 0; i <= n; i++) {
      var s = i / n, r = (r0 + (r1 - r0) * Math.pow(s, pw || 1)), a = (a0 + (a1 - a0) * s) * Math.PI / 180;
      var e = 1, ta = tapA === undefined ? 0.3 : tapA, tb = tapB === undefined ? 0.3 : tapB;
      if (s < ta) e = Math.sin(Math.PI / 2 * s / ta); else if (s > 1 - tb) e = Math.sin(Math.PI / 2 * (1 - s) / tb);
      var hw = (tip + (1 - tip) * Math.max(0, e)) * w / 2;
      var cx = Math.cos(a) * r, cy = Math.sin(a) * r * sq;
      L.push([(cx + Math.cos(a) * hw) * S, (cy + Math.sin(a) * hw * sq) * S]);
      R.push([(cx - Math.cos(a) * hw) * S, (cy - Math.sin(a) * hw * sq) * S]);
    }
    var pts = L; for (var k = R.length - 1; k >= 0; k--) pts.push(R[k]);
    return pts;
  }
  function addRibbon(layer, pts, fill, stroke, sw) {
    var o = { points: pts, closed: true };
    if (fill) o.fill = fill;
    if (stroke) { o.stroke = stroke; o.width = sw; }
    return FX.group(layer, "path", o);
  }

  // hole track (frame, x, y, radius) in u, measured from the reference (largest black blob per frame)
  var HT = [[0, 209, 209, 250], [1, 209, 209, 250], [2, 110, 44, 66], [4, 106, 43, 64], [6, 103, 41, 60], [8, 96, 40, 52],
            [9, 96, 40, 52], [10, 82, 48, 33], [12, 89, 49, 22], [14, 87, 50, 19], [15, 84, 47, 19], [16, 82, 46, 17.5],
            [18, 75, 42, 14.5], [20, 72, 41, 12], [22, 68, 43, 9], [24, 66, 48, 7], [26, 66, 54, 4.5], [28, 68, 58, 3], [30, 72, 59, 0.5]];
  var WC = [[f(0), P(104, 46)], [f(10), P(84, 45)], [f(16), P(78, 45)]];       // whirl centre for rings / foam

  var c = FX.comp(tag, W, H, fps, D);
  FX.solid(c, "cyan", CYAN);

  // ---- teal bands: broad spiral strokes around the whirl centre, rotating counter-clockwise, draining inward
  var ring = FX.shape(c, "teal_bands");
  // [r0, r1, a0, a1, width]
  var RB = [[112, 100, 150, 250, 13], [104, 96, -40, 40, 9], [86, 76, 200, 300, 8], [74, 64, 20, 95, 7],
            [60, 50, 130, 230, 6], [52, 44, -60, 10, 5], [40, 32, 240, 330, 4.5], [34, 28, 60, 140, 4]];
  for (var i = 0; i < RB.length; i++) {
    var g = addRibbon(ring, ribbon(RB[i][0], RB[i][1], RB[i][2], RB[i][3], RB[i][4], 30, 0.78, 0.1, 0.45, 0.45), TEAL);
  }
  FX.keys(ring.position, WC, "both");
  FX.keys(ring.rotation, [[f(0), 30], [f(43), -150]], false);
  FX.keys(ring.scale, [[f(0), [125, 125]], [f(16), [100, 100]], [f(30), [86, 86]]], false);
  FX.keys(ring.opacity, [[f(18), 100], [f(23), 50], [f(27), 0]], false);

  // ---- outer foam: thick white pills along the flow + dots
  var foam = FX.shape(c, "foam");
  var FB = [[96, 200, 14, 4.5], [88, 330, 10, 4], [78, 80, 16, 5], [70, 150, 9, 3.5], [62, 280, 18, 5], [54, 30, 12, 4],
            [46, 190, 14, 4.5], [40, 100, 10, 3.5], [100, 20, 8, 4]];
  for (var j = 0; j < FB.length; j++) addRibbon(foam, ribbon(FB[j][0], FB[j][0] - 2, FB[j][1], FB[j][1] + FB[j][2], FB[j][3] * 1.5, 12, 0.78, 0.45, 0.5, 0.5), WHITE);
  var rnd = FX.rng(17);
  for (var d = 0; d < 22; d++) {
    var rr = 14 + rnd() * 82, aa = rnd() * Math.PI * 2, ds = (0.9 + rnd() * 2.0) * S;
    var gd = FX.group(foam, "ellipse", { size: [ds * (1 + 0.6 * rnd()), ds], fill: WHITE });
    gd.xf.property("ADBE Vector Position").setValue([Math.cos(aa) * rr * S, Math.sin(aa) * rr * 0.78 * S]);
  }
  FX.keys(foam.position, WC, "both");
  FX.keys(foam.rotation, [[f(0), 40], [f(43), -170]], false);
  FX.keys(foam.scale, [[f(0), [115, 115]], [f(16), [100, 100]], [f(32), [80, 80]]], false);
  FX.keys(foam.opacity, [[f(5), 0], [f(7), 100], [f(24), 100], [f(32), 0]], false);

  // ---- the hole (100 u base diameter; layer scale = 2R %), rotating counter-clockwise
  var hole = FX.shape(c, "hole");
  FX.group(hole, "ellipse", { size: [100 * S, 100 * S], fill: BLACK, wiggle: [1.2 * S, 2.5, 0, 50], seed: 3 });
  FX.keys(hole.position, K(HT, function (r) { return P(r[1], r[2]); }), false);
  FX.keys(hole.scale, K(HT, function (r) { return [r[3] * 2, r[3] * 2]; }), false);
  FX.keys(hole.rotation, [[f(0), 0], [f(10), 0], [f(30), -170]], false);
  FX.keys(hole.opacity, [[f(30), 100], [f(30.5), 0]], "hold");
  // black streaks in the water around the hole (a long tail on the left f10-f14, thin slivers below f16-f24),
  // turning with the teal bands
  var bb = FX.shape(c, "black_bands");
  addRibbon(bb, ribbon(30, 50, 100, 245, 10, 30, 0.85, 0.08, 0.15, 0.6), BLACK);
  addRibbon(bb, ribbon(26, 34, 300, 360, 5, 20, 0.85, 0.1, 0.3, 0.5), BLACK);
  FX.keys(bb.position, WC, "both");
  FX.keys(bb.rotation, [[f(10), 0], [f(16), -40], [f(30), -110]], false);
  FX.keys(bb.scale, [[f(10), [100, 100]], [f(16), [100, 100]], [f(26), [85, 85]]], false);
  bb.opacity.setValue(0);
  FX.keys(bb.opacity, [[f(9.2), 0], [f(9.3), 100], [f(15), 100], [f(15.1), 0]], "hold");
  var bs = FX.shape(c, "black_slivers");
  addRibbon(bs, ribbon(40, 42, 60, 110, 3.5, 16, 0.85, 0.1, 0.4, 0.4), BLACK);
  addRibbon(bs, ribbon(45, 47, 125, 160, 3, 14, 0.85, 0.1, 0.4, 0.4), BLACK);
  addRibbon(bs, ribbon(36, 38, 20, 45, 2.5, 12, 0.85, 0.1, 0.4, 0.4), BLACK);
  FX.keys(bs.position, WC, "both");
  FX.keys(bs.rotation, [[f(15), 0], [f(26), -45]], false);
  FX.keys(bs.scale, [[f(15), [100, 100]], [f(26), [85, 85]]], false);
  bs.opacity.setValue(0);
  FX.keys(bs.opacity, [[f(14.9), 0], [f(15), 100], [f(24), 100], [f(25), 0]], "hold");

  // cyan arm(s) with a teal band, curling counter-clockwise (angle shrinks inward) into the disc
  var arms = FX.shape(c, "arms"); kid(arms, hole);
  function armSet(layer, AR) {
    for (var a = 0; a < AR.length; a++) {
      addRibbon(layer, ribbon(AR[a][0], AR[a][1], AR[a][2] - 9, AR[a][3] - 9, AR[a][4] * 0.5, 36, 1, 0.1, 0.12, 0.6, AR[a][5]), CYAN);
      addRibbon(layer, ribbon(AR[a][0], AR[a][1], AR[a][2], AR[a][3], AR[a][4], 36, 1, 0.1, 0.12, 0.6, AR[a][5]), TEAL);
    }
  }
  armSet(arms, [[90, 8, 262, 100, 40, 0.5]]);
  arms.opacity.setValue(0);
  FX.keys(arms.opacity, [[f(9.2), 0], [f(9.3), 100], [f(29), 100], [f(30), 0]], "hold");
  FX.keys(arms.rotation, [[f(10), 0], [f(30), -60]], false);
  var arms2 = FX.shape(c, "arms2"); kid(arms2, hole);
  armSet(arms2, [[85, 12, 80, -60, 28, 0.5]]);
  arms2.opacity.setValue(0);
  FX.keys(arms2.opacity, [[f(14.9), 0], [f(15), 100], [f(29), 100], [f(30), 0]], "hold");
  FX.keys(arms2.rotation, [[f(15), 0], [f(30), -45]], false);

  // the white blob that circles the closing hole (measured centroid + size per frame)
  var blob = FX.shape(c, "hole_blob");
  var gb = FX.group(blob, "ellipse", { size: [10 * S, 7 * S], fill: WHITE });
  var BT = [[14, 64, 24, 8.5], [16, 60, 30, 8.4], [18, 60, 41, 8.6], [20, 63, 51, 7.8], [22, 69, 55, 6.3], [24, 75, 56, 5.5],
            [26, 79, 54, 5.1], [28, 83, 51, 4.0], [30, 83, 48, 2.9], [32, 84, 46, 1.5]];
  FX.keys(blob.position, K(BT, function (r) { return P(r[1], r[2]); }), false);
  FX.keys(blob.scale, K(BT, function (r) { return [r[3] * 21, r[3] * 21]; }), false);
  FX.keys(blob.rotation, K(BT, function (r) { return -40 - (r[0] - 14) * 9; }), false);
  blob.opacity.setValue(0);
  FX.keys(blob.opacity, [[f(13.9), 0], [f(14), 100], [f(32), 100], [f(33), 0]], "hold");

  // white streak riding inside the hole (f2-f12), turning faster than the hole
  var hf = FX.shape(c, "hole_foam"); kid(hf, hole);
  addRibbon(hf, ribbon(33, 30, 0, 60, 7, 20, 1, 0.3, 0.5, 0.5), WHITE);
  addRibbon(hf, ribbon(38, 37, 150, 175, 5, 12, 1, 0.3, 0.5, 0.5), WHITE);
  FX.keys(hf.rotation, [[f(2), -110], [f(4), -125], [f(6), -150], [f(8), -175], [f(10), -150], [f(14), -90]], false);
  FX.keys(hf.opacity, [[f(1), 0], [f(2), 100], [f(12), 100], [f(15), 0]], false);

  // cyan wave sweeping in from the right edge (f4-f10)
  var wave = FX.shape(c, "wave_right");
  FX.group(wave, "ellipse", { size: [40 * S, 52 * S], fill: CYAN, wiggle: [2 * S, 2, 0, 50], seed: 8 });
  FX.keys(wave.position, [[f(3), P(186, 92)], [f(6), P(166, 76)], [f(8), P(156, 50)], [f(10), P(146, 36)]], false);
  FX.keys(wave.scale, [[f(3), [100, 100]], [f(8), [130, 125]]], false);
  FX.keys(wave.opacity, [[f(9), 100], [f(10), 0]], "hold");
  return FX.done(c);
}
