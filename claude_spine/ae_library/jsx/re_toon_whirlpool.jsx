// re_toon_whirlpool: realistic version of wp_toon_whirlpool_v11 (960x540 water transition; same swirl, hole track and
// timing: the exact comp is the colour map and its hole/foam layers are the drivers). Real water: relief + specular
// from an embossed copy, spin motion blur around the (moving) drain, swirled caustics and water_01 photo material,
// foam with photo texture, a dark depth falloff and a wet rim around the drain.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "wp_toon_whirlpool_v11", S = 960 / 158, W = 960, H = 540, D = 1.76;
  RE.purge("re_toon_whirlpool_v");
  var tag = "re_toon_whirlpool_v" + V;
  var f = FX.gt("toon_whirlpool");
  var src = RE.findComp(SRC);
  var HOLE = 'comp("' + SRC + '").layer("hole")';
  var holePos = HOLE + ".transform.position";
  var pFoam = RE.only(SRC, tag + "_foam", function (n) { return n === "foam" || n === "hole_foam" || n === "hole_blob"; }, true);
  var pHole = RE.only(SRC, tag + "_hole", function (n) { return n === "hole" || n === "black_bands" || n === "black_slivers"; }, true);
  var c = RE.comp(tag, W, H, D);

  // 1. the water colour map, wobbling like liquid and spin-blurred around the drain
  var base = c.layers.add(src); base.name = "water";
  var td = FX.fx(base, "ADBE Turbulent Displace"); FX.set(td, "Amount", 7); FX.set(td, "Size", 45); FX.set(td, "Complexity", 2);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 400]], false);
  var rb = FX.fx(base, "ADBE Radial Blur");
  RE.trySet(rb, "Type", 1);
  FX.keys(FX.find(rb, "Amount"), [[0, 2], [f(10), 4], [f(26), 5], [f(32), 2], [f(40), 0]], false);
  FX.find(rb, "Center").expression = holePos;
  // 2. relief + specular: embossed blurred copy (overlay) and its brightest crests (add)
  function emb(nm) {
    var e = c.layers.add(src); e.name = nm;
    var eb = FX.blur(e, 14); RE.trySet(eb, "Repeat Edge Pixels", 1);   // no relief lines along the frame edges
    var em = FX.fx(e, "ADBE Emboss"); RE.trySet(em, "Direction", 135); RE.trySet(em, "Relief", 4); RE.trySet(em, "Contrast", 220);
    var t2 = FX.fx(e, "ADBE Turbulent Displace"); FX.set(t2, "Amount", 7); FX.set(t2, "Size", 45); FX.set(t2, "Complexity", 2);
    FX.keys(FX.find(t2, "Evolution"), [[0, 0], [D, 400]], false);
    return e;
  }
  var rel = emb("relief"); rel.blendingMode = BlendingMode.OVERLAY; rel.opacity.setValue(60);
  var spc = emb("specular");
  var lv = FX.fx(spc, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.58); lv.property("ADBE Pro Levels2-0005").setValue(0.8);
  spc.blendingMode = BlendingMode.ADD; spc.opacity.setValue(45);
  // 3. caustics (cell pattern web) and photo water, both swirled around the drain, only on the water (luma matte)
  function swirl(l, ang) {
    var tw = FX.fx(l, "ADBE Twirl");
    FX.keys(FX.find(tw, "Angle"), [[0, 0], [D, ang]], false);
    RE.trySet(tw, "Twirl Radius", 70);
    FX.find(tw, "Twirl Center").expression = holePos;
  }
  var cs = FX.solid(c, "caustics", [0, 0, 0]);
  var cp = FX.fx(cs, "ADBE Cell Pattern");
  RE.trySet(cp, "Cell Pattern", 1); RE.trySet(cp, "Invert", 1); RE.trySet(cp, "Contrast", 320); RE.trySet(cp, "Size", 70); RE.trySet(cp, "Disperse", 1);
  FX.keys(FX.find(cp, "Evolution"), [[0, 0], [D, 300]], false);
  swirl(cs, -260);
  RE.tint(cs, FX.rgb("DFFFFF"));
  cs.blendingMode = BlendingMode.SCREEN; cs.opacity.setValue(55);
  var csm = c.layers.add(src); csm.name = "caustics_matte"; cs.setTrackMatte(csm, TrackMatteType.LUMA);
  var wp = RE.tex(c, RE.R + "water_01.png", "water_photo", { pos: [W / 2, H / 2], blend: BlendingMode.OVERLAY, scale: 120 });
  RE.tint(wp, FX.rgb("E8FFFF"), FX.rgb("064E58"));
  swirl(wp, -180);
  wp.opacity.setValue(35);
  var wpm = c.layers.add(src); wpm.name = "water_photo_matte"; wp.setTrackMatte(wpm, TrackMatteType.LUMA);
  // 3b. glitter: tiny sun glints on the surface (sparse noise specks, swirled, additive, water only)
  var gn = FX.noise(c, "glints", { type: 1, noise: 4, contrast: 900, brightness: -235, scale: 6, complexity: 2, seed: 5, evo: [[0, 0], [D, 1500]] });
  swirl(gn.layer, -220);
  gn.layer.blendingMode = BlendingMode.ADD; gn.layer.opacity.setValue(70);
  var gnm = c.layers.add(src); gnm.name = "glints_matte"; gn.layer.setTrackMatte(gnm, TrackMatteType.LUMA);
  // 4. depth: the water darkens towards the drain; a wet pale rim on its far (up-left) edge
  var dp = c.layers.add(pHole); dp.name = "depth";
  RE.fill(dp, FX.rgb("021418")); FX.blur(dp, 26);
  dp.blendingMode = BlendingMode.MULTIPLY; dp.opacity.setValue(70);
  var rim = c.layers.add(pHole); rim.name = "drain_rim";
  RE.fill(rim, FX.rgb("CFFBFF")); FX.blur(rim, 2);
  var rimm = c.layers.add(pHole); rimm.name = "drain_rim_m"; rimm.position.setValue([W / 2 + 5, H / 2 + 6]);
  FX.matte(rim, rimm, true);
  rim.opacity.setValue(55);
  // 5. foam: the exact foam softened and wobbling, filled with photo foam texture
  var fb = c.layers.add(pFoam); fb.name = "foam_base";
  var tf = FX.fx(fb, "ADBE Turbulent Displace"); FX.set(tf, "Amount", 12); FX.set(tf, "Size", 14); FX.set(tf, "Complexity", 3);
  FX.keys(FX.find(tf, "Evolution"), [[0, 0], [D, 600]], false);
  FX.blur(fb, 1.5); fb.opacity.setValue(40);
  var ft = RE.tex(c, RE.R + "water_01.png", "foam_photo", { pos: [W / 2, H / 2], blend: BlendingMode.NORMAL, scale: 70 });
  RE.tint(ft, [1, 1, 1], FX.rgb("2AA6B0"));
  FX.keys(ft.rotation, [[0, 0], [D, -60]], false);
  var ftm = c.layers.add(pFoam); ftm.name = "foam_photo_matte";
  var tf2 = FX.fx(ftm, "ADBE Turbulent Displace"); FX.set(tf2, "Amount", 12); FX.set(tf2, "Size", 14); FX.set(tf2, "Complexity", 3);
  FX.keys(FX.find(tf2, "Evolution"), [[0, 0], [D, 600]], false);
  FX.blur(ftm, 1.5);
  FX.matte(ft, ftm, false);
  return FX.done(c);
}
