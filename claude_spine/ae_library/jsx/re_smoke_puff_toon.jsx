// re_smoke_puff_toon: realistic smoke on the timing/positions of the smoke_puff_toon build (puff layout, motion and
// erosion are the PROCEDURAL sp_smoke_puff_toon_v8 data and density comps; the traced v2 is not used). Each puff's
// discs become Kenney White-puff sprites and its tails photo smoke wisps (smoke_01/02), warm mauve, gas-displaced,
// held to the procedural silhouette by a soft luma matte and eaten away by the same erosion field; a dark smoky
// shadow sits under them.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "sp_smoke_puff_toon_v8", S = 1.2, W = 1080, H = 600, fps = 25, NF = 12, D = NF / fps;
  RE.purge("re_smoke_puff_toon_v");
  var tag = "re_smoke_puff_toon_v" + V;
  var rnd = FX.rng(54);
  var KM = [[0, 0], [1, 1], [3, 2], [4, 3], [5, 4], [6, 5], [8, 6], [9, 7], [10, 8], [11, 9], [13, 10], [14, 11]];
  function K(n) {
    for (var i = 0; i < KM.length - 1; i++)
      if (n <= KM[i + 1][0]) return (KM[i][1] + (KM[i + 1][1] - KM[i][1]) * (n - KM[i][0]) / (KM[i + 1][0] - KM[i][0])) / fps;
    return (KM[KM.length - 1][1] + (n - 14)) / fps;
  }
  function P(x, y) { return [x * S, y * S]; }
  var LIGHT = FX.rgb("F0AE96"), SHADE = FX.rgb("6A3E40"), HAZE = FX.rgb("3E2828");
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

  var Sd = RE.findComp(SRC + "_S"), E = RE.findComp(SRC + "_E");
  // ---- sprites: one White-puff per disc, photo wisps along the tails, all riding the puff motion
  var sm = FX.comp(tag + "_sprites", W, H, fps, D, RE.FOLDER);
  var pi = 0;
  for (var p = 0; p < PUFFS.length; p++) {
    var pf = PUFFS[p], cx = pf.c[0], cy = pf.c[1];
    var nl = sm.layers.addNull(D); nl.name = pf.name + "_ctrl";
    var pk = [], sk = [];
    for (var m = 0; m < pf.mv.length; m++) { pk.push([K(pf.mv[m][0]), P(cx + pf.mv[m][1], cy + pf.mv[m][2])]); sk.push([K(pf.mv[m][0]), [pf.mv[m][3], pf.mv[m][3]]]); }
    FX.keys(nl.position, pk, false); FX.keys(nl.scale, sk, false);
    for (var i = 0; i < pf.e.length; i++) {
      var e = pf.e[i], n = (pi++ * 7 + 3) % 25;
      var l = sm.layers.add(FX.imp(RE.K + ["smoke_04.png", "smoke_07.png", "smoke_01.png", "smoke_05.png"][pi % 4]));
      l.name = pf.name + "_puff" + i;
      l.parent = nl;
      l.position.setValue(P(e[0] - cx, e[1] - cy));
      var sz = Math.max(e[2], e[3]) * 2 * S * 2.1 / 400 * 100;
      l.scale.setValue([sz * (e[2] / Math.max(e[2], e[3])) * 1.1, sz * (e[3] / Math.max(e[2], e[3])) * 1.1]);
      FX.keys(l.rotation, [[0, rnd() * 360], [D, rnd() * 360]], false);
      RE.tint(l, LIGHT, SHADE);
      var lc = FX.fx(l, "ADBE Pro Levels2"); lc.property("ADBE Pro Levels2-0004").setValue(0.12); lc.property("ADBE Pro Levels2-0005").setValue(0.7);
    }
    for (var k = 0; k < pf.t.length; k++) {
      var tr = pf.t[k], ax = (tr[0][0] + tr[1][0]) / 2, ay = (tr[0][1] + tr[1][1]) / 2;
      var ang = Math.atan2(tr[2][1] - ay, tr[2][0] - ax) * 180 / Math.PI, len = Math.sqrt(Math.pow(tr[2][0] - ax, 2) + Math.pow(tr[2][1] - ay, 2));
      var w = sm.layers.add(FX.imp(RE.R + (k % 2 ? "smoke_02.png" : "smoke_01.png")));
      w.name = pf.name + "_wisp" + k; w.parent = nl;
      RE.circMask(w, 512, 340, 300, 200);
      w.position.setValue(P((ax + tr[2][0]) / 2 - cx, (ay + tr[2][1]) / 2 - cy));
      w.rotation.setValue(ang + (k % 2 ? 90 : 0));
      var ws = len * S * 1.6 / 600 * 100; w.scale.setValue([ws, ws]);
      RE.tint(w, LIGHT, [0, 0, 0]);
      w.blendingMode = BlendingMode.SCREEN;
    }
  }
  var tdz = FX.adj(sm, "gas"); var td = FX.fx(tdz, "ADBE Turbulent Displace");
  FX.set(td, "Amount", 30); FX.set(td, "Size", 22 * S); FX.set(td, "Complexity", 3);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 160]], false);
  // ---- matte: the procedural density softened, minus the erosion holes (same keyed threshold as the exact build)
  var mt = FX.comp(tag + "_matte", W, H, fps, D, RE.FOLDER);
  FX.solid(mt, "black", [0, 0, 0]);
  var sl = mt.layers.add(Sd); sl.name = "shape";
  var lv = FX.fx(sl, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.08); lv.property("ADBE Pro Levels2-0005").setValue(0.45);
  FX.blur(sl, 3 * S);
  var holes = FX.cel(mt, E, "holes", [[K(0), 0.98], [K(2), 0.97], [K(3), 0.95], [K(4), 0.9], [K(5), 0.85], [K(6), 0.78], [K(8), 0.55], [K(9), 0.3], [K(10), 0.2], [K(11), 0.13], [K(12), 0.08], [K(13), 0.05], [K(14), 0.02]], [1, 1, 1], 0.12);
  FX.blur(holes, 2 * S);
  holes.blendingMode = BlendingMode.SUBTRACT;

  var c = RE.comp(tag, W, H, D);
  // dark smoky shadow under the puffs
  var hz = FX.cel(c, Sd, "haze", 0.3, HAZE, 0.2);
  hz.position.setValue([W / 2, H / 2 + 7 * S]); FX.blur(hz, 14 * S);
  FX.keys(hz.opacity, [[K(0), 40], [K(3), 65], [K(5), 50], [K(7), 30], [K(9), 10], [K(11), 0]], false);
  var body = c.layers.add(sm); body.name = "smoke";
  var mm = c.layers.add(mt); mm.name = "smoke_matte";
  body.setTrackMatte(mm, TrackMatteType.LUMA);
  // soft self-shadow: the smoke darkened down-right where it is thick (shifted copy, multiply)
  var shd = c.layers.add(sm); shd.name = "self_shadow"; RE.fill(shd, FX.rgb("2A1818")); FX.blur(shd, 4 * S);
  shd.position.setValue([W / 2 + 3 * S, H / 2 + 4 * S]); shd.blendingMode = BlendingMode.MULTIPLY; shd.opacity.setValue(35);
  var shm = c.layers.add(mt); shm.name = "self_shadow_matte"; shd.setTrackMatte(shm, TrackMatteType.LUMA);
  return FX.done(c);
}
