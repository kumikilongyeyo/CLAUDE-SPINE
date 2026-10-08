// el_fire_loop: seamless 1.0 s realistic flame column, 384x640 (base at the bottom), for burning a symbol / reel edge.
// Physics: hot gas rises and ACCELERATES (noise streams up faster than the base, tongues stretch as they climb and
// pinch off), small fast licks ride the big slow body, white-hot core at the base -> yellow -> orange -> red tips.
// Loop: the rising noise is rendered for 2 s and cross-faded into 1 s (claude-spine fire-template loopify), the
// threshold/heat colour comes AFTER the crossfade; sprites and embers live on time wrapped to the 1 s period.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 384, H = 640, P = 1.0, BX = 192, BY = 600, F = 0.04;
  EL.purge("el_fire_loop_v");
  var tag = "el_fire_loop_v" + V, rnd = FX.rng(77 + V);
  var TWO_PI = "6.283185307179586";

  // ---------- 1. rising density (2P long)
  var src = EL.comp(tag + "_src", W, H, 2 * P);
  FX.solid(src, "black", [0, 0, 0]);
  function rising(nm, sw, sh, speed, seed, revs, op, blend) {
    var n = FX.noise(src, nm, { type: 1, noise: 3, contrast: 105, brightness: -5, sw: sw, sh: sh, complexity: 5, seed: seed, evo: [[0, 0], [2 * P, 360 * revs * 2]] });
    FX.find(n.fx, "Offset Turbulence").expression = "[value[0], value[1] - time * " + speed + "]";
    if (blend) n.layer.blendingMode = blend;
    if (op !== undefined) n.layer.opacity.setValue(op);
    return n.layer;
  }
  var big = rising("body_noise", 34, 120, 380, 3, 1, 100);
  var lick = rising("lick_noise", 14, 52, 700, 17, 2, 60, BlendingMode.SCREEN);
  // density = (noise + hot body) x height falloff x side falloff, all full-frame ramps (template-style), so the
  // threshold later cuts real tongues instead of a uniform blob
  var bodyR = FX.ramp(src, "hot_body", BX, BY - 30, 150, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.ADD);
  bodyR.layer.anchorPoint.setValue([BX, BY - 30]); bodyR.layer.position.setValue([BX, BY - 30]);
  bodyR.layer.scale.setValue([100, 380]); bodyR.layer.opacity.setValue(70);
  var hR = FX.ramp(src, "height_falloff", BX, -170, 0, [0, 0, 0, 1], [1, 1, 1, 1], BlendingMode.MULTIPLY, true, [BX, BY - 300]);
  var sR = FX.ramp(src, "side_falloff", BX, BY, 175, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.MULTIPLY);
  sR.layer.anchorPoint.setValue([BX, BY]); sR.layer.position.setValue([BX, BY]); sR.layer.scale.setValue([100, 400]);
  var baseFade = FX.ramp(src, "base_fade", BX, BY + 30, 0, [0, 0, 0, 1], [1, 1, 1, 1], BlendingMode.MULTIPLY, true, [BX, BY - 20]);

  // ---------- 2. loopify: late copy (src time t+P) under an early copy fading in over the period
  var luma = EL.comp(tag + "_luma", W, H, P);
  var late = luma.layers.add(src); late.name = "late"; late.startTime = -P;
  var early = luma.layers.add(src); early.name = "early";
  FX.keys(early.opacity, [[0, 0], [P, 100]], false);
  // shake after the loop (cycled turbulence), and a gentle sideways sway at the tips
  var shake = FX.adj(luma, "shake"); EL.turb(shake, 22, 60, P, 1, true, 2);
  var shake2 = FX.adj(luma, "shake_fine"); EL.turb(shake2, 8, 18, P, 2, true, 3);

  // ---------- 3. main comp
  var c = EL.comp(tag, W, H, P);
  // base glow (light the thing that burns)
  var bg = EL.blob(c, "base_glow", FX.rgb("FF6A10"), BX, BY - 30, 120, 110);
  bg.scale.setValue([110, 55]);
  bg.opacity.expression = "38 + 8 * Math.sin(" + TWO_PI + " * 7 * time / " + P + ") + 6 * Math.sin(" + TWO_PI + " * 13 * time / " + P + " + 1.3)";
  // flame body: alpha from density (thin gas vanishes), coloured by heat
  var fb = EL.layerOf(c, luma, "flame_body");
  EL.levels(fb, 0.30, 0.86, 1.0);
  EL.lumaAlpha(fb);
  EL.heat(fb);
  // photo fire as material inside the body: real flame texture, displaced by the looping density
  var pf = EL.tex(c, EL.R + "fire_01.png", "photo_fire", { blend: BlendingMode.ADD });
  pf.anchorPoint.setValue([515, 330]); pf.position.setValue([BX, BY - 240]);
  pf.scale.setValue([120, 150]);
  EL.heat(pf);
  EL.ell(pf, 515, 330, 470, 300, 110);
  var dm = FX.fx(pf, "ADBE Displacement Map");
  dm.property("ADBE Displacement Map-0001").setValue(fb.index + 0);    // re-set below once the map layer exists
  var map = EL.layerOf(c, luma, "disp_map"); map.enabled = false; map.moveToEnd();
  dm.property("ADBE Displacement Map-0001").setValue(map.index);
  dm.property("ADBE Displacement Map-0002").setValue(5); dm.property("ADBE Displacement Map-0003").setValue(22);
  dm.property("ADBE Displacement Map-0004").setValue(5); dm.property("ADBE Displacement Map-0005").setValue(60);
  var pfm = EL.layerOf(c, luma, "photo_fire_matte"); pfm.moveBefore(pf); EL.levels(pfm, 0.32, 0.8, 1.0);
  pf.setTrackMatte(pfm, TrackMatteType.LUMA);
  pf.opacity.setValue(70);

  // tongues: Kenney flame cards born at the base, stretching and accelerating up, pinching off (wrapped time)
  var NT = 10;
  for (var k = 0; k < NT; k++) {
    var L = P / 2, ph = (k / NT) * L + rnd() * 0.02, x0 = BX + (rnd() - 0.5) * 150, nm = ["flame_05", "flame_06"][k % 2];
    var drift = (rnd() - 0.5) * 60, sx = 24 + rnd() * 14, rise0 = 200 + rnd() * 80, acc = 1300 + rnd() * 600;
    for (var pass = 0; pass < 2; pass++) {
      var tg = EL.tex(c, EL.K + nm + ".png", "tongue" + k + (pass ? "_core" : ""), { anchor: [258, 360], blend: BlendingMode.ADD });
      RE.fill(tg, pass ? FX.rgb("FFE7A0") : FX.rgb("FF7E1A"));
      var u = "var L = " + L + ", u = ((time + " + ph.toFixed(4) + ") % L + L) % L, f = u / L;";
      var yb = BY - 30 - Math.abs(x0 - BX) * 0.5;
      tg.position.expression = u + " [" + x0 + " + " + drift + " * f + 6 * Math.sin(f * 9), " + yb + " - (" + rise0 + " * u + 0.5 * " + acc + " * u * u)]";
      var s1 = sx * (pass ? 0.55 : 1);
      tg.scale.expression = u + " var sy = " + s1 + " * (0.5 + 1.6 * Math.sqrt(f)); [" + s1 + " * (1 - 0.55 * f), sy]";
      tg.opacity.expression = u + " " + (pass ? 85 : 75) + " * Math.min(1, f / 0.15) * Math.pow(1 - f, 1.4)";
      tg.rotation.setValue(drift * 0.15);
    }
  }
  // embers drifting up on the draft, swaying (period P each: invisible at the wrap)
  for (var e = 0; e < 16; e++) {
    var d = EL.dot(c, "ember" + e, 2.4 + rnd() * 2, 2.4 + rnd() * 2, FX.rgb("FFC860"));
    d.layer.blendingMode = BlendingMode.ADD; d.layer.motionBlur = true;
    var ph2 = rnd() * P, ex = BX + (rnd() - 0.5) * 170, top = 60 + rnd() * 200, sway = 10 + rnd() * 22, fr = 1 + Math.floor(rnd() * 3);
    var ue = "var u = ((time + " + ph2.toFixed(4) + ") % " + P + " + " + P + ") % " + P + ", f = u / " + P + ";";
    d.layer.position.expression = ue + " [" + ex + " + " + sway + " * Math.sin(" + TWO_PI + " * " + fr + " * f + " + (rnd() * 6).toFixed(2) + "), " + (BY - 60) + " - (" + (BY - 60 - top) + ") * Math.pow(f, 1.4)]";
    d.layer.opacity.expression = ue + " 100 * Math.min(1, f / 0.1) * Math.pow(1 - f, 1.2) * (0.7 + 0.3 * Math.sin(" + TWO_PI + " * " + (8 + e % 5) + " * f))";
    FX.keys(d.fill, [[0, FX.rgb("FFD070")]], false);
  }
  // air: shimmer (cycled) and bloom; overall flicker at 11 Hz-ish (integer cycles per period)
  var sh = FX.adj(c, "heat_shimmer"); EL.turb(sh, 4, 30, P, 2, true, 2);
  var gl = FX.adj(c, "bloom"); FX.glow(gl, 30, 0.8, 50, FX.rgb("FF8A20"), FX.rgb("B02A08"));
  fb.opacity.expression = "92 + 6 * Math.sin(" + TWO_PI + " * 11 * time / " + P + ") + 3 * Math.sin(" + TWO_PI + " * 17 * time / " + P + " + 2.1)";
  return EL.done(c, "additive", [BX, BY], true);
}
