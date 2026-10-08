// re_target_ring: realistic version of tr_target_ring_v4 (same comp size, timing and motion, which are taken from
// the exact comp itself). A hot energy reticle: plasma ring with heat bloom, flare + anamorphic streak on the
// flash, sparks flying off the spikes, embers shed when the ring breaks up, slight heat shimmer.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "tr_target_ring_v4", S = 2, W = 460, H = 408, cx = W / 2, cy = H / 2, D = 0.96;
  RE.purge("re_target_ring_v");
  var tag = "re_target_ring_v" + V;
  var f = FX.gt("target_ring");
  var WHITE = FX.rgb("FFF8E6"), HOT = FX.rgb("FFD878"), ORA = FX.rgb("FF7A1A"), RED = FX.rgb("D8300A"), DEEP = FX.rgb("7A1404");
  var rnd = FX.rng(31);

  // drivers cut from the exact comp
  var pRing = RE.only(SRC, tag + "_ring", function (n) { return n === "ring"; });
  var pSpk = RE.only(SRC, tag + "_spikes", function (n) { return n === "cross_spikes" || n === "diag_ticks"; });
  var pDot = RE.only(SRC, tag + "_dot", function (n) { return n === "dot"; });
  var pRet = RE.only(SRC, tag + "_dots", function (n) { return n.indexOf("reticle") === 0; });

  var c = RE.comp(tag, W, H, D);

  // 1. heat bloom: wide deep-red haze, medium orange, both strongest at the flash
  RE.light(c, pRing, "bloom_deep", DEEP, 26 * S, [[f(9.5), 0], [f(10), 100], [f(13), 70], [f(22), 30]]);
  RE.light(c, pRing, "bloom_red", RED, 12 * S, [[f(9.5), 0], [f(10), 85], [f(13), 55], [f(22), 35]]);
  var bo = RE.light(c, pRing, "bloom_orange", FX.rgb("FF9A30"), 4.5 * S, 85);
  var bred = c.layer("bloom_red");
  var wl = [bo, bred];
  for (var wi = 0; wi < 2; wi++) {
    var tdw = FX.fx(wl[wi], "ADBE Turbulent Displace"); FX.set(tdw, "Amount", 10 + wi * 8); FX.set(tdw, "Size", (5 + wi * 3) * S); FX.set(tdw, "Complexity", 2);
    FX.keys(FX.find(tdw, "Evolution"), [[0, 0], [D, 900]], false);
  }
  RE.light(c, pSpk, "spk_bloom", RED, 8 * S, 90);
  RE.light(c, pSpk, "spk_orange", ORA, 2.5 * S, 100);

  // 2. plasma material inside the ring band: turbulent noise, rotating, matted by a softened ring
  var pl = RE.plasma(c, "ring_plasma", { type: 6, contrast: 240, brightness: 5, scale: 22 * S, complexity: 4, seed: 5, evo: 1440, color: HOT,
                                         rotKeys: [[0, 0], [D, 120]] });
  var plm = c.layers.add(pRing); plm.name = "ring_plasma_matte"; FX.blur(plm, 2.5 * S);
  FX.matte(pl, plm, false);

  // 3. white-hot core, wavering a touch like gas
  var core = RE.light(c, pRing, "ring_core", WHITE, 0.6 * S, 100);
  var td = FX.fx(core, "ADBE Turbulent Displace"); FX.set(td, "Amount", 6); FX.set(td, "Size", 10 * S); FX.set(td, "Complexity", 2);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 1800]], false);
  var hot = RE.light(c, pRing, "ring_hot", FX.rgb("FFE79A"), 1.6 * S, 100);
  var hn = FX.noise(c, "ring_hot_noise", { type: 6, noise: 3, contrast: 160, brightness: 10, scale: 16 * S, complexity: 3, seed: 12, evo: [[0, 0], [D, 1600]] });
  FX.keys(FX.find(hn.fx, "Rotation"), [[0, 0], [D, -90]], false);
  hot.setTrackMatte(hn.layer, TrackMatteType.LUMA);
  var td2 = FX.fx(hot, "ADBE Turbulent Displace"); FX.set(td2, "Amount", 9); FX.set(td2, "Size", 14 * S);
  FX.keys(FX.find(td2, "Evolution"), [[0, 0], [D, 1500]], false);
  RE.light(c, pSpk, "spk_core", WHITE, 0.4 * S, 100);
  // energy flowing round the ring: two short hot segments chasing each other
  var fA = RE.flow(pRing, tag + "_flowA", "ring", 14, [[0, 0], [D, 620]]);
  var fB = RE.flow(pRing, tag + "_flowB", "ring", 9, [[0, 180], [D, -260]]);
  RE.light(c, fA, "flowA_bloom", HOT, 5 * S, 90); RE.light(c, fA, "flowA_core", WHITE, 1.2 * S, 100);
  RE.light(c, fB, "flowB_bloom", HOT, 5 * S, 80); RE.light(c, fB, "flowB_core", WHITE, 1.2 * S, 90);
  RE.light(c, pRet, "ret_glow", ORA, 3 * S, 100);
  RE.light(c, pRet, "ret_core", HOT, 0, 100);

  // 4. the flash: hot dot, Kenney flare + star burst, anamorphic streaks
  RE.light(c, pDot, "dot_bloom", ORA, 8 * S, 100);
  RE.light(c, pDot, "dot_core", WHITE, 1 * S, 100);
  var fl = RE.tex(c, RE.K + "flare_01.png", "flash_flare", { pos: [cx, cy] });
  RE.fill(fl, HOT);
  FX.keys(fl.scale, [[f(8.4), [30, 30]], [f(9.2), [110, 110]], [f(11), [70, 70]]], false);
  FX.keys(fl.opacity, [[f(8.3), 0], [f(8.8), 100], [f(9.6), 100], [f(11.5), 0]], false);
  var st = RE.tex(c, RE.K + "star_08.png", "flash_star", { pos: [cx, cy], rot: 45 });
  RE.fill(st, WHITE);
  FX.keys(st.scale, [[f(8.5), [20, 20]], [f(9.2), [55, 55]], [f(10.5), [70, 70]]], "out");
  FX.keys(st.opacity, [[f(8.5), 0], [f(8.9), 100], [f(9.6), 90], [f(11), 0]], false);
  RE.light(c, pDot, "flash_bloom", ORA, 22 * S, [[f(8), 0], [f(9), 100], [f(10), 70], [f(12), 0]]);
  var an1 = RE.tex(c, RE.K + "flare_01.png", "anamorphic_wide", { pos: [cx, cy] });
  RE.fill(an1, FX.rgb("FFB050"));
  FX.keys(an1.scale, [[f(8.5), [90, 30]], [f(9.5), [230, 22]], [f(13), [260, 14]]], "out");
  FX.keys(an1.opacity, [[f(8.5), 0], [f(9.1), 100], [f(10.5), 80], [f(14.5), 0]], false);
  var an2 = RE.tex(c, RE.K + "flare_01.png", "anamorphic_core", { pos: [cx, cy] });
  RE.fill(an2, WHITE);
  FX.keys(an2.scale, [[f(8.7), [70, 10]], [f(9.4), [170, 7]], [f(12), [190, 5]]], "out");
  FX.keys(an2.opacity, [[f(8.7), 0], [f(9.2), 100], [f(10), 70], [f(12.5), 0]], false);

  // 5. sparks flying off the four cross spikes (tips at r ~80..90 GIF px) and glints riding the tips
  for (var s = 0; s < 4; s++) {
    var ang = -90 + s * 90;
    for (var k = 0; k < 10; k++) {
      var t0 = f(9.4 + rnd() * 3.2), t1 = t0 + 0.12 + rnd() * 0.22;
      var r0 = (34 + rnd() * 50) * S, a0 = ang * Math.PI / 180;
      var p0 = [cx + Math.cos(a0) * r0, cy + Math.sin(a0) * r0];
      var sa = ang + (rnd() - 0.5) * 70;
      RE.spark(c, "spark_" + s + "_" + k, p0, sa, (16 + rnd() * 30) * S, t0, t1, { len: (5 + rnd() * 8) * S, w: (0.6 + rnd() * 0.8) * S, color: rnd() < 0.5 ? WHITE : HOT, grav: 4 * S });
    }
    var gl = RE.tex(c, RE.K + "star_06.png", "tip_glint_" + s, { pos: [cx, cy], rot: 0 });
    RE.fill(gl, HOT);
    gl.anchorPoint.setValue([256, 256]);
    // follow the spike tip outward (cross spike keys: outer end 80 -> 86 -> 91 GIF px)
    var a1 = ang * Math.PI / 180;
    FX.keys(gl.position, [[f(9), [cx + Math.cos(a1) * 34 * S, cy + Math.sin(a1) * 34 * S]], [f(10), [cx + Math.cos(a1) * 80 * S, cy + Math.sin(a1) * 80 * S]],
                          [f(14), [cx + Math.cos(a1) * 86 * S, cy + Math.sin(a1) * 86 * S]], [f(19), [cx + Math.cos(a1) * 91 * S, cy + Math.sin(a1) * 91 * S]]], false);
    FX.keys(gl.scale, [[f(9), [14, 14]], [f(10), [20, 20]], [f(13), [12, 12]], [f(19), [5, 5]]], false);
    FX.keys(gl.opacity, [[f(8.8), 0], [f(9.2), 100], [f(16), 70], [f(20), 0]], false);
    gl.rotation.expression = "wiggle(12, 8)";
    // sparkler photo crackle at the tips while the spikes are hot
    var sp = RE.tex(c, RE.R + "sparks_02.png", "tip_sparkler_" + s, { mask: 120, inset: 140 });
    sp.anchorPoint.setValue([410, 345]);
    FX.keys(sp.position, [[f(10), [cx + Math.cos(a1) * 80 * S, cy + Math.sin(a1) * 80 * S]], [f(15), [cx + Math.cos(a1) * 87 * S, cy + Math.sin(a1) * 87 * S]]], false);
    sp.rotation.setValue(ang + 90);
    FX.keys(sp.scale, [[f(9.6), [5, 5]], [f(10.5), [14, 14]], [f(14), [10, 10]]], false);
    FX.keys(sp.opacity, [[f(9.6), 0], [f(10.2), 100], [f(13), 60], [f(15.5), 0]], false);
    sp.opacity.expression = "value * (0.55 + 0.45 * Math.abs(Math.sin(time * 97 + " + s * 1.7 + ")))";
  }
  // 6. embers shed from the ring as it breaks into dashes (f15..f22)
  for (var e = 0; e < 16; e++) {
    var ea = rnd() * 360, er = 111 * S / 2 + (rnd() - 0.5) * 4 * S, ear = ea * Math.PI / 180;
    var et0 = f(14 + rnd() * 6), et1 = et0 + 0.2 + rnd() * 0.25;
    RE.spark(c, "ember_" + e, [cx + Math.cos(ear) * er, cy + Math.sin(ear) * er], ea + (rnd() - 0.5) * 40, (6 + rnd() * 14) * S, et0, et1,
             { len: (1.5 + rnd() * 2) * S, w: 0.8 * S, color: rnd() < 0.4 ? HOT : ORA, grav: 3 * S });
  }
  // 7. air: heat shimmer, then one soft overall bloom
  RE.shimmer(c, 4, 18 * S, 3);
  var gb = FX.adj(c, "bloom_all"); var g = FX.glow(gb, 10 * S, 0.6, 55, ORA, RED);
  FX.keys(FX.find(g, "Glow Intensity"), [[f(8), 1.4], [f(10), 1.0], [f(13), 0.5], [f(22), 0.3]], false);
  return FX.done(c);
}
