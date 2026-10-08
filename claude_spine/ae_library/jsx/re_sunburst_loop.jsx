// re_sunburst_loop: realistic version of cb_sunburst_loop_v6 (same 1556x1740 frame, burst centre clip px 780,540,
// same 3.0 s seamless loop, same measured light levels). Volumetric god rays: an evolving occluder (fractal noise
// gaps, cycled evolution, a sine sweep of +-4 deg = exact loop) radially zoom-blurred from the centre (light
// scattering in haze), extinction falloff; the exact comp's spokes kept faint underneath for the same silhouette;
// hot core + warm wash at the exact comp's measured levels; dust motes drifting in the air that only show where a
// beam passes (luma track matte by the rays); gold bokeh from the bokeh_01 photo drifting slowly + Kenney flare glints.
// ADDITIVE.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var W = 1556, H = 1740, D = 3.0, FPS = 30, CX = 780, CY = 540, SB = 6;
  var tag = "re_cb_sunburst_loop_v" + V;
  var rnd = FX.rng(303);
  function comp(n) { var c = FX.comp(n, W, H, FPS, D, RE.FOLDER); c.motionBlur = true; c.shutterAngle = 180; c.shutterPhase = -90; return c; }
  function ramp(c, nm, r, col, op, blend) { var o = FX.ramp(c, nm, CX, CY, r, [col[0], col[1], col[2], 1], [0, 0, 0, 1], blend || BlendingMode.ADD); if (op !== undefined) o.layer.opacity.setValue(op); return o.layer; }

  // ---- 1. volumetric rays
  var occ = comp(tag + "_occluder");
  FX.solid(occ, "black", [0, 0, 0]);
  var big = Math.ceil(Math.sqrt(W * W + H * H) * 1.6);
  var gaps = FX.solid(occ, "gaps", [0, 0, 0], big, big);
  gaps.position.setValue([CX, CY]);
  var fn = FX.fx(gaps, "ADBE Fractal Noise");
  FX.set(fn, "Fractal Type", 1); FX.set(fn, "Noise Type", 3); FX.set(fn, "Contrast", 170); FX.set(fn, "Brightness", -10);
  FX.set(fn, "Uniform Scaling", 0); FX.set(fn, "Scale Width", 48); FX.set(fn, "Scale Height", 300); FX.set(fn, "Complexity", 3);
  FX.set(fn, "Random Seed", 12);
  FX.keys(FX.find(fn, "Evolution"), [[0, 0], [D, 360]], false); FX.set(fn, "Cycle Evolution", 1); FX.set(fn, "Cycle (in Revolutions)", 1);
  var pc = FX.fx(gaps, "ADBE Polar Coordinates"); FX.set(pc, "Interpolation", 1); FX.set(pc, "Type of Conversion", 1);  // streaks -> spokes round the centre
  var lv = FX.fx(gaps, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.42); lv.property("ADBE Pro Levels2-0005").setValue(0.75);
  gaps.rotation.expression = "Math.sin(2 * Math.PI * time / " + D + ") * 4";
  var open = ramp(occ, "opening", 650, [1, 1, 1], 100, BlendingMode.MULTIPLY);     // only gaps near the source radiate
  var rays = comp(tag + "_rays");
  var rl = rays.layers.add(occ); rl.name = "occluder";
  for (var i = 0; i < 2; i++) { var rb = FX.fx(rl, "ADBE Radial Blur"); FX.set(rb, "Amount", 100); FX.set(rb, "Center", [CX, CY]); FX.set(rb, "Type", 2); }
  var gain = FX.fx(rl, "ADBE Pro Levels2"); gain.property("ADBE Pro Levels2-0005").setValue(0.6);
  ramp(rays, "extinction", 1250, [1, 1, 1], 100, BlendingMode.MULTIPLY);

  var c = comp(tag);
  // warm wash + core (exact comp's measured levels)
  ramp(c, "warm_wash", 1150, [1, 0.3, 0], 30);
  var g1 = ramp(c, "glow_yellow", 700, [1, 0.86, 0], 58);
  g1.opacity.expression = "42 + 5 * Math.sin(2 * Math.PI * 2 * time / " + D + ")";
  ramp(c, "glow_core", 350, FX.rgb("FFE880"), 45);
  // exact spokes, faint (same silhouette and drift)
  var ex = c.layers.add(RE.findComp("cb_sb_rays_v" + SB)); ex.name = "exact_spokes";
  ex.position.setValue([CX, CY]); ex.rotation.setValue(180);
  var et = FX.fx(ex, "ADBE Tritone"); FX.set(et, "Highlights", FX.rgb("FFE060")); FX.set(et, "Midtones", FX.rgb("FFC040")); FX.set(et, "Shadows", [0, 0, 0]);
  ex.blendingMode = BlendingMode.ADD; ex.opacity.setValue(14);
  // volumetric shafts
  var vr = c.layers.add(rays); vr.name = "volumetric_rays";
  var vt = FX.fx(vr, "ADBE Tritone"); FX.set(vt, "Highlights", FX.rgb("FFF4D0")); FX.set(vt, "Midtones", FX.rgb("FFC24A")); FX.set(vt, "Shadows", [0, 0, 0]);
  vr.blendingMode = BlendingMode.ADD; vr.opacity.setValue(28);

  // ---- 2. dust motes in the beams
  var motes = comp(tag + "_motes");
  for (var m = 0; m < 160; m++) {
    var d = FX.shape(motes, "mote" + m), sz = 1.6 + Math.pow(rnd(), 3) * 3.4;
    FX.group(d, "ellipse", { size: [sz, sz], fill: [1, 0.95, 0.85] });
    d.anchorPoint.setValue([0, 0]);
    var a = rnd() * 2 * Math.PI, r = 60 + Math.pow(rnd(), 0.7) * 820, ax = 10 + rnd() * 24, ay = 8 + rnd() * 20, ph = rnd() * 6.28, f1 = 1 + Math.floor(rnd() * 2);
    var x0 = CX + Math.cos(a) * r, y0 = CY + Math.sin(a) * r * 0.9;
    d.position.expression = "[" + x0 + " + " + ax + " * Math.sin(2 * Math.PI * " + f1 + " * time / " + D + " + " + ph + "), " +
      y0 + " + " + ay + " * Math.cos(2 * Math.PI * time / " + D + " + " + (ph * 1.7) + ")]";
    d.opacity.expression = "70 + 30 * Math.sin(2 * Math.PI * " + (2 + m % 4) + " * time / " + D + " + " + ph + ")";
    d.motionBlur = true;
  }
  var ml = c.layers.add(motes); ml.name = "dust_motes"; ml.blendingMode = BlendingMode.ADD;
  FX.blur(ml, 0.6);
  var mm = c.layers.add(rays); mm.name = "dust_matte";
  var mmg = FX.fx(mm, "ADBE Pro Levels2"); mmg.property("ADBE Pro Levels2-0005").setValue(0.45);
  ml.setTrackMatte(mm, TrackMatteType.LUMA);

  // ---- 3. gold bokeh (photo), drifting slowly, plus flare glints
  for (var b = 0; b < 2; b++) {
    var bk = RE.tex(c, RE.R + "bokeh_01.png", "gold_bokeh" + b, { mask: 380, inset: 30 });
    var bx = CX + (b ? 260 : -240), by = CY + (b ? 120 : -60);
    bk.position.expression = "[" + bx + " + 30 * Math.sin(2 * Math.PI * time / " + D + " + " + b * 2 + "), " + by + " - 22 * Math.cos(2 * Math.PI * time / " + D + " + " + b + ")]";
    bk.scale.setValue(b ? [95, 95] : [120, 120]); bk.rotation.setValue(b ? 180 : 0);
    var bb = FX.fx(bk, "ADBE Gaussian Blur 2"); FX.set(bb, "Blurriness", b ? 3 : 6);
    bk.opacity.expression = (b ? 22 : 26) + " + 6 * Math.sin(2 * Math.PI * time / " + D + " + " + b * 3 + ")";
  }
  for (var q = 0; q < 12; q++) {
    var st = RE.tex(c, RE.K + "star_06.png", "glint" + q, {});
    RE.fill(st, FX.rgb("FFF0C0"));
    var a2 = rnd() * 2 * Math.PI, rr = 150 + rnd() * 450;
    st.position.setValue([CX + Math.cos(a2) * rr, CY + Math.sin(a2) * rr]);
    var f = 1 + Math.floor(rnd() * 2), p = rnd() * 6.28, smax = 10 + rnd() * 10;
    st.opacity.expression = "var v = Math.sin(2 * Math.PI * " + f + " * time / " + D + " + " + p + "); 100 * Math.pow(Math.max(0, v), 3)";
    st.scale.expression = "var v = Math.max(0, Math.sin(2 * Math.PI * " + f + " * time / " + D + " + " + p + ")); [" + smax + " * (0.4 + 0.6 * v), " + smax + " * (0.4 + 0.6 * v)]";
    st.rotation.setValue(rnd() * 20 - 10);
  }
  var bl = FX.adj(c, "bloom"); FX.glow(bl, 18, 0.35, 80, FX.rgb("FFD060"), FX.rgb("FF9030"));
  return FX.done(c, '"mode":"additive"');
}
