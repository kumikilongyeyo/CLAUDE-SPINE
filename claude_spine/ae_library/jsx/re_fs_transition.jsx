// re_fs_transition: realistic version of cb_fs_transition_v5 (clip B 4.12-5.42, same 1556x1740 frame, same timing and
// measured light levels). A real camera-flash bloom: the same white -> lavender -> violet bloom and haze, plus optics -
// lens dirt (bokeh_01 photo, desaturated) lit only while the flash is up, an anamorphic horizontal streak and Kenney
// lens-ghost rings on the line through the frame centre, Kenney star glints instead of drawn crosses, a soft bloom.
// The sunburst is the nested re_cb_sunburst_loop_v<SBV>, offset so its loop time is 0 at this comp's last frame.
// ADDITIVE. (The 45 % black dip at 4.14-4.27 is again a disabled normal layer `dip`.)
$.evalFile(FXLIB_DIR + "re_kit.jsx");
var RE_SBV = 3;
function BUILD(V) {
  var W = 1556, H = 1740, D = 1.3, FPS = 30, BX = 810, BY = 780, CX = 780, CY = 540;
  var name = "re_cb_fs_transition_v" + V;
  var c = FX.comp(name, W, H, FPS, D, RE.FOLDER);
  c.motionBlur = true; c.shutterAngle = 180; c.shutterPhase = -90;
  var WHITE = [1, 1, 1], LAV = FX.rgb("E0D8FF"), LILAC = [0.75, 0.62, 1], VIOLET = [0.55, 0.35, 1];
  function T(clip) { return clip - 4.12; }
  // flash strength 0..100 used by every optical element (bloom core opacity curve of the exact comp)
  var FLASH = [[T(4.195), 0], [T(4.229), 85], [T(4.267), 100], [T(4.306), 90], [T(4.344), 60], [T(4.383), 30], [T(4.44), 0]];

  // sunburst
  var sbc = RE.findComp("re_cb_sunburst_loop_v" + RE_SBV);
  var sb = c.layers.add(sbc); sb.name = "sunburst";
  sb.startTime = D - sbc.duration;
  sb.anchorPoint.setValue([CX, CY]); sb.position.setValue([CX, CY]); sb.blendingMode = BlendingMode.ADD;
  FX.keys(sb.opacity, [[T(4.595), 0], [T(4.615), 100]], false);
  FX.keys(sb.scale, [[T(4.595), [70, 70]], [T(4.65), [100, 100]]], "out");
  var boost = FX.ramp(c, "on_boost", CX, CY, 900, [1, 0.86, 0.45, 1], [0, 0, 0, 1], BlendingMode.ADD);
  FX.keys(boost.layer.opacity, [[T(4.6), 0], [T(4.62), 35], [T(4.72), 45], [T(4.85), 25], [T(5.05), 0]], false);
  var pop = RE.tex(c, RE.K + "flare_01.png", "burst_pop", { pos: [CX, CY] });       // the instant the sun ignites
  RE.fill(pop, FX.rgb("FFF0C0"));
  FX.keys(pop.scale, [[T(4.595), [80, 80]], [T(4.63), [420, 420]], [T(4.75), [300, 300]]], "out");
  FX.keys(pop.opacity, [[T(4.595), 0], [T(4.615), 90], [T(4.75), 0]], false);

  // bloom + haze (exact comp's curves and colours)
  var core = FX.ramp(c, "bloom_core", BX, BY, 200, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.ADD);
  FX.rampRadius(core, BX, BY, [[T(4.20), 150], [T(4.229), 450], [T(4.267), 800], [T(4.306), 1000], [T(4.344), 1100], [T(4.42), 1150]]);
  FX.keys(core.layer.opacity, [[T(4.195), 0], [T(4.229), 70], [T(4.267), 80], [T(4.306), 65], [T(4.344), 40], [T(4.383), 18], [T(4.44), 0]], false);
  var csc = FX.fx(core.layer, "ADBE Shift Channels"); FX.set(csc, "Take Alpha From", 5);
  var cf = FX.fx(core.layer, "ADBE Fill");
  FX.keys(FX.find(cf, "Color"), [[T(4.267), WHITE], [T(4.306), LAV], [T(4.344), LILAC], [T(4.383), VIOLET]], false);
  var haze = FX.solid(c, "haze", WHITE); haze.blendingMode = BlendingMode.ADD;
  var hf = FX.fx(haze, "ADBE Fill");
  FX.keys(FX.find(hf, "Color"), [[T(4.267), WHITE], [T(4.306), LAV], [T(4.344), LILAC], [T(4.383), VIOLET]], false);
  FX.keys(haze.opacity, [[T(4.21), 0], [T(4.229), 6], [T(4.267), 22], [T(4.306), 25], [T(4.344), 28], [T(4.383), 25], [T(4.42), 18], [T(4.46), 12], [T(4.5), 7], [T(4.56), 0]], false);
  // real light source: Kenney light + flare at the bloom centre
  var src = RE.tex(c, RE.K + "light_02.png", "flash_source", { pos: [BX, BY] });
  RE.fill(src, FX.rgb("F4F0FF"));
  FX.keys(src.scale, [[T(4.20), [30, 30]], [T(4.267), [95, 95]], [T(4.344), [120, 120]]], "out");
  FX.keys(src.opacity, [[T(4.195), 0], [T(4.229), 45], [T(4.267), 55], [T(4.344), 25], [T(4.42), 0]], false);
  // anamorphic streak
  var an = FX.shape(c, "anamorphic_streak");
  FX.group(an, "rect", { size: [2400, 10], fill: FX.rgb("DCD4FF") });
  an.anchorPoint.setValue([0, 0]); an.position.setValue([BX, BY]);
  FX.blur(an, 7);
  FX.keys(an.scale, [[T(4.20), [20, 60]], [T(4.267), [100, 120]], [T(4.383), [120, 60]]], "out");
  FX.keys(an.opacity, [[T(4.195), 0], [T(4.229), 45], [T(4.306), 60], [T(4.383), 18], [T(4.44), 0]], false);
  an.blendingMode = BlendingMode.ADD;
  // lens ghosts on the line source -> frame centre -> beyond
  var GH = [["light_01.png", -0.5, 70, FX.rgb("B8A8FF")], ["circle_05.png", 0.45, 40, FX.rgb("FFB8E8")], ["light_03.png", 1.15, 95, FX.rgb("A8C8FF")], ["circle_05.png", 1.6, 25, FX.rgb("D8B8FF")]];
  var FX0 = W / 2, FY0 = H / 2;
  for (var g = 0; g < GH.length; g++) {
    var t = GH[g][1], gx = BX + (FX0 - BX) * 2 * t, gy = BY + (FY0 - BY) * 2 * t;
    var gl = RE.tex(c, RE.K + GH[g][0], "ghost" + g, { pos: [gx, gy], scale: GH[g][2] });
    RE.fill(gl, GH[g][3]);
    FX.keys(gl.opacity, [[T(4.21), 0], [T(4.267), 32], [T(4.344), 24], [T(4.42), 0]], false);
  }
  // lens dirt lit by the flash
  var dirt = RE.tex(c, RE.R + "bokeh_01.png", "lens_dirt", { pos: [W / 2, H / 2], scale: [180, 260], mask: 300, inset: 20 });
  var hs = FX.fx(dirt, "ADBE HUE SATURATION"); try { FX.set(hs, "Master Saturation", -85); } catch (x) {}
  RE.tint(dirt, FX.rgb("EEE6FF"));
  FX.blur(dirt, 4);
  FX.keys(dirt.opacity, [[T(4.20), 0], [T(4.267), 20], [T(4.306), 24], [T(4.383), 12], [T(4.46), 0]], false);
  // glints
  var rnd = FX.rng(5);
  for (var k = 0; k < 26; k++) {
    var a = rnd() * 6.283, r = 80 + rnd() * 620, sc = 8 + rnd() * 14;
    var s = RE.tex(c, RE.K + "star_06.png", "flash_glint" + k, { pos: [BX + Math.cos(a) * r, BY + Math.sin(a) * r * 1.1] });
    RE.fill(s, WHITE);
    var t0 = T(4.24 + rnd() * 0.16);
    FX.keys(s.opacity, [[t0, 0], [t0 + 0.03, 100], [t0 + 0.12, 0]], false);
    FX.keys(s.scale, [[t0, [sc * 0.3, sc * 0.3]], [t0 + 0.03, [sc, sc]], [t0 + 0.12, [sc * 0.4, sc * 0.4]]], false);
  }
  var bl = FX.adj(c, "bloom"); var blg = FX.glow(bl, 30, 0.15, 88, FX.rgb("F0E8FF"), FX.rgb("C8B0FF"));
  FX.keys(FX.find(blg, "Glow Intensity"), [[T(4.19), 0], [T(4.267), 0.15], [T(4.383), 0.06], [T(4.46), 0]], false);   // flash only, never tints the sun
  var dip = FX.solid(c, "dip", [0, 0, 0]);
  FX.keys(dip.opacity, [[T(4.12), 0], [T(4.155), 45], [T(4.20), 45], [T(4.267), 0]], false);
  dip.enabled = false;
  return FX.done(c, '"mode":"additive"');
}
