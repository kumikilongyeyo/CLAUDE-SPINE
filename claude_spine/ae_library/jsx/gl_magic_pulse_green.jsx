// gl_magic_pulse_green: emerald healing / nature glow. Seamless loop of 38 frames (1.52 s @25; 1.5 s is 37.5 frames).
// A ground circle seen in perspective pulses once per loop (soft disc + bright ring + a rotating rune ring + two
// expanding pulse rings half a loop apart); a soft aura column with cycling fractal-noise shimmer rises from it;
// soft light particles, fluttering leaf-like wisps (Kenney trace / twirl) and 4-point sparkles float upward.
// Colour: mint-white core -> emerald -> deep green edges, a touch of lime in the sparkles.
$.evalFile(FXLIB_DIR + "gl_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, D = 1.52, gx = 256, gy = 372, RX = 168, RY = 54;
  RE.purge("gl_magic_pulse_green_v");
  var tag = "gl_magic_pulse_green_v" + V;
  var WHITE = FX.rgb("EEFFF4"), MINT = FX.rgb("A4FFCF"), EMER = FX.rgb("22E37E"), GREEN = FX.rgb("10B24E"),
      DEEP = FX.rgb("067A33"), LIME = FX.rgb("C8FF5C"), TEAL = FX.rgb("19D6A0");
  var rnd = FX.rng(1515);
  var PULSE = "var ph=time/" + D + ";ph=ph-Math.floor(ph);var e=Math.pow(0.5+0.5*Math.cos(2*Math.PI*ph),3);";   // peak at t=0

  // rune ring precomp (rotates by whole symmetry steps per loop, squashed into perspective in the body)
  var rune = GL.pre(tag + "_rune", 512, 512, D);
  var rl = GL.sprite(rune, GL.K + "magic_02.png", "rune", { pos: [256, 256], color: [1, 1, 1] });
  GL.ex(rl.rotation, "360/7*time/" + D);
  var rl2 = GL.sprite(rune, GL.K + "circle_04.png", "rune_ring", { pos: [256, 256], scale: 104, color: [1, 1, 1], op: 70 });

  // aura column shimmer precomp (cycling noise through a soft vertical matte)
  var col = GL.pre(tag + "_column", W, H, D);
  var n = FX.noise(col, "wisps", { type: 1, noise: 4, contrast: 160, brightness: -25, sw: 40, sh: 260, complexity: 3, seed: 8,
    evo: [[0, 0], [D, 360]] });
  FX.set(n.fx, "Cycle Evolution", 1); FX.set(n.fx, "Cycle (in Revolutions)", 1);
  var cm = FX.shape(col, "column_matte");
  var g = FX.group(cm, "ellipse", { size: [RX * 1.5, 330], fill: [1, 1, 1] }); cm.position.setValue([gx, gy - 140]);
  FX.blur(cm, 60);
  cm.moveBefore(n.layer); FX.matte(n.layer, cm, false);
  GL.opaque(col);

  var b = GL.pre(tag + "_body", W, H, D);
  // 1. ground: wide deep glow, emerald disc, pulsing
  var gd = GL.orb(b, "ground_deep", [gx, gy], [150, 55], DEEP, 70);
  GL.ex(gd.opacity, PULSE + "40+30*e");
  var gm = GL.orb(b, "ground_disc", [gx, gy], [95, 32], GREEN, 80);
  GL.ex(gm.opacity, PULSE + "22+38*e");
  GL.ex(gm.scale, PULSE + "[95+10*e,32+3.5*e]");
  // 2. aura column + shimmer
  var ac = GL.orb(b, "aura_column", [gx, gy - 110], [70, 120], GREEN, 45);
  GL.ex(ac.opacity, PULSE + "32+22*e");
  var cl = b.layers.add(col); cl.name = "column_wisps"; cl.blendingMode = BlendingMode.ADD;
  GL.tritone(cl, MINT, GREEN, [0, 0, 0]); GL.lumaAlpha(cl);
  GL.ex(cl.opacity, PULSE + "32+24*e");
  // 3. rune circle + bright ground ring
  var ru = b.layers.add(rune); ru.name = "rune_ground"; ru.blendingMode = BlendingMode.ADD;
  ru.position.setValue([gx, gy]); ru.scale.setValue([RX / 230 * 100, RY / 230 * 100]);
  RE.fill(ru, EMER);
  GL.ex(ru.opacity, PULSE + "50+40*e");
  var ring = GL.sprite(b, GL.K + "circle_02.png", "ground_ring", { pos: [gx, gy], color: MINT });
  ring.scale.setValue([RX / 165 * 100, RY / 165 * 100]);
  GL.ex(ring.opacity, PULSE + "35+65*e");
  // 4. expanding pulse rings (period D, half a loop apart)
  for (var p = 0; p < 2; p++) {
    var pr = GL.sprite(b, GL.K + "circle_02.png", "pulse_ring" + p, { pos: [gx, gy], color: p ? TEAL : EMER });
    var U = "var u=time/" + D + "+" + (p * 0.5) + ";u=u-Math.floor(u);";
    GL.ex(pr.scale, U + "var s=0.35+0.85*(1-Math.pow(1-u,2.2));[" + (RX / 165 * 100) + "*s," + (RY / 165 * 100) + "*s]");
    GL.ex(pr.opacity, U + "var e=Math.min(1,u/0.08)*Math.pow(1-u,1.6);95*e");
  }
  // 5. rising soft light particles
  for (var k = 0; k < 26; k++) {
    var a = rnd() * Math.PI * 2, rr = Math.sqrt(rnd()), x0 = gx + Math.cos(a) * RX * 0.85 * rr, y0 = gy + Math.sin(a) * RY * 0.85 * rr;
    var big = rnd() < 0.3;
    GL.mote(b, GL.K + "circle_05.png", "mote" + k, {
      D: D, k: rnd() < 0.4 ? 2 : 1, ph: rnd(), p0: [x0, y0], p1: [x0 + (rnd() - 0.5) * 40, y0 - 150 - rnd() * 170],
      sway: [5 + rnd() * 9, 1 + Math.floor(rnd() * 2)], swph: rnd(), s0: big ? 5.5 + rnd() * 3 : 2.4 + rnd() * 1.6, s1: big ? 2.5 : 1.2,
      op: big ? 55 + rnd() * 25 : 80 + rnd() * 20, color: [MINT, EMER, WHITE, LIME, EMER][Math.floor(rnd() * 5)],
      fin: 0.15, fout: 0.5, flick: big ? 0 : 0.35, flickN: 3 + Math.floor(rnd() * 3) });
  }
  // 6. leaf-like wisps fluttering upward (flip via scale X, spin)
  var leafTex = ["flame_05.png", "flame_06.png", "magic_05.png", "flame_05.png", "flame_06.png", "magic_05.png", "flame_05.png", "flame_06.png"];
  for (var lf = 0; lf < 11; lf++) {
    var la = rnd() * Math.PI * 2, lx = gx + Math.cos(la) * RX * 0.7, ly = gy + Math.sin(la) * RY * 0.7;
    var tex = leafTex[lf % leafTex.length], s0 = tex.indexOf("twirl") === 0 ? 9 : (tex.indexOf("magic") === 0 ? 7 : 9);
    var L = GL.mote(b, GL.K + tex, "leaf" + lf, { D: D, k: 1, ph: rnd(), p0: [lx, ly], p1: [lx + (rnd() - 0.5) * 70, ly - 190 - rnd() * 120],
      sway: [14 + rnd() * 12, 1], swph: rnd(), s0: s0, s1: s0 * 0.7, op: 85, color: lf % 3 ? EMER : LIME, fin: 0.2, fout: 0.45,
      rot: [rnd() * 360, rnd() * 360 + (rnd() < 0.5 ? -1 : 1) * 360] });
    // flutter: scale X swings through 0 like a leaf turning in the air (2 turns per life)
    GL.ex(L.scale, GL.U(D, 1, 0) + "var s=" + s0 + "+(" + (-0.3 * s0) + ")*u;var f=Math.cos(2*Math.PI*(2*time/" + D + "+" + rnd().toFixed(3) + "));[s*(0.25+0.75*Math.abs(f)),s]");
  }
  // 7. sparkles
  var tw = [[0.08, -80, -150], [0.3, 70, -210], [0.5, -40, -260], [0.7, 110, -120], [0.88, -120, -60]];
  for (var t = 0; t < tw.length; t++) {
    GL.twinkle(b, GL.K + "star_06.png", "sparkle" + t, { D: D, ph: -tw[t][0], len: 0.16, pos: [gx + tw[t][1], gy + tw[t][2]],
      s: 9 + (t % 2) * 4, op: 100, color: t % 2 ? LIME : MINT, rot: t * 23 });
  }
  // 8. hot source at the ground centre
  var hot = GL.orb(b, "source_hot", [gx, gy], [40, 14], WHITE, 80);
  GL.ex(hot.opacity, PULSE + "45+50*e");
  var gb = FX.adj(b, "bloom");
  FX.glow(gb, 18, 0.4, 62, EMER, DEEP);

  var c = GL.comp(tag, W, H, D);
  GL.vignette(c, b, 256, 270, 246, 240, 60);
  return FX.done(c);
}
