// re_teal_dome_splash: realistic version of td_teal_dome_v15 (same size/timing; the exact comp's procedural cel
// stack is the water's shape and shading). Real water: CC Glass refraction/specular, water_02/water_01 photo material,
// bright rim highlights, a fine droplet spray (water_02) where the dome bursts, drips that glint as they fall, mist.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "td_teal_dome_v15", S = 3, W = 510, H = 300, D = 1.84, cx = 80 * S, cy = 49 * S;
  RE.purge("re_teal_dome_splash_v");
  var tag = "re_teal_dome_splash_v" + V;
  var f = FX.gt("teal_dome_splash");
  var src = RE.findComp(SRC);
  var c = RE.comp(tag, W, H, D);
  var MIST = FX.rgb("BFEDEE"), PALE = FX.rgb("E6FFFF");

  // 1. mist behind: soft white puffs around the dome as it opens and breaks (Kenney White puff + smoke_02 photo)
  for (var m = 0; m < 6; m++) {
    var ma = (200 + m * 28) * Math.PI / 180, mr = 46 * S;
    var mp = RE.tex(c, RE.KS + "White puff/whitePuff" + ((m * 2 + 4) < 10 ? "0" : "") + (m * 2 + 4) + ".png", "mist" + m, { blend: BlendingMode.SCREEN });
    RE.tint(mp, MIST);
    FX.keys(mp.position, [[f(16), [cx + Math.cos(ma) * mr * 0.8, cy + 10 * S + Math.sin(ma) * mr * 0.4]], [D, [cx + Math.cos(ma) * mr * 1.15, cy + 16 * S + Math.sin(ma) * mr * 0.5]]], "out");
    FX.keys(mp.scale, [[f(16), [14, 14]], [D, [30, 30]]], "out");
    FX.keys(mp.rotation, [[f(16), m * 50], [D, m * 50 + 30]], false);
    FX.keys(mp.opacity, [[f(16), 0], [f(24), 7], [f(32), 5], [f(40), 0]], false);
  }
  // 2. the water (a soft dark edge behind it keeps it reading on light backgrounds)
  var edge = c.layers.add(src); edge.name = "dark_edge"; RE.fill(edge, FX.rgb("06242A")); FX.blur(edge, 2.5 * S); edge.opacity.setValue(70);
  var w = RE.waterize(c, src, "dome", { pos: [cx, cy], scale: [[f(9), [14, 14]], [f(16), [30, 30]], [D, [36, 36]]], blur: 1.5,
                                         glass: { height: 30, soft: 10, disp: 25 }, exposure: -0.3 });
  // bright rim (fresnel): the water alpha minus itself shifted down-right, pale, soft
  var rim = c.layers.add(src); rim.name = "rim_light";
  RE.fill(rim, PALE); FX.blur(rim, 1 * S);
  var rimm = c.layers.add(src); rimm.name = "rim_light_m"; rimm.position.setValue([W / 2 + 0.8 * S, H / 2 + 0.9 * S]);
  FX.matte(rim, rimm, true);
  rim.opacity.setValue(35);
  // 3. glints riding the dome and the falling drips: the water's own specular, bloomed
  var sp = c.layers.add(src); sp.name = "spec_bloom";
  var lv = FX.fx(sp, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.85);   // only the near-white specular
  FX.blur(sp, 2 * S); sp.blendingMode = BlendingMode.ADD; sp.opacity.setValue(60);
  // 4. droplet spray where the dome bursts open (f19-f34): water_02 photo, two copies flying outwards
  for (var k = 0; k < 2; k++) {
    var dp = RE.tex(c, RE.R + "water_02.png", "spray" + k, { pos: [cx + (k ? 30 : -30) * S, cy + 12 * S], blend: BlendingMode.SCREEN, rot: k ? 20 : -160 });
    dp.anchorPoint.setValue([520, 320]); RE.circMask(dp, 520, 320, 330, 160);
    RE.tint(dp, FX.rgb("A8EAEE"), [0, 0, 0]);
    FX.keys(dp.scale, [[f(19), [10, 10]], [f(26), [22, 22]], [f(36), [28, 28]]], "out");
    FX.keys(dp.position, [[f(19), [cx + (k ? 22 : -22) * S, cy + 8 * S]], [f(36), [cx + (k ? 40 : -40) * S, cy + 26 * S]]], false);
    FX.keys(dp.opacity, [[f(19), 0], [f(23), 15], [f(29), 6], [f(34), 0]], false);
  }
  var gb = FX.adj(c, "bloom"); FX.glow(gb, 5 * S, 0.25, 80, PALE, FX.rgb("4FB1B2"));
  return FX.done(c);
}
