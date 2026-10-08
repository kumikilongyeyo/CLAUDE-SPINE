// gl_energy_orb: magical cyan-violet energy orb. Seamless 1.6 s loop (40 frames @25).
// Back to front: violet outer bloom, cyan inner bloom, roiling fractal plasma inside the sphere (twirled, cycling),
// real plasma-lamp tendrils (electric_01, two mirrored copies, slow cross-faded rotation + cycling turbulence),
// Kenney twirl / magic swirls orbiting (whole turns per loop), Fresnel rim (Kenney circle_02), thin crackling
// Advanced Lightning arcs across the sphere surface (hold-keyed flicker), white-hot core, cyan/violet Glow.
$.evalFile(FXLIB_DIR + "gl_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, cx = 256, cy = 256, D = 1.6, R = 118, N = 40;
  RE.purge("gl_energy_orb_v");
  var tag = "gl_energy_orb_v" + V;
  var CORE = FX.rgb("EAFFFF"), ICE = FX.rgb("9EF4FF"), CYAN = FX.rgb("22DDFF"), AZURE = FX.rgb("3A7CFF"),
      VIOLET = FX.rgb("7440FF"), DEEPV = FX.rgb("4512B0"), MAG = FX.rgb("C24BFF");
  var rnd = FX.rng(1608);

  // --- roiling plasma inside the sphere (precomp so the matte is clean)
  var pl = GL.pre(tag + "_plasma", W, H, D);
  var n = FX.noise(pl, "plasma_noise", { type: 6, noise: 4, contrast: 170, brightness: -32, scale: 34, complexity: 4, seed: 21,
    evo: [[0, 0], [D, 720]] });
  FX.set(n.fx, "Cycle Evolution", 1); FX.set(n.fx, "Cycle (in Revolutions)", 2);
  var tw = FX.fx(n.layer, "ADBE Twirl"); FX.set(tw, "Angle", 160); FX.set(tw, "Twirl Radius", 26); FX.set(tw, "Twirl Center", [cx, cy]);
  var pm = FX.shape(pl, "sphere_matte");
  FX.group(pm, "ellipse", { size: [R * 2 - 10, R * 2 - 10], fill: [1, 1, 1] }); pm.position.setValue([cx, cy]);
  FX.blur(pm, 22);
  pm.moveBefore(n.layer); FX.matte(n.layer, pm, false);
  GL.opaque(pl);

  // --- crackling arcs precomp
  var ar = GL.pre(tag + "_arcs", W, H, D);
  var arcs = [];
  for (var k = 0; k < 7; k++) {
    var a0 = rnd() * Math.PI * 2, r0 = R * (0.35 + rnd() * 0.6), da = (0.6 + rnd() * 0.9) * (rnd() < 0.5 ? -1 : 1), r1 = R * (0.75 + rnd() * 0.25);
    var p0 = [cx + Math.cos(a0) * r0, cy + Math.sin(a0) * r0], p1 = [cx + Math.cos(a0 + da) * r1, cy + Math.sin(a0 + da) * r1];
    var s = FX.solid(ar, "arc" + k, [0, 0, 0]);
    var lf = FX.fx(s, "ADBE Lightning 2");
    FX.set(lf, "Lightning Type", 2);
    FX.set(lf, "Origin", p0); FX.set(lf, "Contextual Control", p1);
    FX.set(lf, "Core Radius", 1.1); FX.set(lf, "Core Opacity", 100); FX.set(lf, "Core Color", [1, 1, 1, 1]);
    FX.set(lf, "Glow Radius", 10); FX.set(lf, "Glow Opacity", 55); FX.set(lf, "Glow Color", [CYAN[0], CYAN[1], CYAN[2], 1]);
    FX.set(lf, "Turbulence", 1.6); FX.set(lf, "Forking", 0.22); FX.set(lf, "Decay", 0.45); FX.set(lf, "Complexity", 7);
    // conductivity jumps every 2 frames (crackle), on/off windows
    var ck = [], ok = [], on0 = Math.floor(rnd() * N), len = 4 + Math.floor(rnd() * 5), on1 = (on0 + 14 + Math.floor(rnd() * 10)) % N;
    for (var f = 0; f < N; f += 2) ck.push([f / 25, rnd() * 50]);
    for (var g = 0; g < N; g++) {
      var vis = ((g - on0 + N) % N) < len || ((g - on1 + N) % N) < Math.max(2, len - 2);
      ok.push([g / 25, vis ? (g % 2 ? 70 : 100) : 0]);
    }
    FX.keys(FX.find(lf, "Conductivity State"), ck, "hold");
    FX.keys(s.opacity, ok, "hold");
    s.blendingMode = BlendingMode.ADD;
    arcs.push(s);
  }

  var b = GL.pre(tag + "_body", W, H, D);
  // 1. blooms
  var bv = GL.orb(b, "bloom_violet", [cx, cy], 165, DEEPV, 70);
  GL.breathScale(bv, D, 165, 6, 1, 0); GL.breathOp(bv, D, 62, 10, 1, 0);
  var bm = GL.orb(b, "bloom_violet2", [cx, cy], 118, VIOLET, 60);
  GL.breathScale(bm, D, 118, 5, 1, 0.1);
  var bc = GL.orb(b, "bloom_cyan", [cx, cy], 80, AZURE, 40);
  GL.breathOp(bc, D, 50, 12, 2, 0.2);
  // 2. plasma interior
  var pll = b.layers.add(pl); pll.name = "plasma"; pll.blendingMode = BlendingMode.ADD;
  GL.tritone(pll, CYAN, DEEPV, [0, 0, 0]); GL.lumaAlpha(pll); GL.breathOp(pll, D, 60, 15, 2, 0);
  // 3. real plasma tendrils (two mirrored copies so they fill every direction)
  var ef = GL.photoSrc(tag + "_plasmasrc", GL.R + "electric_01.png", D, [[384, 462, 300, 300, 90], ["rect", 340, 485, 430, 1024, 30, "sub"]]);
  for (var e = 0; e < 2; e++) {
    var pr = GL.loopRot(b, ef, "tendrils" + e, D, e ? -50 : 50, { pos: [cx, cy], anchor: [384, 462], scale: 38, rot0: e ? 180 : 0, op: 90 });
    for (var q = 0; q < 2; q++) {
      var L = pr[q];
      if (e) L.scale.setValue([-38, 38]);
      GL.tritone(L, ICE, VIOLET, [0, 0, 0]);
      var td = FX.fx(L, "ADBE Turbulent Displace"); FX.set(td, "Amount", 30); FX.set(td, "Size", 60);
      FX.set(td, "Cycle Evolution", 1); FX.set(td, "Cycle (in Revolutions)", 1);
      FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 360]], false);
      GL.lumaAlpha(L);
    }
  }
  // 4. swirls orbiting (whole turns per loop), Kenney twirl + magic
  var sw = [["twirl_01.png", 62, 360, CYAN, 70], ["twirl_02.png", 55, -360, VIOLET, 80], ["twirl_03.png", 46, 720, ICE, 55],
            ["twirl_01.png", 70, -720, MAG, 35]];
  for (var w = 0; w < sw.length; w++) {
    var tl = GL.sprite(b, GL.K + sw[w][0], "swirl" + w, { pos: [cx, cy], scale: sw[w][1], color: sw[w][3] });
    GL.ex(tl.rotation, (w * 90) + "+" + sw[w][2] + "*time/" + D);
    GL.breathOp(tl, D, sw[w][4], sw[w][4] * 0.3, 2, w * 0.25);
  }
  var mg = GL.sprite(b, GL.K + "magic_02.png", "rune_ring", { pos: [cx, cy], scale: 62, color: VIOLET, op: 30 });
  GL.ex(mg.rotation, "-360*time/" + D + "/1");
  // 5. Fresnel rim
  var rim = GL.sprite(b, GL.K + "circle_02.png", "rim", { pos: [cx, cy], scale: 76, color: CYAN });
  GL.breathOp(rim, D, 48, 12, 2, 0);
  var rim2 = GL.sprite(b, GL.K + "circle_03.png", "rim_violet", { pos: [cx, cy], scale: 80, color: VIOLET, op: 25 });
  // 6. arcs
  var al = b.layers.add(ar); al.name = "arcs"; al.blendingMode = BlendingMode.ADD;
  // 7. core
  var c1 = GL.orb(b, "core_cyan", [cx, cy], 34, CYAN, 50); GL.breathScale(c1, D, 34, 5, 2, 0);
  var c2 = GL.orb(b, "core_white", [cx, cy], 14, CORE, 100); GL.breathScale(c2, D, 14, 2, 4, 0);
  var gb = FX.adj(b, "bloom");
  FX.glow(gb, 16, 0.3, 72, CYAN, VIOLET);

  var c = GL.comp(tag, W, H, D);
  GL.vignette(c, b, cx, cy, 238, 238, 60);
  return FX.done(c);
}
