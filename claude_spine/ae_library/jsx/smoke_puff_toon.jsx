// smoke_puff_toon (085754), PROCEDURAL cel smoke (the traced reference build is smoke_puff_toon_traced.jsx).
// Five puffs over the whole 900x500 GIF frame: a rising central column, a sideways wisp on the right, three wisps on
// the left. Each puff is a cluster of discs + pointed tail triangles (white on black), turbulent-displaced and blurred
// into a grey density field S; a 0.5 threshold gives the silhouette (shade #8D615E), a copy of S nudged up-left plus
// noise gives the light tone (#BA8C7A) inside it, a blurred low threshold gives the dark smoky base. Erosion: holes
// where E = (heavily blurred S: puff interiors first) + blob noise rises above a threshold that falls over time, so the
// puffs hollow out and leave thin curved rims (curls) that then vanish. S = 1.2, 25 fps, 12 frames (0.48 s).
function BUILD(V) {
  var S = 1.2, W = 900 * S, H = 500 * S, fps = 25, NF = 12, D = NF / fps, tag = "sp_smoke_puff_toon_v" + V;
  // K(n): render time at which GIF frame n is compared (the cycle's 15 GIF frames at ~33 fps onto 12 frames)
  var KM = [[0, 0], [1, 1], [3, 2], [4, 3], [5, 4], [6, 5], [8, 6], [9, 7], [10, 8], [11, 9], [13, 10], [14, 11]];
  function K(n) {
    for (var i = 0; i < KM.length - 1; i++)
      if (n <= KM[i + 1][0]) return (KM[i][1] + (KM[i + 1][1] - KM[i][1]) * (n - KM[i][0]) / (KM[i + 1][0] - KM[i][0])) / fps;
    return (KM[KM.length - 1][1] + (n - 14)) / fps;
  }
  function P(x, y) { return [x * S, y * S]; }
  var LIGHT = FX.rgb("BA8C7A"), SHADE = FX.rgb("8D615E"), HAZE = FX.rgb("4A2E30");

  // puffs in GIF px: c = centre (scale/rise pivot), e = discs [x, y, rx, ry], t = tail triangles, mv = motion keys
  // [gifFrame, dx, dy, scale%]
  var PUFFS = [
    { name: "column", c: [455, 240],
      e: [[450, 158, 13, 12], [427, 205, 22, 22], [480, 205, 21, 21], [452, 190, 18, 16], [457, 253, 11, 18], [450, 298, 10, 24], [452, 322, 14, 7], [507, 257, 8, 14]],
      t: [[[478, 276], [492, 248], [522, 236]]],
      mv: [[0, 0, 8, 96], [2, 0, 0, 110], [5, -2, -6, 114], [9, -3, -10, 115], [14, -4, -14, 115]] },
    { name: "right", c: [705, 295],
      e: [[745, 302, 18, 15], [764, 288, 11, 12], [712, 314, 20, 9], [632, 296, 8, 8], [660, 316, 24, 6]],
      t: [[[758, 284], [770, 262], [779, 247]], [[628, 300], [642, 313], [612, 320]]],
      mv: [[0, 0, 2, 102], [2, 0, 0, 110], [8, 2, -2, 113], [14, 3, -4, 114]] },
    { name: "top_left", c: [195, 125],
      e: [[183, 82, 14, 13], [178, 108, 11, 13], [181, 146, 22, 18], [238, 150, 11, 8], [165, 140, 10, 11]],
      t: [[[188, 70], [200, 90], [228, 95]], [[195, 130], [203, 166], [313, 160]]],
      mv: [[0, 6, 4, 98], [2, 0, 0, 110], [6, -6, -2, 112], [14, -12, -4, 113]] },
    { name: "mid_left", c: [215, 262],
      e: [[178, 238, 13, 13], [172, 268, 11, 10], [200, 272, 16, 9], [270, 270, 7, 5]],
      t: [[[212, 262], [220, 286], [298, 280]]],
      mv: [[0, 4, 0, 100], [2, 0, 0, 110], [8, -4, 0, 112], [14, -8, 0, 113]] },
    { name: "bottom_left", c: [200, 385],
      e: [[230, 377, 15, 13], [218, 389, 12, 9], [180, 385, 8, 6]],
      t: [[[218, 372], [212, 400], [127, 391]]],
      mv: [[0, -10, 2, 90], [2, 0, 0, 110], [6, 8, -2, 114], [14, 16, -4, 115]] }
  ];

  // ---------------------------------------------------------------- S: puff density
  var Sd = FX.density(tag + "_S", W, H, fps, D, function (d) {
    for (var p = 0; p < PUFFS.length; p++) {
      var pf = PUFFS[p], l = FX.shape(d, pf.name), cx = pf.c[0], cy = pf.c[1];
      for (var i = 0; i < pf.e.length; i++) {
        var e = pf.e[i], g = FX.group(l, "ellipse", { size: [e[2] * 2 * S, e[3] * 2 * S], fill: [1, 1, 1] });
        g.xf.property("ADBE Vector Position").setValue(P(e[0] - cx, e[1] - cy));
      }
      for (var k = 0; k < pf.t.length; k++) {
        var tr = pf.t[k], pts = [];
        for (var q = 0; q < 3; q++) pts.push(P(tr[q][0] - cx, tr[q][1] - cy));
        FX.group(l, "path", { points: pts, closed: true, fill: [1, 1, 1] });
      }
      var pk = [], sk = [];
      for (var m = 0; m < pf.mv.length; m++) {
        pk.push([K(pf.mv[m][0]), P(cx + pf.mv[m][1], cy + pf.mv[m][2])]);
        sk.push([K(pf.mv[m][0]), [pf.mv[m][3], pf.mv[m][3]]]);
      }
      FX.keys(l.position, pk, false); FX.keys(l.scale, sk, false);
      var td = FX.fx(l, "ADBE Turbulent Displace");
      FX.set(td, "Amount", 55); FX.set(td, "Size", 14 * S); FX.set(td, "Random Seed", 3 + p * 7);
      FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 120]], false);
      FX.blur(l, 3 * S);
    }
  });
  // ---------------------------------------------------------------- Lf: light-tone field (S nudged up-left + noise)
  var Lf = FX.density(tag + "_L", W, H, fps, D, function (d) {
    var s = d.layers.add(Sd); s.position.setValue([W / 2 - 3 * S, H / 2 - 5 * S]);
    var n = FX.noise(d, "patches", { type: 1, noise: 4, contrast: 150, brightness: -20, scale: 9 * S, complexity: 1, seed: 8, evo: [[0, 0], [D, 90]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(30);
  });
  // ---------------------------------------------------------------- E: erosion (interiors first) + blob noise
  var E = FX.density(tag + "_E", W, H, fps, D, function (d) {
    // S nudged down-right: its interior is eaten first and the up-left rims survive longest as curls
    var s = d.layers.add(Sd); s.position.setValue([W / 2 + 6 * S, H / 2 + 7 * S]); FX.blur(s, 3 * S); s.opacity.setValue(70);
    var n = FX.noise(d, "holes", { type: 1, noise: 4, contrast: 140, brightness: 0, scale: 12 * S, complexity: 1, seed: 17, evo: [[0, 0], [D, 160]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(35);
  });

  // ---------------------------------------------------------------- body: shade + light, cut by the holes
  var body = FX.comp(tag + "_body", W, H, fps, D, "fxlib_density");
  FX.cel(body, Sd, "shade", 0.5, SHADE, 0.03);
  FX.celIn(body, Lf, "light", [[K(0), 0.8], [K(5), 0.83], [K(10), 0.88], [K(14), 0.9]], LIGHT, 0.03, Sd, 0.5);

  var c = FX.comp(tag, W, H, fps, D);
  // dark smoky base: a low threshold of S, nudged down and blurred
  var hz = FX.cel(c, Sd, "haze", 0.3, HAZE, 0.2);
  hz.position.setValue([W / 2, H / 2 + 7 * S]); FX.blur(hz, 12 * S);
  FX.keys(hz.opacity, [[K(0), 45], [K(3), 75], [K(5), 60], [K(7), 35], [K(9), 12], [K(11), 0]], false);
  var bl = c.layers.add(body); bl.name = "puffs";
  var holes = FX.cel(c, E, "holes", [[K(0), 0.98], [K(2), 0.97], [K(3), 0.95], [K(4), 0.9], [K(5), 0.85], [K(6), 0.78], [K(8), 0.55], [K(9), 0.3], [K(10), 0.2], [K(11), 0.13], [K(12), 0.08], [K(13), 0.05], [K(14), 0.02]], [1, 1, 1], 0.02);
  FX.matte(bl, holes, true);
  FX.blur(bl, 0.4 * S);
  return FX.done(c);
}
