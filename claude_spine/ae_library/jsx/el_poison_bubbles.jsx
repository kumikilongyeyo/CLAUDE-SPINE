// el_poison_bubbles: seamless toxic bubbling cloud, 512x512, loop of 38 frames (1.52 s at 25 fps).
// Physics: a heavy green vapour cloud churns in place (slow roll, breathing); bubbles nucleate at its surface, rise
// slowly while they grow (lower pressure), wobble side to side (wake shedding), then POP: the film snaps (one frame
// of a bright ring) and flings a few droplets on short parabolas; thick drops hang from the underside, stretch
// and fall accelerating; wisps of fume rise off the top and thin out. Every motion is periodic in P.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, P = 1.52, F = 0.04, CX = 256, CY = 300;
  EL.purge("el_poison_bubbles_v");
  var tag = "el_poison_bubbles_v" + V, rnd = FX.rng(6060 + V);
  var TP = "6.283185307179586";
  var TOX = FX.rgb("8CFF3A"), TOXL = FX.rgb("D8FF9A"), TOXM = FX.rgb("3FB81C"), TOXD = FX.rgb("10340A"), GOO = FX.rgb("6AE020");
  function per(n, ph) { return "(" + TP + " * " + n + " * time / " + P + " + " + (ph || 0).toFixed(3) + ")"; }
  function wrap(ph) { return "var f = ((time / " + P + " + " + ph.toFixed(4) + ") % 1 + 1) % 1;"; }

  // ---------- fume DENSITY precomp: photo wisps + Kenney cloud cards all filled white, so only their alpha (the
  // density) survives; the main comp colours that density: thin = deep green, thick = glowing yellow-green.
  // (Toning the photos kept their grey detail and read muddy grey-olive.)
  var den = EL.comp(tag + "_density", W, H, P);
  var wisps = ["smoke_02", "smoke_03", "smoke_02", "smoke_04"];
  for (var w = 0; w < wisps.length; w++) {
    for (var inst = 0; inst < 2; inst++) {
      var ph = w * 0.23 + inst * 0.5, wx = CX + (w - 1.5) * 50;
      var wl = EL.tex(den, EL.R + wisps[w] + ".png", "fume" + w + "_" + inst, { anchor: w === 3 ? [360, 350] : (w % 2 ? [480, 300] : [555, 400]), mask: 120, inset: 60 });
      RE.fill(wl, [1, 1, 1]);
      wl.position.expression = wrap(ph) + " [" + wx + " + 20 * Math.sin(" + TP + " * f + " + w + "), " + (CY - 40) + " - 190 * f]";
      wl.scale.expression = wrap(ph) + " var s = " + (w === 3 ? 22 : 30) + " * (0.7 + 0.6 * f); [s * " + (w % 2 ? -1 : 1) + ", s]";
      wl.opacity.expression = wrap(ph) + " 75 * Math.sin(Math.PI * f)";
      wl.rotation.setValue((w - 1.5) * 6);
    }
  }
  var cn = ["smoke_08", "smoke_07", "smoke_04", "smoke_06", "smoke_08"];
  var cpos = [[CX, CY], [CX - 70, CY + 10], [CX + 72, CY + 6], [CX - 20, CY - 34], [CX + 30, CY + 26]];
  for (var k = 0; k < cn.length; k++) {
    var cl = EL.tex(den, EL.K + cn[k] + ".png", "cloud" + k);
    RE.fill(cl, [1, 1, 1]);
    var s0 = [62, 42, 44, 40, 46][k];
    cl.position.expression = "[" + cpos[k][0] + " + 6 * Math.sin" + per(1, k) + ", " + cpos[k][1] + " + 4 * Math.cos" + per(1, k * 1.7) + "]";
    cl.scale.expression = "var s = " + s0 + " * (1 + 0.05 * Math.sin" + per(1, k * 2.1) + "); [s, s * 0.8]";
    cl.rotation.expression = (k * 70) + " + 14 * Math.sin" + per(1, k);
    cl.opacity.setValue(k === 0 ? 95 : 85);
  }

  var c = EL.comp(tag + "_body", W, H, P);
  // 1. thin vapour: the whole density in a deep saturated green
  var thin = EL.layerOf(c, den, "fume_thin"); RE.fill(thin, FX.rgb("1E8A10"));
  // 2. mid density: bright toxic green
  var mid = EL.layerOf(c, den, "fume_mid"); RE.fill(mid, FX.rgb("5CE01E"));
  EL.levels(mid, 0, 1, 1).property("ADBE Pro Levels2-0032").setValue(0.3);
  // 3. thick core: yellow-green, glowing
  var thick = EL.layerOf(c, den, "fume_thick"); RE.fill(thick, FX.rgb("C8FF4A"));
  EL.levels(thick, 0, 1, 1).property("ADBE Pro Levels2-0032").setValue(0.6);
  var glow = EL.layerOf(c, den, "fume_glow", BlendingMode.ADD); RE.fill(glow, FX.rgb("8CFF2A"));
  EL.levels(glow, 0, 1, 1).property("ADBE Pro Levels2-0032").setValue(0.55);
  FX.blur(glow, 14); glow.opacity.expression = "45 + 10 * Math.sin" + per(2);
  // churning toxic noise inside the cloud (cycled), light from above / darker green underneath
  var churn = FX.noise(c, "churn", { type: 6, noise: 3, contrast: 170, brightness: -10, scale: 40, complexity: 4, seed: 5, evo: [[0, 0], [P, 360]], cycle: 1 });
  RE.tint(churn.layer, FX.rgb("E8FF8A"), FX.rgb("0E4A08")); churn.layer.blendingMode = BlendingMode.OVERLAY; churn.layer.opacity.setValue(45);
  var cm = EL.layerOf(c, den, "churn_matte"); cm.moveBefore(churn.layer); churn.layer.setTrackMatte(cm, TrackMatteType.ALPHA);
  var shade = FX.ramp(c, "underside_shade", CX, CY + 90, 0, [0.25, 0.55, 0.12, 1], [1, 1, 1, 1], BlendingMode.MULTIPLY, true, [CX, CY - 20]);
  shade.layer.opacity.setValue(55);
  var sm = EL.layerOf(c, den, "shade_matte"); sm.moveBefore(shade.layer); shade.layer.setTrackMatte(sm, TrackMatteType.ALPHA);

  // 3. drips hanging from the underside: swell, stretch, let go, fall accelerating
  for (var d = 0; d < 5; d++) {
    var ph3 = d / 5 + rnd() * 0.1, dx = CX + (d - 2) * 46 + (rnd() - 0.5) * 20, dy = CY + 56 - Math.abs(d - 2) * 10;
    var dl = EL.dot(c, "drip" + d, 12, 16, GOO);
    EL.bevel(dl.layer, 2, -50, 0.8);
    var u = wrap(ph3) + " var hang = 0.45, t = Math.max(0, f - hang) * " + P + ";";
    dl.layer.anchorPoint.setValue([0, -6]);
    dl.layer.position.expression = u + " [" + dx + ", " + dy + " + (f < hang ? 18 * f / hang : 18 + 900 * t * t)]";
    dl.layer.scale.expression = u + " f < hang ? [60 + 40 * f / hang, 50 + 110 * f / hang] : [80, 170 - 40 * Math.min(1, t * 6)]";
    dl.layer.opacity.expression = u + " 100 * Math.min(1, f / 0.1) * (f > 0.92 ? (1 - f) / 0.08 : 1)";
    dl.layer.motionBlur = true;
  }
  // 4. bubbles: nucleate on the surface, rise + grow + wobble, pop with a ring and droplets
  for (var b = 0; b < 12; b++) {
    var ph4 = b / 12 + rnd() * 0.04, bx = CX + (rnd() - 0.5) * 220, by = CY - 10 + (rnd() - 0.5) * 50;
    var life = 0.5 + rnd() * 0.22, rise = 60 + rnd() * 80, size = 24 + rnd() * 24;
    var ub = wrap(ph4) + " var L = " + life.toFixed(3) + ", g = f / L;";
    var pos = ub + " [" + bx.toFixed(1) + " + 6 * Math.sin(g * 14), " + by.toFixed(1) + " - " + rise.toFixed(1) + " * g * g]";
    var film = EL.tex(c, EL.K + "circle_01.png", "bubble" + b, { blend: BlendingMode.NORMAL });
    RE.fill(film, TOXL); FX.glow(film, 6, 0.8, 40, TOX, TOXM);
    film.position.expression = pos;
    film.scale.expression = ub + " var s = " + (size / 4.2).toFixed(2) + " * (0.25 + 0.75 * Math.sqrt(Math.min(1, g))) * (g > 0.97 ? 1.25 : 1); [s * (1 + 0.06 * Math.sin(g * 20)), s * (1 - 0.06 * Math.sin(g * 20))]";
    film.opacity.expression = ub + " g >= 1 ? 0 : 95 * Math.min(1, g / 0.08)";
    var fill = EL.dot(c, "bubble_body" + b, 100, 100, GOO);
    fill.layer.position.expression = pos;
    fill.layer.scale.expression = ub + " var s = " + (size * 0.92).toFixed(2) + " * (0.25 + 0.75 * Math.sqrt(Math.min(1, g))); [s, s]";
    fill.layer.opacity.expression = ub + " g >= 1 ? 0 : 38 * Math.min(1, g / 0.08)";
    fill.layer.moveAfter(film);
    var hl = EL.dot(c, "bubble_spec" + b, 6, 4, [1, 1, 1]);
    hl.layer.position.expression = ub + " var s = " + (size * 0.5).toFixed(2) + " * (0.25 + 0.75 * Math.sqrt(Math.min(1, g))); " +
      "[" + bx.toFixed(1) + " + 6 * Math.sin(g * 14) - s * 0.35, " + by.toFixed(1) + " - " + rise.toFixed(1) + " * g * g - s * 0.4]";
    hl.layer.scale.expression = ub + " var s = (0.25 + 0.75 * Math.sqrt(Math.min(1, g))) * " + (size / 20).toFixed(2) + " * 100; [s, s]";
    hl.layer.opacity.expression = ub + " g >= 1 ? 0 : 90 * Math.min(1, g / 0.1)";
    hl.layer.rotation.setValue(-35);
    // pop: droplets flung on short parabolas (local time after the pop)
    for (var q = 0; q < 4; q++) {
      var aq = (q / 4) * Math.PI * 2 + rnd() * 0.8, sq = 120 + rnd() * 120;
      var pd = EL.dot(c, "pop" + b + "_" + q, 3.2, 3.2, TOXL);
      pd.layer.motionBlur = true;
      var up = wrap(ph4) + " var L = " + life.toFixed(3) + ", t = (f - L) * " + P + ", bx = " + bx.toFixed(1) + ", by = " + (by - rise).toFixed(1) + ";";
      pd.layer.position.expression = up + " t < 0 ? [bx, by] : [bx + " + (Math.cos(aq) * sq).toFixed(1) + " * t, by + " + (Math.sin(aq) * sq - 120).toFixed(1) + " * t + 0.5 * 900 * t * t]";
      pd.layer.opacity.expression = up + " (t < 0 || t > 0.3) ? 0 : 100 * (1 - t / 0.3)";
    }
    var ring = EL.tex(c, EL.K + "circle_01.png", "pop_ring" + b, { blend: BlendingMode.ADD });
    RE.fill(ring, TOXL);
    var ur = wrap(ph4) + " var L = " + life.toFixed(3) + ", t = (f - L) * " + P + ";";
    ring.position.setValue([bx, by - rise]);
    ring.scale.expression = ur + " var s = " + (size / 4.2).toFixed(2) + " * (1.1 + Math.max(0, t) * 12); [s, s]";
    ring.opacity.expression = ur + " (t < 0 || t > 0.1) ? 0 : 90 * (1 - t / 0.1)";
  }
  // 5. toxic glow
  var ds = FX.adj(c, "vapour_wobble"); EL.turb(ds, 6, 30, P, 1, true, 2);
  var main = EL.edgeSafe(c, tag, 30, 36);
  return EL.done(main, "normal", [CX, CY], true);
}
