// re_ca_coin_glow: realistic version of ca_coin_glow_v4 (same 684x276 @30 fps, 0.8 s, clip A t0 2.79,
// comp = clip box (0,1560)-(684,1836)). Real metallic light on the WIN bar: the exact wash/fringes as light with a
// soft bloom, a photographic light sweep (soft diagonal band) racing across the bar, an anamorphic streak along the
// top rail, and metallic star glints (Kenney star / flare / trace) popping where the exact glints are, with bloom.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "ca_coin_glow_v4", W = 684, H = 276, D = 0.8, FPS = 30, OY = 1560;
  RE.purge("re_ca_coin_glow_v");
  var tag = "re_ca_coin_glow_v" + V;
  var rnd = FX.rng(307);
  function T(t) { return t - 2.79; }
  function Y(y) { return y - OY; }
  function pre(nm, keep) {
    var p = RE.only(SRC, tag + "_" + nm, keep);
    p.motionBlur = true; p.shutterAngle = 270; p.shutterPhase = -135; return p;
  }
  var pWash = pre("wash", function (n) { return n === "bar_wash" || n === "wash_core" || n === "rail_glow"; });
  var pFringe = pre("fringe", function (n) { return n.indexOf("fringe") === 0 || n === "purple_haze"; });
  var pHalo = pre("halos", function (n) { return n.indexOf("glint_halo") === 0; });

  var c = FX.comp(tag, W, H, FPS, D, RE.FOLDER);
  c.motionBlur = true; c.shutterAngle = 270; c.shutterPhase = -135;

  // 1. wash + fringes + glint halos as light (exact timing), with a soft spill bloom
  RE.light(c, pFringe, "fringe_bloom", null, 10, 30);
  var fr = RE.light(c, pFringe, "fringes", null, 0, 100); fr.blendingMode = BlendingMode.NORMAL;
  RE.light(c, pWash, "wash_spill", null, 24, 18);
  var wl = RE.light(c, pWash, "wash", null, 0, 72); wl.blendingMode = BlendingMode.NORMAL;
  RE.light(c, pHalo, "glint_halos", null, 4, 85);

  // 2. light sweep: a soft slanted white band racing left -> right across the bar while it is lit, then a second,
  //    fainter sweep when the number has settled (metallic sheen)
  function sweep(nm, t0, t1, op, wid) {
    var l = FX.shape(c, nm);
    FX.group(l, "rect", { size: [wid, 420], fill: FX.rgb("FFFFFF") });
    l.rotation.setValue(18);
    FX.blur(l, wid * 0.6);
    FX.keys(l.position, [[t0, [-120, Y(1730)]], [t1, [W + 120, Y(1730)]]], "in");
    FX.keys(l.opacity, [[t0, 0], [t0 + (t1 - t0) * 0.2, op], [t1 - (t1 - t0) * 0.2, op], [t1, 0]], false);
    l.blendingMode = BlendingMode.ADD;
    var m = FX.shape(c, nm + "_matte");
    FX.group(m, "rect", { size: [W + 40, 130], fill: [1, 1, 1] });
    m.position.setValue([W / 2, Y(1732)]);
    FX.blur(m, 6);
    l.setTrackMatte(m, TrackMatteType.ALPHA);
    return l;
  }
  sweep("sweep1", T(2.80), T(2.95), 35, 60);
  sweep("sweep2", T(3.02), T(3.30), 12, 30);

  // 3. anamorphic streak along the top rail (trace texture laid horizontally) + hot rail line
  for (var a = 0; a < 2; a++) {
    var tr = RE.tex(c, RE.K + "trace_01.png", "rail_streak" + a, { pos: [W / 2 + (a ? 120 : -80), Y(1667)] });
    tr.rotation.setValue(90);
    RE.fill(tr, a ? FX.rgb("CFE8FF") : FX.rgb("FFF4D8"));
    FX.keys(tr.scale, [[T(2.80), [8, 140]], [T(2.86), [10, 220]], [T(2.97), [6, 160]]], false);
    FX.keys(tr.opacity, [[T(2.795), 0], [T(2.81), 75], [T(2.9), 60], [T(2.98), 0]], false);
  }

  // 4. metallic star glints at the exact glint spots (+ a few on the bar edges), each a star + tiny flare core
  var GL = [[60, 1675, 2.93, 3.0, 0.7, "FFFFFF", "star_06.png"],
            [640, 1665, 2.94, 3.05, 0.8, "FFF2D0", "star_08.png"],
            [465, 1648, 2.98, 3.22, 1.0, "F4E8FF", "star_08.png"],
            [395, 1672, 3.03, 3.18, 0.8, "FFFFFF", "star_04.png"],
            [665, 1662, 3.16, 3.26, 0.9, "FFF6C0", "star_06.png"],
            [25, 1668, 3.17, 3.28, 0.8, "EAF2FF", "star_04.png"],
            [305, 1628, 3.07, 3.18, 0.45, "FFFFFF", "star_01.png"],
            [160, 1795, 2.88, 2.96, 0.5, "FFFFFF", "star_06.png"],
            [520, 1670, 2.83, 2.92, 0.6, "FFFFFF", "star_04.png"]];
  for (var i = 0; i < GL.length; i++) {
    var g = GL[i], t0 = T(g[2]), t1 = T(g[3]), tm = t0 + (t1 - t0) * 0.35, s0 = g[4] * 24;
    var st = RE.tex(c, RE.K + g[6], "glint" + i, { pos: [g[0], Y(g[1])] });
    RE.fill(st, FX.rgb(g[5]));
    FX.keys(st.scale, [[t0, [s0 * 0.2, s0 * 0.2]], [tm, [s0, s0]], [t1, [s0 * 0.3, s0 * 0.3]]], false);
    FX.keys(st.rotation, [[t0, rnd() * 20 - 10], [t1, rnd() * 40 - 20]], false);
    FX.keys(st.opacity, [[t0, 0], [tm, 100], [t1, 0]], false);
    var fc = RE.tex(c, RE.K + "flare_01.png", "glint_core" + i, { pos: [g[0], Y(g[1])] });
    FX.keys(fc.scale, [[t0, [5, 5]], [tm, [s0 * 1.2, s0 * 1.2]], [t1, [5, 5]]], false);
    FX.keys(fc.opacity, [[t0, 0], [tm, 100], [t1, 0]], false);
  }

  // 5. bloom (two passes: tight white, wide warm)
  var g2 = FX.adj(c, "bloom_wide"); FX.glow(g2, 22, 0.15, 90, FX.rgb("FFE8A0"), FX.rgb("E070FF"));
  return FX.done(c);
}
