// gl_win_glow_gold: warm golden aura behind a winning symbol. Seamless 2.0 s loop (50 frames @25).
// Back to front: amber halo + gold breathing bloom (falloff ends well inside the frame), volumetric rays
// (CC Light Rays cast from a ring of cycling noise, slow rotation via cross-faded copies), a faint real-bokeh
// photo ring, rising gold bokeh discs and light motes, star twinkles, white-hot core, warm Glow; a round vignette
// keeps the frame edge pure black.
$.evalFile(FXLIB_DIR + "gl_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, cx = 256, cy = 256, D = 2.0;
  RE.purge("gl_win_glow_gold_v");
  var tag = "gl_win_glow_gold_v" + V;
  var WHITE = FX.rgb("FFF6E2"), CREAM = FX.rgb("FFE6A8"), GOLD = FX.rgb("FFC53D"), AMBER = FX.rgb("FF9A1A"),
      ORANGE = FX.rgb("F06A00"), DEEP = FX.rgb("A83A00"), HONEY = FX.rgb("FFB21E");
  var rnd = FX.rng(2024);

  var pr = GL.shapeRays(tag + "_rays", W, H, D, { n: 14, seed: 5, len: [150, 235], wdeg: [1.4, 3.6], flick: 0.6, blur: 4, cycles: 2 });
  var pw = GL.shapeRays(tag + "_rayswide", W, H, D, { n: 7, seed: 9, len: [170, 240], wdeg: [8, 14], flick: 0.45, blur: 14, cycles: 1 });
  var disc = GL.bokehDisc(tag + "_disc", 48, D);

  var b = GL.pre(tag + "_body", W, H, D);
  // 1. halo + bloom
  var halo = GL.orb(b, "halo_amber", [cx, cy], 135, ORANGE, 38);
  GL.breathScale(halo, D, 135, 6, 1, 0.1); GL.breathOp(halo, D, 34, 8, 1, 0.1);
  var bloom = GL.orb(b, "bloom_gold", [cx, cy], 115, AMBER, 42);
  GL.breathScale(bloom, D, 115, 7, 1, 0); GL.breathOp(bloom, D, 38, 10, 1, 0);
  var bloom2 = GL.orb(b, "bloom_honey", [cx, cy], 70, GOLD, 40);
  GL.breathScale(bloom2, D, 70, 5, 1, 0.05); GL.breathOp(bloom2, D, 36, 10, 1, 0.05);

  // 2. rays: slow rotation (12 deg per loop) cross-faded so frame 50 == frame 0; centre masked out
  var rr = GL.loopRot(b, pr, "rays", D, 12, { pos: [cx, cy], op: 70 });
  var rw = GL.loopRot(b, pw, "rays_wide", D, -9, { pos: [cx, cy], op: 45, rot0: 41 });
  var all = [rr[0], rr[1], rw[0], rw[1]];
  for (var i = 0; i < 4; i++) {
    GL.tritone(all[i], i < 2 ? CREAM : GOLD, i < 2 ? AMBER : ORANGE, [0, 0, 0]);
    GL.ellipse(all[i], cx, cy, 70, 70, 50, MaskMode.SUBTRACT);
  }
  for (var i2 = 0; i2 < 4; i2++) { var mm = GL.ellipse(all[i2], cx, cy, 250, 250, 120); mm.maskMode = MaskMode.INTERSECT; }

  // 3. faint real-bokeh photo, ring-shaped, orbiting gently
  var bsrc = GL.photoSrc(tag + "_bokehsrc", GL.R + "bokeh_01.png", D, [[512, 341, 240, 230, 180], [512, 341, 160, 160, 130, "sub"]]);
  var bk = b.layers.add(bsrc); bk.name = "bokeh_photo"; bk.scale.setValue([58, 58]);
  GL.photoLight(bk, CREAM, AMBER, [0, 0, 0]);
  GL.ex(bk.position, "var a=2*Math.PI*time/" + D + ";[" + cx + "+8*Math.sin(a)," + cy + "-6*Math.cos(a)]");
  GL.breathOp(bk, D, 22, 6, 1, 0.3);

  // 4. rising bokeh discs in an annulus around the symbol (near = bigger, softer, dimmer)
  for (var k = 0; k < 18; k++) {
    var a = rnd() * Math.PI * 2, rad = 105 + rnd() * 120, x0 = cx + Math.cos(a) * rad, y0 = cy + Math.sin(a) * rad * 0.92 + 30;
    var near = rnd() < 0.3, s0 = near ? 30 + rnd() * 18 : 10 + rnd() * 14;
    GL.mote(b, disc, "bokeh" + k, {
      D: D, k: rnd() < 0.35 ? 2 : 1, ph: rnd(), p0: [x0, y0], p1: [x0 + (rnd() - 0.5) * 30, y0 - 60 - rnd() * 80],
      sway: [3 + rnd() * 5, 1], swph: rnd(), s0: s0, s1: s0 * (0.85 + rnd() * 0.3), op: near ? 30 + rnd() * 15 : 50 + rnd() * 35,
      color: near ? AMBER : [GOLD, HONEY, AMBER, GOLD][Math.floor(rnd() * 4)], fin: 0.25, fout: 0.45, blur: near ? 2.5 : 0 });
  }
  // tiny light motes
  for (var m = 0; m < 16; m++) {
    var am = rnd() * Math.PI * 2, rm = 80 + rnd() * 130, xm = cx + Math.cos(am) * rm, ym = cy + Math.sin(am) * rm + 20;
    GL.mote(b, GL.K + "light_01.png", "mote" + m, {
      D: D, k: 1, ph: rnd(), p0: [xm, ym], p1: [xm + (rnd() - 0.5) * 24, ym - 45 - rnd() * 60],
      sway: [3 + rnd() * 3, 2], swph: rnd(), s0: 1.6 + rnd() * 1.8, s1: 1.2, op: 75 + rnd() * 25, color: rnd() < 0.5 ? CREAM : GOLD,
      fin: 0.2, fout: 0.5, flick: 0.45, flickN: 4 + Math.floor(rnd() * 3) });
  }
  // 5. twinkles: star glints popping around the aura (one about every 0.35 s)
  var tw = [[0.04, 150, 0], [0.22, 190, 1], [0.41, 125, 0], [0.58, 175, 0], [0.76, 205, 1], [0.92, 140, 0]];
  for (var t = 0; t < tw.length; t++) {
    var at = (t * 137 + 20) * Math.PI / 180;
    GL.twinkle(b, GL.K + (tw[t][2] ? "star_07.png" : "star_06.png"), "twinkle" + t, {
      D: D, ph: -tw[t][0], len: 0.13, pos: [cx + Math.cos(at) * tw[t][1], cy + Math.sin(at) * tw[t][1] * 0.95],
      s: 11 + (t % 3) * 3, op: 100, color: t % 2 ? WHITE : CREAM, rot: t * 17 });
  }
  // 6. white-hot core
  var core = GL.orb(b, "core_hot", [cx, cy], 40, WHITE, 60);
  GL.breathScale(core, D, 40, 4, 1, 0); GL.breathOp(core, D, 55, 12, 1, 0);
  var core2 = GL.orb(b, "core_cream", [cx, cy], 58, CREAM, 40);
  GL.breathScale(core2, D, 58, 5, 1, 0);
  var gb = FX.adj(b, "bloom");
  FX.glow(gb, 22, 0.3, 75, GOLD, ORANGE);

  var c = GL.comp(tag, W, H, D);
  GL.vignette(c, b, cx, cy, 236, 236, 70);
  return FX.done(c);
}
