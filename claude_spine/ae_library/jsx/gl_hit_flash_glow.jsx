// gl_hit_flash_glow: one-shot impact glow, 0.6 s (15 frames @25), 512x512, centred.
// Frame 0 is the peak: white-hot core + warm bloom stack that decays as 1/(1 + t/tau) (each wider layer with a
// longer tau, so the light cools white -> gold -> orange as it fades), anamorphic horizontal streak (Kenney
// trace_06 + flare_01), Kenney star glint, a shockwave ring of light (circle_02 + softer circle_03), a quick
// ray burst, sparks: motion-blurred tapered streaks with gravity, the sparkler photo and Kenney spark crackle.
$.evalFile(FXLIB_DIR + "gl_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, cx = 256, cy = 256, D = 0.6, T = 0.56;   // T = when everything is out
  RE.purge("gl_hit_flash_glow_v");
  var tag = "gl_hit_flash_glow_v" + V;
  var WHITE = FX.rgb("FFFFFF"), HOT = FX.rgb("FFF6DC"), PALE = FX.rgb("FFE8A8"), GOLD = FX.rgb("FFC03A"),
      AMBER = FX.rgb("FF9218"), ORANGE = FX.rgb("FF6408"), RED = FX.rgb("C82408");
  var rnd = FX.rng(606);

  var rays = GL.shapeRays(tag + "_rays", W, H, D, { n: 18, seed: 31, len: [150, 240], wdeg: [1.5, 4.5], flick: 0.2, blur: 3, cycles: 1 });
  var c = GL.comp(tag, W, H, D);

  // 1. bloom stack: wider layers decay slower (cooler colour lingers)
  var b3 = GL.orb(c, "bloom_orange", [cx, cy], 170, ORANGE);
  FX.keys(b3.opacity, GL.falloff(0, 0.04, 0.24, 60), false);
  FX.keys(b3.scale, [[0, [150, 150]], [0.42, [200, 200]]], "out");
  var b2 = GL.orb(c, "bloom_gold", [cx, cy], 150, GOLD);
  FX.keys(b2.opacity, GL.falloff(0, 0.045, 0.3, 75), false);
  FX.keys(b2.scale, [[0, [95, 95]], [0.3, [130, 130]]], "out");
  var b1 = GL.orb(c, "core_white", [cx, cy], 70, WHITE);
  FX.keys(b1.opacity, GL.falloff(0, 0.03, 0.36, 100), false);
  FX.keys(b1.scale, [[0, [70, 70]], [0.25, [45, 45]]], "out");

  // 2. ray burst
  var rl = c.layers.add(rays); rl.name = "ray_burst"; rl.blendingMode = BlendingMode.ADD;
  GL.tritone(rl, PALE, AMBER, [0, 0, 0]);
  FX.keys(rl.scale, [[0, [35, 35]], [0.12, [95, 95]], [0.45, [118, 118]]], "out");
  FX.keys(rl.opacity, GL.falloff(0, 0.07, 0.45, 70), false);
  FX.keys(rl.rotation, [[0, 0], [D, 8]], false);

  // 3. shockwave ring of light
  var r1 = GL.sprite(c, GL.K + "circle_02.png", "shock_ring", { pos: [cx, cy], color: PALE });
  FX.keys(r1.scale, [[0, [6, 6]], [0.42, [92, 92]]], "out", 85);
  FX.keys(r1.opacity, [[0, 0], [0.03, 100], [0.12, 75], [0.26, 30], [0.42, 0]], false);
  var r2 = GL.sprite(c, GL.K + "circle_04.png", "shock_ring_soft", { pos: [cx, cy], color: ORANGE });
  FX.keys(r2.scale, [[0, [4, 4]], [0.5, [80, 80]]], "out", 85);
  FX.keys(r2.opacity, [[0, 0], [0.05, 45], [0.18, 25], [0.4, 0]], false);
  FX.blur(r2, 4);

  // 4. sparks: sparkler photo, Kenney crackle, tapered streaks with gravity
  var ssrc = GL.photoSrc(tag + "_sparksrc", GL.R + "sparks_02.png", D, [[432, 392, 330, 300, 160]]);
  for (var p = 0; p < 2; p++) {
    var sk = c.layers.add(ssrc); sk.name = "sparkler" + p; sk.position.setValue([cx, cy]);
    var lv = FX.fx(sk, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.12);
    GL.photoLight(sk, HOT, AMBER, [0, 0, 0]);
    sk.anchorPoint.setValue([432, 392]); sk.rotation.setValue(p * 180 + 35);
    FX.keys(sk.scale, [[0.0, [12, 12]], [0.12, [42, 42]], [0.45, [55, 55]]], "out");
    FX.keys(sk.opacity, [[0, 0], [0.04, 95], [0.2, 70], [0.45, 0]], false);
  }
  for (var q = 0; q < 2; q++) {
    var cr = GL.sprite(c, GL.K + (q ? "spark_02.png" : "spark_01.png"), "crackle" + q, { pos: [cx, cy], color: PALE, rot: q * 140 });
    FX.keys(cr.scale, [[0, [30, 30]], [0.16, [62, 62]]], "out");
    FX.keys(cr.opacity, [[0, 0], [0.02, 100], [0.08, 60], [0.16, 0]], "hold");
  }
  for (var k = 0; k < 26; k++) {
    var a = rnd() * 360, t0 = rnd() * 0.04, t1 = t0 + 0.24 + rnd() * 0.28, ar = a * Math.PI / 180, r0 = 8 + rnd() * 20;
    RE.spark(c, "spark" + k, [cx + Math.cos(ar) * r0, cy + Math.sin(ar) * r0], a, 110 + rnd() * 120, t0, t1,
             { len: 12 + rnd() * 16, w: 1.6 + rnd() * 1.6, color: rnd() < 0.45 ? HOT : (rnd() < 0.6 ? GOLD : AMBER), grav: 30 + rnd() * 40 });
  }

  // 5. anamorphic horizontal streak + star glint (on top: the brightest, sharpest light)
  var s1 = GL.sprite(c, GL.K + "trace_06.png", "streak_wide", { pos: [cx, cy], rot: 90, color: AMBER });
  FX.keys(s1.scale, [[0, [22, 150]], [0.1, [26, 230]], [0.45, [14, 260]]], "out");
  FX.keys(s1.opacity, GL.falloff(0, 0.07, 0.36, 80), false);
  FX.blur(s1, 6);
  var s2 = GL.sprite(c, GL.K + "trace_06.png", "streak_core", { pos: [cx, cy], rot: 90, color: HOT });
  FX.keys(s2.scale, [[0, [7, 140]], [0.1, [8, 210]], [0.4, [4, 240]]], "out");
  FX.keys(s2.opacity, GL.falloff(0, 0.05, 0.4, 100), false);
  var fl = GL.sprite(c, GL.K + "flare_01.png", "flare", { pos: [cx, cy], color: PALE });
  FX.keys(fl.scale, [[0, [110, 110]], [0.3, [150, 120]]], "out");
  FX.keys(fl.opacity, GL.falloff(0, 0.05, 0.28, 100), false);
  var st = GL.sprite(c, GL.K + "star_08.png", "star_glint", { pos: [cx, cy], color: WHITE });
  FX.keys(st.scale, [[0, [20, 20]], [0.06, [62, 62]], [0.4, [40, 40]]], "out");
  FX.keys(st.rotation, [[0, -10], [D, 25]], "out");
  FX.keys(st.opacity, GL.falloff(0, 0.09, 0.42, 100), false);

  // 6. global bloom, strongest on the hit
  var gb = FX.adj(c, "bloom");
  var g = FX.glow(gb, 20, 0.6, 65, GOLD, ORANGE);
  FX.keys(FX.find(g, "Glow Intensity"), [[0, 0.8], [0.15, 0.4], [0.35, 0.15], [D, 0.1]], false);
  return FX.done(c);
}
