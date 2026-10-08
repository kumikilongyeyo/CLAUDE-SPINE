// re_ca_rainbow_burst: realistic version of ca_rainbow_burst_v6 (same 684x1100 @30 fps, 0.75 s, clip A t0 1.84,
// comp = clip box (0,380)-(684,1480); the burst follows the X5 path through the `centre` null). Volumetric light
// burst with real lens character: the exact ray field as light + CC Light Rays volume, dust motes floating in the
// rays (radially streaked), chromatic fringe (red/blue offset copies), photo bokeh (bokeh_01/02), sparkler sparks
// (sparks_02 + motion-blurred streaks with gravity), lens flare core with a cyan lens ring. Additive.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "ca_rainbow_burst_v6", W = 684, H = 1100, D = 0.75, FPS = 30, OY = 380;
  RE.purge("re_ca_rainbow_burst_v");
  var tag = "re_ca_rainbow_burst_v" + V;
  var rnd = FX.rng(211);
  var PATH = [[1.84, 540], [1.90, 620], [1.96, 662], [2.02, 750], [2.08, 840], [2.15, 905], [2.21, 950], [2.27, 1050],
              [2.33, 1110], [2.39, 1165], [2.45, 1225], [2.51, 1320], [2.57, 1390]];
  function ctrAt(t) {            // comp t -> centre in comp px (same keys as the exact null, linear)
    var ct = t + 1.84;
    for (var i = 0; i < PATH.length - 1; i++) if (ct <= PATH[i + 1][0]) {
      var f = Math.max(0, (ct - PATH[i][0]) / (PATH[i + 1][0] - PATH[i][0]));
      return [320, PATH[i][1] + (PATH[i + 1][1] - PATH[i][1]) * f - OY];
    }
    return [320, PATH[PATH.length - 1][1] - OY];
  }
  function pre(nm, keep) {
    var p = RE.only(SRC, tag + "_" + nm, keep);
    for (var i = 1; i <= p.numLayers; i++) p.layer(i).motionBlur = true;
    p.motionBlur = true; p.shutterAngle = 270; p.shutterPhase = -135; return p;
  }
  var pRays = pre("rays", function (n) { return n === "centre" || n.indexOf("rays_") === 0 || n.indexOf("streaks_") === 0; });
  var pHaze = pre("haze", function (n) { return n === "centre" || n === "haze"; });
  var pCore = pre("core", function (n) { return n === "centre" || n === "core" || n === "core_glow" || n === "cyan_ring"; });

  var c = FX.comp(tag, W, H, FPS, D, RE.FOLDER);
  c.motionBlur = true; c.shutterAngle = 270; c.shutterPhase = -135;
  try { c.motionBlurSamplesPerFrame = 24; c.motionBlurAdaptiveSampleLimit = 128; } catch (x) {}
  var ctr = c.layers.addNull(D); ctr.name = "centre";
  var pk = []; for (var i = 0; i < PATH.length; i++) pk.push([PATH[i][0] - 1.84, [320, PATH[i][1] - OY]]);
  FX.keys(ctr.position, pk, false);
  var CP = 'thisComp.layer("centre").transform.position';
  var FOLLOW = "var p = " + CP + "; p + value";

  // 1. warm haze
  var hz = RE.light(c, pHaze, "haze", null, 0, 100); hz.blendingMode = BlendingMode.NORMAL;

  // 2. ray field (exact colours) + chromatic fringe copies scaled about the moving centre
  function about(l, pct) {
    l.anchorPoint.expression = CP; l.position.expression = CP; l.scale.setValue([pct, pct]);
  }
  var rr = RE.light(c, pRays, "rays_red_fringe", [1, 0.25, 0.3], 2, 22); about(rr, 104);
  var rb = RE.light(c, pRays, "rays_blue_fringe", [0.25, 0.45, 1], 2, 22); about(rb, 96.5);
  var rm = RE.light(c, pRays, "rays", null, 0, 100); rm.blendingMode = BlendingMode.NORMAL;
  // volume: CC Light Rays on a copy (light pours out of the centre)
  var rv = RE.light(c, pRays, "rays_volume", null, 0, 22);
  var lr = FX.fx(rv, "CC Light Rays");
  FX.set(lr, "Intensity", 60); FX.set(lr, "Radius", 50);
  FX.find(lr, "Center").expression = CP;
  try { FX.set(lr, "Warp Softness", 30); } catch (x) {}

  // 3. dust motes floating in the rays (specks matted by the ray luminance, streaked radially)
  var dm = FX.noise(c, "dust_motes", { type: 1, noise: 1, contrast: 520, brightness: -150, scale: 9, complexity: 1, seed: 17, evo: [[0, 0], [D, 400]] });
  dm.layer.blendingMode = BlendingMode.ADD;
  RE.tint(dm.layer, FX.rgb("FFF0D8"));
  var rbz = FX.fx(dm.layer, "ADBE Radial Blur");
  FX.set(rbz, "Amount", 18); FX.set(rbz, "Type", 2);         // 2 = zoom
  FX.find(rbz, "Center").expression = CP;
  var dmm = c.layers.add(pRays); dmm.name = "dust_matte";
  dm.layer.setTrackMatte(dmm, TrackMatteType.LUMA);
  dm.layer.opacity.setValue(70);

  // 4. bokeh: photo bokeh discs drifting outward around the burst
  var BK = [["bokeh_01.png", null, 0], ["bokeh_02.png", FX.rgb("FF8AD8"), 120], ["bokeh_01.png", FX.rgb("FFB0F0"), 240], ["bokeh_02.png", FX.rgb("FFD890"), 300]];
  for (var b = 0; b < BK.length; b++) {
    var bl = RE.tex(c, RE.R + BK[b][0], "bokeh" + b, {});
    RE.ellMask(bl, 160, 60);
    if (BK[b][1]) RE.tint(bl, BK[b][1]);
    var ba = BK[b][2] * Math.PI / 180;
    FX.keys(bl.position, [[0.04, [Math.cos(ba) * 60, Math.sin(ba) * 60]], [D, [Math.cos(ba) * 240, Math.sin(ba) * 200]]], "out");
    bl.position.expression = FOLLOW;
    bl.rotation.setValue(BK[b][2]);
    FX.keys(bl.scale, [[0.04, [30, 30]], [0.2, [62, 62]], [D, [70, 70]]], "out");
    FX.keys(bl.opacity, [[0.04, 0], [0.12, 75], [0.36, 60], [0.52, 25], [0.64, 0]], false);
  }

  // 5. sparkler sparks: photo burst at the centre + motion-blurred streaks with gravity launched from the X5
  for (var q = 0; q < 2; q++) {
    var sk = RE.tex(c, RE.R + "sparks_02.png", "sparkler" + q, {}); RE.circMask(sk, 410, 345, 200, 150);
    sk.anchorPoint.setValue([410, 345]); sk.position.expression = CP;
    sk.rotation.setValue(q * 180 + 15);
    FX.keys(sk.scale, [[0.03, [20, 20]], [0.1, [80, 80]], [0.3, [110, 110]], [0.5, [80, 80]]], "out");
    FX.keys(sk.opacity, [[0.02, 0], [0.06, 80], [0.3, 60], [0.5, 25], [0.6, 0]], false);
  }
  var COLS = [FX.rgb("FFFFFF"), FX.rgb("FFE9A0"), FX.rgb("FFC0E8"), FX.rgb("FFD070")];
  for (var k = 0; k < 44; k++) {
    var t0 = 0.03 + rnd() * 0.32, t1 = t0 + 0.2 + rnd() * 0.25, a = rnd() * 360, p0 = ctrAt(t0), r0 = 30 + rnd() * 40, ar = a * Math.PI / 180;
    RE.spark(c, "spark" + k, [p0[0] + Math.cos(ar) * r0, p0[1] + Math.sin(ar) * r0], a, 180 + rnd() * 320, t0, t1,
             { len: 18 + rnd() * 26, w: 2 + rnd() * 2.5, color: COLS[k % 4], grav: 60 + rnd() * 90 });
  }

  // 6. core: exact core light + lens flare + cyan lens ring + star glint
  var co = RE.light(c, pCore, "core", null, 0, 85); co.blendingMode = BlendingMode.NORMAL;
  var fl = RE.tex(c, RE.K + "flare_01.png", "lens_flare", {});
  fl.position.expression = CP;
  FX.keys(fl.scale, [[0, [30, 30]], [0.05, [70, 70]], [0.35, [60, 60]], [0.55, [40, 40]], [0.66, [20, 20]]], "out");
  FX.keys(fl.opacity, [[0, 0], [0.03, 80], [0.4, 70], [0.6, 30], [0.68, 0]], false);
  var ring = RE.tex(c, RE.K + "light_03.png", "lens_ring", {});
  RE.fill(ring, FX.rgb("50E0FF"));
  ring.position.expression = CP;
  FX.keys(ring.scale, [[0.04, [20, 20]], [0.14, [42, 40]], [0.45, [46, 44]], [0.62, [30, 28]]], "out");
  FX.keys(ring.opacity, [[0.04, 0], [0.1, 70], [0.45, 60], [0.62, 0]], false);
  var st = RE.tex(c, RE.K + "star_08.png", "star_glint", {});
  st.position.expression = CP;
  FX.keys(st.scale, [[0.02, [20, 20]], [0.07, [90, 90]], [0.3, [70, 70]], [0.55, [40, 40]]], false);
  FX.keys(st.rotation, [[0, 0], [D, 25]], false);
  FX.keys(st.opacity, [[0.02, 0], [0.06, 90], [0.45, 60], [0.6, 0]], false);

  // 7. bloom
  var gb = FX.adj(c, "bloom"); FX.glow(gb, 30, 0.2, 80, FX.rgb("FFF2D0"), FX.rgb("FF70C8"));
  ctr.moveToBeginning();
  return FX.done(c);
}
