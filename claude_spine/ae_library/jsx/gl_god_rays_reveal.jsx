// gl_god_rays_reveal: one-shot bright reveal, 1.5 s (38 frames @25), 768x768, centred.
// 0-0.2 s a point of light gathers; 0.2 s burst: volumetric god rays shoot out (sharp + wide procedural ray fans
// plus CC Light Rays streaking a cycling noise disc for the soft volumetric haze), white-hot core flash and a star
// glint; 0.3-1.0 s beams shimmer and turn slowly while dust motes and faint Kenney smoke drift INSIDE the beams
// (luma track matte by the beams); 1.0-1.5 s the rays retract and the light settles to a steady soft glow.
$.evalFile(FXLIB_DIR + "gl_kit.jsx");
function BUILD(V) {
  var W = 768, H = 768, cx = 384, cy = 384, D = 1.5, TB = 0.2;   // TB = burst time
  RE.purge("gl_god_rays_reveal_v");
  var tag = "gl_god_rays_reveal_v" + V;
  var WHITE = FX.rgb("FFFFFF"), CREAM = FX.rgb("FFF4DA"), PALE = FX.rgb("FFE4A6"), GOLD = FX.rgb("FFC75A"),
      AMBER = FX.rgb("FF9C34"), DEEP = FX.rgb("C25A10");
  var rnd = FX.rng(1500);

  // --- beams: two ray fans animated inside one precomp (used as light AND as the matte for dust/haze)
  var sharp = GL.shapeRays(tag + "_rsharp", W, H, D, { n: 34, seed: 77, len: [200, 375], wdeg: [0.6, 2.2], flick: 0.6, blur: 2.5, cycles: 3 });
  var wide = GL.shapeRays(tag + "_rwide", W, H, D, { n: 9, seed: 13, len: [260, 375], wdeg: [5, 10], flick: 0.45, blur: 18, cycles: 2 });
  var beams = GL.pre(tag + "_beams", W, H, D);
  var lw = beams.layers.add(wide); lw.name = "wide"; lw.blendingMode = BlendingMode.ADD;
  var OPW = [[TB - 0.03, 0], [TB + 0.06, 55], [0.95, 45], [1.3, 8], [D, 0]];
  var ls = beams.layers.add(sharp); ls.name = "sharp"; ls.blendingMode = BlendingMode.ADD;
  var SC = [[TB - 0.02, [12, 12]], [TB + 0.28, [100, 100]], [1.0, [104, 104]], [D, [84, 84]]];
  FX.keys(lw.scale, SC, "out"); FX.keys(ls.scale, SC, "out");
  FX.keys(lw.rotation, [[0, -4], [D, 6]], false); FX.keys(ls.rotation, [[0, 3], [D, -5]], false);
  var OP = [[TB - 0.03, 0], [TB + 0.06, 100], [0.95, 88], [1.3, 30], [D, 12]];
  FX.keys(lw.opacity, OPW, "both"); FX.keys(ls.opacity, OP, "both");
  var ctr = GL.ellipse(ls, cx, cy, 30, 30, 40, MaskMode.SUBTRACT);

  // --- volumetric haze rays (CC Light Rays on cycling noise)
  var vol = GL.rays(tag + "_vol", W, H, D, { r: 70, blurM: 24, scale: 16, contrast: 240, bright: -30, revs: 1, seed: 4, complexity: 2,
    radius: 80, soft: 70, intensity: 250, intensityKeys: [[TB, 0], [TB + 0.25, 320], [1.0, 280], [D, 120]] });

  // --- dust motes (drift slowly, twinkle) and faint smoke, both revealed only inside the beams
  var dust = GL.pre(tag + "_dust", W, H, D);
  for (var k = 0; k < 60; k++) {
    var a = rnd() * Math.PI * 2, r = 40 + Math.sqrt(rnd()) * 300, x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
    var m = GL.sprite(dust, GL.K + "circle_05.png", "mote" + k, { pos: [x, y], color: rnd() < 0.5 ? PALE : GOLD, scale: 3 + rnd() * 3.5 });
    var dx = (rnd() - 0.5) * 50, dy = -10 - rnd() * 40;
    FX.keys(m.position, [[0, [x, y]], [D, [x + dx, y + dy]]], false);
    GL.ex(m.opacity, "70+30*Math.sin(2*Math.PI*(" + (0.7 + rnd() * 1.5).toFixed(2) + "*time+" + rnd().toFixed(2) + "))");
  }
  for (var s = 0; s < 2; s++) {
    var sm = GL.sprite(dust, GL.K + (s ? "smoke_08.png" : "smoke_07.png"), "haze" + s, { pos: [cx, cy], scale: s ? 150 : 125, color: AMBER, op: 35 });
    FX.keys(sm.rotation, [[0, s * 90], [D, s * 90 + (s ? -14 : 12)]], false);
  }

  var b = GL.pre(tag + "_body", W, H, D);
  // 1. wide warm halo (settles to the final soft glow)
  var halo = GL.orb(b, "halo", [cx, cy], 260, AMBER);
  FX.keys(halo.opacity, [[0, 0], [TB, 25], [TB + 0.15, 55], [1.0, 40], [D, 30]], "both");
  FX.keys(halo.scale, [[TB, [180, 180]], [0.6, [270, 270]], [D, [250, 250]]], "out");
  // 2. volumetric haze rays
  var vl = b.layers.add(vol); vl.name = "volumetric"; vl.blendingMode = BlendingMode.ADD;
  GL.tritone(vl, CREAM, AMBER, [0, 0, 0]); GL.lumaAlpha(vl);
  FX.keys(vl.opacity, [[TB - 0.02, 0], [TB + 0.1, 80], [1.0, 70], [D, 30]], false);
  // 3. beams (light)
  var bl = b.layers.add(beams); bl.name = "beams"; bl.blendingMode = BlendingMode.ADD;
  GL.tritone(bl, WHITE, GOLD, [0, 0, 0]); bl.opacity.setValue(85);
  var bw = b.layers.add(beams); bw.name = "beams_warm_spill"; bw.blendingMode = BlendingMode.ADD;
  GL.tritone(bw, AMBER, DEEP, [0, 0, 0]); FX.blur(bw, 22); bw.opacity.setValue(35);
  // 4. dust + haze inside the beams (luma matte = the beams, brightened)
  var dl = b.layers.add(dust); dl.name = "dust"; dl.blendingMode = BlendingMode.ADD;
  var dm = b.layers.add(beams); dm.name = "dust_matte";
  var lv = FX.fx(dm, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0005").setValue(0.45);
  FX.blur(dm, 6);
  dm.moveBefore(dl);
  dl.setTrackMatte(dm, TrackMatteType.LUMA);
  var dl2 = b.layers.add(dust); dl2.name = "dust_ambient"; dl2.blendingMode = BlendingMode.ADD;
  FX.keys(dl2.opacity, [[TB, 0], [TB + 0.2, 14], [D, 9]], false);
  // 5. core: gather -> flash -> settle
  var cb = GL.orb(b, "core_bloom", [cx, cy], 120, PALE);
  FX.keys(cb.scale, [[0, [20, 20]], [TB, [60, 60]], [TB + 0.06, [115, 115]], [0.8, [95, 95]], [D, [90, 90]]], "out");
  FX.keys(cb.opacity, [[0, 0], [TB - 0.1, 50], [TB + 0.04, 100], [0.8, 70], [D, 60]], false);
  var core = GL.orb(b, "core_white", [cx, cy], 40, WHITE);
  FX.keys(core.scale, [[0, [4, 4]], [TB, [30, 30]], [TB + 0.04, [72, 72]], [0.7, [44, 44]], [D, [38, 38]]], "out");
  FX.keys(core.opacity, [[0, 0], [0.06, 70], [TB, 100], [D, 95]], false);
  // gathering motes pulled into the point before the burst
  for (var g = 0; g < 12; g++) {
    var ga = rnd() * Math.PI * 2, gr = 120 + rnd() * 110;
    var gm = GL.sprite(b, GL.K + "circle_05.png", "gather" + g, { color: CREAM, scale: 2 + rnd() * 1.5 });
    FX.keys(gm.position, [[0, [cx + Math.cos(ga) * gr, cy + Math.sin(ga) * gr]], [TB, [cx + Math.cos(ga) * 8, cy + Math.sin(ga) * 8]]], "in");
    FX.keys(gm.opacity, [[0, 0], [0.06, 90], [TB - 0.02, 100], [TB, 0]], false);
    gm.motionBlur = true;
  }
  // 6. star glint on the burst
  var st = GL.sprite(b, GL.K + "star_09.png", "burst_star", { pos: [cx, cy], color: WHITE });
  FX.keys(st.scale, [[TB - 0.04, [15, 15]], [TB + 0.05, [95, 95]], [0.9, [45, 45]]], "out");
  FX.keys(st.opacity, [[TB - 0.04, 0], [TB + 0.02, 100], [0.5, 60], [1.0, 0]], false);
  FX.keys(st.rotation, [[TB, 0], [1.0, 20]], "out");
  var gb = FX.adj(b, "bloom");
  var gl = FX.glow(gb, 30, 0.4, 68, PALE, GOLD);
  FX.keys(FX.find(gl, "Glow Intensity"), [[TB, 0.4], [TB + 0.06, 0.8], [0.8, 0.35], [D, 0.25]], false);

  var c = GL.comp(tag, W, H, D);
  GL.vignette(c, b, cx, cy, 360, 360, 90);
  return FX.done(c);
}
