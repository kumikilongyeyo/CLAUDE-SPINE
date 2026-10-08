// re_pink_radial_burst: realistic version of pr_pink_burst_v16 (1200x1200, SEAMLESS 1.92 s loop; the exact comp's
// rays are the light source). Volumetric light: zoom-blurred light shafts and a soft core haze from the rays, hot
// energy streaks (the ray heads, sharpened), drifting photo bokeh and dust motes flying out. Every added motion is a
// function of (time % L), so frame 48 == frame 0.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "pr_pink_burst_v16", W = 1200, H = 1200, L = 1.92, cx = 600, cy = 600;
  RE.purge("re_pink_radial_burst_v");
  var tag = "re_pink_radial_burst_v" + V;
  var src = RE.findComp(SRC);
  var rnd = FX.rng(808);
  var PINK = FX.rgb("FF6FD0"), HOT = FX.rgb("FFD0F2"), PLUM = FX.rgb("6A1E70"), VIO = FX.rgb("8A3CFF");
  var T = "(time % " + L + ")", TWO = "2 * Math.PI * " + T + " / " + L;
  var c = RE.comp(tag, W, H, L);

  // 1. volumetric shafts: the rays zoom-blurred outwards (two lengths), additive
  function shaft(nm, amount, col, op) {
    var l = RE.light(c, src, nm, col, 0, op);
    var rb = FX.fx(l, "ADBE Radial Blur"); RE.trySet(rb, "Type", 2); FX.set(rb, "Amount", amount); FX.find(rb, "Center").setValue([cx, cy]);
    RE.trySet(rb, "Antialiasing (Best Quality)", 2);
    return l;
  }
  shaft("shafts_long", 60, PLUM, 28);
  shaft("shafts_mid", 25, PINK, 10);
  // 2. bokeh: two photos tinted pink/violet, breathing on loop sines, masked soft, behind the rays
  var bk = [["bokeh_02.png", PINK, 0], ["bokeh_01.png", VIO, 1]];
  for (var i = 0; i < bk.length; i++) {
    var b = RE.tex(c, RE.R + bk[i][0], "bokeh" + i, { pos: [cx, cy], blend: BlendingMode.SCREEN });
    RE.ellMask(b, 260, 60);
    // keep the dark centre hole clear of bokeh: a soft subtract mask at the layer point under the comp centre
    var bm = RE.circMask(b, 512, 341, 75, 60); bm.maskMode = MaskMode.SUBTRACT;
    RE.tint(b, bk[i][1]);
    b.scale.expression = "var s = " + (150 + i * 30) + " + 6 * Math.sin(" + TWO + " + " + i + "); [s, s]";
    b.rotation.expression = (i ? "-" : "") + "8 * Math.sin(" + TWO + ")";
    b.opacity.setValue(i ? 22 : 30);
  }
  // 3. the rays themselves + hot cores of the brightest heads
  var base = c.layers.add(src); base.name = "rays"; base.blendingMode = BlendingMode.ADD;
  var hot = c.layers.add(src); hot.name = "ray_heads";
  var lv = FX.fx(hot, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.7); lv.property("ADBE Pro Levels2-0005").setValue(1.0);
  RE.tint(hot, HOT); FX.blur(hot, 3);
  hot.blendingMode = BlendingMode.ADD; hot.opacity.setValue(25);
  // 4. dust motes: each flies out along its ray and loops exactly every L (phase-shifted), fading in and out
  for (var k = 0; k < 70; k++) {
    var a = rnd() * 360, r0 = 120 + rnd() * 80, r1 = 420 + rnd() * 260, ph = rnd(), sz = 3 + rnd() * rnd() * 9, cyc = rnd() < 0.5 ? 1 : 2;
    var d = FX.shape(c, "mote" + k);
    FX.group(d, "ellipse", { size: [sz, sz], fill: rnd() < 0.3 ? HOT : PINK });
    var u = "var a = " + (a * Math.PI / 180).toFixed(4) + "; var p = ((" + T + " / " + L + ") * " + cyc + " + " + ph.toFixed(4) + ") % 1;";
    d.position.expression = u + " var r = " + r0.toFixed(1) + " + (" + (r1 - r0).toFixed(1) + ") * p * p; [" + cx + " + Math.cos(a) * r, " + cy + " + Math.sin(a) * r]";
    d.opacity.expression = u + " " + (60 + rnd() * 40).toFixed(0) + " * Math.sin(Math.PI * p)";
    d.motionBlur = true; d.blendingMode = BlendingMode.ADD;
  }
  // 5. bloom
  var gb = FX.adj(c, "bloom"); FX.glow(gb, 30, 0.08, 85, PINK, PLUM);
  return FX.done(c);
}
