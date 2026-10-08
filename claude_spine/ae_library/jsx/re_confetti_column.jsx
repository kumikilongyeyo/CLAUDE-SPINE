// re_confetti_column: realistic version of cb_confetti_column_v2 - the SAME flakes (same seed, same draw order, so the
// same positions, drift, flip and spin) re-made as metallic foil: each flake's colour is shaded by how much it faces
// the camera (|cos| of its flip), with a sharp white specular flash when it turns face-on under the light (gated by a
// second slow phase so flashes are sparse), a bright foil edge, motion blur (shutter 180) and a bloom that only the
// flashes reach. Curled foil streamers shade the same way. Same 600x1320 frame and 1.0 s seamless loop.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var W = 600, H = 1320, D = 1.0, FPS = 30, XL = 141, XR = 459;
  var name = "re_cb_confetti_column_v" + V;
  var c = FX.comp(name, W, H, FPS, D, RE.FOLDER);
  c.motionBlur = true; c.shutterAngle = 180; c.shutterPhase = -90;
  try { c.motionBlurSamplesPerFrame = 16; c.motionBlurAdaptiveSampleLimit = 64; } catch (x) {}
  // metallic foil palette (deeper base than the flat colours; highlights come from the shading)
  var COLS = ["1EA8E0", "1F5FD8", "7CCC1E", "2EB850", "E0B818", "D82828", "C02AB0", "7428C8", "1EA8E0", "1F5FD8", "7CCC1E"];
  var rnd = FX.rng(77), r2 = FX.rng(5077), TAU = "2 * Math.PI";
  function periodic(l, x0, y0) {          // identical to the exact comp (same rnd draws)
    var fx = 1 + Math.floor(rnd() * 2), fy = 1 + Math.floor(rnd() * 2), ax = 8 + rnd() * 24, ay = 16 + rnd() * 50;
    var p1 = rnd() * 6.28, p2 = rnd() * 6.28, p3 = rnd() * 6.28, p4 = rnd() * 6.28;
    var k = 1 + Math.floor(rnd() * 3), m = Math.floor(rnd() * 3) - 1, q = 1 + Math.floor(rnd() * 2), r0 = rnd() * 360;
    l.position.expression = "[" + x0 + " + " + ax + " * Math.sin(" + TAU + " * time * " + fx + " / " + D + " + " + p1 + "), " +
      y0 + " - " + ay + " * Math.sin(" + TAU + " * time * " + fy + " / " + D + " + " + p2 + ")]";
    l.scale.expression = "var s = Math.cos(" + TAU + " * time * " + k + " / " + D + " + " + p3 + "); [100 * (0.12 + 0.88 * Math.abs(s)) * (s < 0 ? -1 : 1), 100 * (0.8 + 0.2 * Math.cos(" + TAU + " * time / " + D + " + " + p4 + "))]";
    l.rotation.expression = r0 + " + 360 * " + m + " * time / " + D;
    l.motionBlur = true;
    return { k: k, p3: p3, q: q, p4: p4 };
  }
  // colour = base shaded by facing + specular white flash (sparse: needs the light phase too)
  function foilExpr(base, ph) {
    var g = r2() * 6.28, gq = 1 + Math.floor(r2() * 2);
    return "var f = Math.abs(Math.cos(" + TAU + " * time * " + ph.k + " / " + D + " + " + ph.p3 + "));" +
      "var L = Math.max(0, Math.sin(" + TAU + " * time * " + gq + " / " + D + " + " + g + "));" +
      "var spec = 0.95 * Math.pow(f, 30) * Math.pow(L, 3);" +
      "var sh = 0.3 + 0.7 * Math.pow(f, 1.5);" +
      "var b = [" + base.join(",") + "];" +
      "[Math.min(1, b[0] * sh + spec), Math.min(1, b[1] * sh + spec), Math.min(1, b[2] * sh + spec), 1]";
  }
  function edgeX() {
    var r = rnd();
    if (r < 0.18) return XL + 20 + rnd() * (XR - XL - 40);
    var side = rnd() < 0.5 ? XL : XR, d = Math.pow(rnd(), 0.8) * 95;
    return side + (rnd() < 0.62 ? 1 : -1) * d * (side === XL ? -1 : 1);
  }
  for (var i = 0; i < 150; i++) {
    var l = FX.shape(c, "flake" + i), w = (14 + rnd() * 16) / 2, h = (9 + rnd() * 11) / 2;
    var col = FX.rgb(COLS[Math.floor(rnd() * COLS.length)]);
    var j1 = function () { return (rnd() - 0.5) * 0.5; };
    var g = FX.group(l, "path", { points: [[-w * (1 + j1()), -h * (1 + j1())], [w * (1 + j1()), -h * (1 + j1())], [w * (1 + j1()), h * (1 + j1())], [-w * (1 + j1()), h * (1 + j1())]], closed: true, fill: col,
      stroke: [1, 1, 1], width: 1.2 });
    l.anchorPoint.setValue([0, 0]);
    var ph = periodic(l, edgeX(), 30 + rnd() * (H - 60));
    g.fillC.expression = foilExpr(col, ph);
    g.strokeO.expression = "var f = Math.abs(Math.cos(" + TAU + " * time * " + ph.k + " / " + D + " + " + ph.p3 + ")); 12 + 40 * (1 - f)";   // edge catches light when turned
    FX.blur(l, 0.5);
  }
  var RC = ["7428C8", "B02AB0", "D83050", "6424C0"];
  for (var j = 0; j < 26; j++) {
    var r = FX.shape(c, "ribbon" + j), sz = 10 + rnd() * 10;
    sz = 16 + rnd() * 14;
    var pts = [[-sz, sz * 0.7], [-sz * 0.1, -sz * 0.2], [-sz * 0.45, -sz * 0.6], [-sz * 0.6, -sz * 0.1], [sz * 0.4, 0], [sz, -sz * 0.7]];
    var ti = [[0, 0], [-sz * 0.3, sz * 0.3], [sz * 0.25, 0], [0, -sz * 0.25], [-sz * 0.3, 0], [-sz * 0.2, sz * 0.2]];
    var to = [[sz * 0.3, -sz * 0.2], [sz * 0.3, -sz * 0.3], [-sz * 0.25, 0], [0, sz * 0.25], [sz * 0.3, 0], [0, 0]];
    var rc = FX.rgb(RC[j % RC.length]);
    var rg = FX.group(r, "path", { points: pts, inT: ti, outT: to, stroke: rc, width: 4, taper: [20, 30] });
    r.anchorPoint.setValue([0, 0]);
    var ph2 = periodic(r, edgeX(), 30 + rnd() * (H - 60));
    rg.strokeProp.property("ADBE Vector Stroke Color").expression = foilExpr(rc, ph2);
  }
  // faint glints of light on foil (the exact comp's rainbow dashes become tiny lens streaks)
  for (var k = 0; k < 10; k++) {
    var gl = FX.shape(c, "glint" + k), len = 30 + rnd() * 30;
    FX.group(gl, "path", { points: [[-len / 2, 0], [len / 2, 0]], stroke: FX.rgb(["FFE8B0", "D0F0FF", "FFD0E8"][k % 3]), width: 1.4, taper: [80, 80] });
    gl.anchorPoint.setValue([0, 0]);
    gl.position.setValue([XR + 20 + rnd() * 110, 60 + rnd() * (H - 120)]);
    if (k % 2) gl.position.setValue([XL - 20 - rnd() * 110, 60 + rnd() * (H - 120)]);
    gl.rotation.setValue(-8 + rnd() * 16);
    gl.opacity.expression = "var v = Math.sin(2 * Math.PI * time * " + (2 + k % 3) + " / " + D + " + " + (rnd() * 6.28) + "); 60 * Math.max(0, v)";
    gl.blendingMode = BlendingMode.ADD;
  }
  var bl = FX.adj(c, "spec_bloom"); FX.glow(bl, 7, 0.5, 93, [1, 1, 1], FX.rgb("FFE0A0"));
  return FX.done(c);
}
