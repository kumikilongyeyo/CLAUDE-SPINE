// re_sun_rune_burst: realistic version of sr_sun_rune_v3 (same size, timing and motion, taken from the exact comp).
// Real sparkler sparks streaking in and out with motion blur, a molten-metal ring, white-hot cross and spinning
// filaments, then a glowing ember donut with warm-lit photo smoke lingering.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "sr_sun_rune_v3", S = 3, W = 414, H = 441, cx = 76 * S, cy = 70 * S, D = 0.96;
  RE.purge("re_sun_rune_burst_v");
  var tag = "re_sun_rune_burst_v" + V;
  var f = FX.gt("sun_rune_burst");
  var WHITE = FX.rgb("FFF8E2"), YEL = FX.rgb("FFD86A"), ORA = FX.rgb("FF7A18"), RED = FX.rgb("C8300A"), DEEP = FX.rgb("6A1404"),
      AMB = FX.rgb("E08A2A"), SMOKE = FX.rgb("6E4A30");
  var rnd = FX.rng(77);
  function pre(nm, keep) { var p = RE.only(SRC, tag + "_" + nm, keep); for (var i = 1; i <= p.numLayers; i++) p.layer(i).motionBlur = true;
    p.motionBlur = true; p.shutterAngle = 270; p.shutterPhase = -135; return p; }
  var pGather = pre("gather", function (n) { return n.indexOf("gather") === 0 || n === "dot"; });
  var pRing = pre("ring", function (n) { return n === "ring"; });
  var pCross = pre("cross", function (n) { return n === "cross"; });
  var pRays = pre("rays", function (n) { return n.indexOf("ray") === 0 || n.indexOf("ember") === 0; });
  var pStar = pre("starburst", function (n) { return n === "starburst"; });
  var pDonut = pre("donut", function (n) { return n === "donut"; });
  var pDash = pre("dashed", function (n) { return n === "dashed_ring"; });

  var c = RE.comp(tag, W, H, D);

  // 1. lingering smoke (warm-lit by the embers), behind everything
  var sm = RE.tex(c, RE.K + "smoke_10.png", "smoke_ring", { pos: [cx, cy], blend: BlendingMode.SCREEN });
  RE.tint(sm, FX.rgb("8A5A36"));
  FX.keys(sm.scale, [[f(11), [52, 52]], [f(23), [74, 74]]], "out");
  FX.keys(sm.rotation, [[f(11), 0], [D, 25]], false);
  FX.keys(sm.opacity, [[f(11), 0], [f(14), 55], [f(19), 50], [D, 32]], false);
  for (var q = 0; q < 3; q++) {
    var ps = RE.tex(c, RE.R + "smoke_04.png", "smoke_photo" + q, { blend: BlendingMode.SCREEN }); RE.circMask(ps, 300 + q * 200, 380, 230, 200);
    RE.tint(ps, FX.rgb("7A5236"));
    var qa = (q * 120 + 30) * Math.PI / 180;
    FX.keys(ps.position, [[f(12), [cx + Math.cos(qa) * 22 * S, cy + Math.sin(qa) * 22 * S]], [D, [cx + Math.cos(qa) * 30 * S, cy + Math.sin(qa) * 30 * S - 10 * S]]], false);
    ps.rotation.setValue(q * 120);
    FX.keys(ps.scale, [[f(12), [22, 22]], [D, [30, 30]]], false);
    FX.keys(ps.opacity, [[f(12), 0], [f(15), 35], [D, 25]], false);
  }

  // 2. ember donut: amber body + flickering ember specks inside it
  RE.light(c, pDonut, "donut_glow", AMB, 3 * S, 55);
  RE.light(c, pDonut, "donut_red", RED, 9 * S, 45);
  var sp = FX.noise(c, "ember_specks", { type: 1, noise: 4, contrast: 700, brightness: -175, scale: 2 * S, complexity: 2, seed: 33, evo: [[0, 0], [D, 2200]] });
  RE.tint(sp.layer, FX.rgb("FFB040"));
  sp.layer.blendingMode = BlendingMode.ADD;
  var spm = c.layers.add(pDonut); spm.name = "ember_specks_matte";
  FX.matte(sp.layer, spm, false);
  var sp2 = FX.noise(c, "ember_mottle", { type: 6, noise: 3, contrast: 200, brightness: -20, scale: 14 * S, complexity: 3, seed: 8, evo: [[0, 0], [D, 700]] });
  RE.tint(sp2.layer, RED); sp2.layer.blendingMode = BlendingMode.ADD; sp2.layer.opacity.setValue(45);
  var spm2 = c.layers.add(pDonut); spm2.name = "ember_mottle_matte";
  FX.matte(sp2.layer, spm2, false);

  // 3. molten ring: deep bloom, orange body with molten noise, white-hot core
  RE.light(c, pRing, "ring_bloom", RED, 12 * S, 100);
  var rb = RE.light(c, pRing, "ring_body", ORA, 2.5 * S, 100);
  var td = FX.fx(rb, "ADBE Turbulent Displace"); FX.set(td, "Amount", 14); FX.set(td, "Size", 6 * S);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 1500]], false);
  var mol = RE.light(c, pRing, "ring_molten", YEL, 1.2 * S, 100);
  var mn = FX.noise(c, "molten_noise", { type: 6, noise: 3, contrast: 170, brightness: 15, scale: 9 * S, complexity: 3, seed: 3, evo: [[0, 0], [D, 1300]] });
  mol.setTrackMatte(mn.layer, TrackMatteType.LUMA);
  RE.light(c, pRing, "ring_core", WHITE, 0.4 * S, 85);

  // 4. cross + spinning filaments, white-hot with orange bloom
  RE.light(c, pCross, "cross_bloom", ORA, 5 * S, 100);
  RE.light(c, pCross, "cross_core", WHITE, 0, 100);
  RE.light(c, pStar, "star_bloom", RED, 4 * S, 100);
  RE.light(c, pStar, "star_core", YEL, 0, 100);
  RE.light(c, pDash, "dash_bloom", ORA, 3 * S, 100);
  RE.light(c, pDash, "dash_core", YEL, 0, 90);

  // 5. sparks: the exact streaks (motion blurred) as white-hot heads with orange trails, plus sparkler photo bursts
  RE.light(c, pGather, "gather_bloom", ORA, 3 * S, 100);
  RE.light(c, pGather, "gather_core", WHITE, 0, 100);
  RE.light(c, pRays, "rays_bloom", RED, 4 * S, 100);
  RE.light(c, pRays, "rays_orange", ORA, 1.2 * S, 100);
  RE.light(c, pRays, "rays_core", WHITE, 0, 100);
  for (var k = 0; k < 34; k++) {      // extra free sparks with gravity
    var a = rnd() * 360, t0 = f(7.8 + rnd() * 1.5), t1 = t0 + 0.18 + rnd() * 0.3, r0 = (8 + rnd() * 14) * S, ar = a * Math.PI / 180;
    RE.spark(c, "spark" + k, [cx + Math.cos(ar) * r0, cy + Math.sin(ar) * r0], a, (40 + rnd() * 34) * S, t0, t1,
             { len: (3 + rnd() * 5) * S, w: (0.5 + rnd() * 0.6) * S, color: rnd() < 0.5 ? WHITE : YEL, grav: (6 + rnd() * 8) * S });
  }
  for (var b = 0; b < 2; b++) {
    var sk = RE.tex(c, RE.R + "sparks_02.png", "sparkler" + b, { pos: [cx, cy] }); RE.circMask(sk, 410, 345, 170, 140);
    sk.anchorPoint.setValue([410, 345]);
    sk.rotation.setValue(b * 180 + 20);
    FX.keys(sk.scale, [[f(7.6), [12, 12]], [f(8.5), [40, 40]], [f(11), [52, 52]]], "out");
    FX.keys(sk.opacity, [[f(7.5), 0], [f(8), 100], [f(9.5), 85], [f(12), 0]], false);
  }
  // 6. flash on the pop
  var fl = RE.tex(c, RE.K + "flare_01.png", "flash", { pos: [cx, cy] });
  RE.fill(fl, YEL);
  FX.keys(fl.scale, [[f(6.8), [15, 15]], [f(8), [50, 50]], [f(10), [25, 25]]], false);
  FX.keys(fl.opacity, [[f(6.8), 0], [f(7.6), 100], [f(8.5), 90], [f(10.5), 0]], false);

  // 7. air
  RE.shimmer(c, 3, 16 * S, 3);
  var gb = FX.adj(c, "bloom_all"); var g = FX.glow(gb, 8 * S, 0.6, 55, ORA, RED);
  FX.keys(FX.find(g, "Glow Intensity"), [[f(7.5), 0.6], [f(8), 1.6], [f(10), 0.8], [f(14), 0.4]], false);
  return FX.done(c);
}
