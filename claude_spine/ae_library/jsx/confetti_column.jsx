// confetti_column (clip B, reel 4 anticipation, t 0.0-1.4): opaque coloured confetti flakes (cyan, blue, lime,
// yellow, red, magenta, purple) and a few curly ribbons hovering around both edge lines of the fire column, drifting a
// little, flipping (scale X through 0) and twinkling. NORMAL blend. Same frame as cb_reel_fire (600x1320, centre clip
// px 1079,760, edge lines at local x 141 / 459). Seamless 1.0 s loop: every motion is an integer number of cycles.
function BUILD(V) {
  var W = 600, H = 1320, D = 1.0, FPS = 30, XL = 141, XR = 459;
  var name = "cb_confetti_column_v" + V;
  var c = FX.comp(name, W, H, FPS, D);
  var COLS = ["3CC8F0", "2C7CF0", "9CE83C", "52D86C", "F0E040", "F04646", "D646C8", "9046E0", "3CC8F0", "2C7CF0", "9CE83C"];
  var rnd = FX.rng(77), TAU = "2 * Math.PI";
  function periodic(l, x0, y0) {
    var fx = 1 + Math.floor(rnd() * 2), fy = 1 + Math.floor(rnd() * 2), ax = 8 + rnd() * 24, ay = 16 + rnd() * 50;
    var p1 = rnd() * 6.28, p2 = rnd() * 6.28, p3 = rnd() * 6.28, p4 = rnd() * 6.28;
    var k = 1 + Math.floor(rnd() * 3), m = Math.floor(rnd() * 3) - 1, q = 1 + Math.floor(rnd() * 2), r0 = rnd() * 360;
    l.position.expression = "[" + x0 + " + " + ax + " * Math.sin(" + TAU + " * time * " + fx + " / " + D + " + " + p1 + "), " +
      y0 + " - " + ay + " * Math.sin(" + TAU + " * time * " + fy + " / " + D + " + " + p2 + ")]";
    l.scale.expression = "var s = Math.cos(" + TAU + " * time * " + k + " / " + D + " + " + p3 + "); [100 * (0.25 + 0.75 * Math.abs(s)) * (s < 0 ? -1 : 1), 100]";
    l.rotation.expression = r0 + " + 360 * " + m + " * time / " + D;
    l.opacity.expression = "var v = Math.sin(" + TAU + " * time * " + q + " / " + D + " + " + p4 + "); 100 * Math.min(1, Math.max(0.6, v * 1.4 + 0.9))";
  }
  function edgeX() {
    var r = rnd();
    if (r < 0.18) return XL + 20 + rnd() * (XR - XL - 40);                 // a few drift over the column
    var side = rnd() < 0.5 ? XL : XR, d = Math.pow(rnd(), 0.8) * 95;
    return side + (rnd() < 0.62 ? 1 : -1) * d * (side === XL ? -1 : 1);     // most just OUTSIDE the edge lines
  }
  // flakes
  for (var i = 0; i < 150; i++) {
    var l = FX.shape(c, "flake" + i), w = (14 + rnd() * 16) / 2, h = (9 + rnd() * 11) / 2;
    var col = FX.rgb(COLS[Math.floor(rnd() * COLS.length)]);
    var j1 = function () { return (rnd() - 0.5) * 0.5; };          // irregular torn-paper quad
    var g = FX.group(l, "path", { points: [[-w * (1 + j1()), -h * (1 + j1())], [w * (1 + j1()), -h * (1 + j1())], [w * (1 + j1()), h * (1 + j1())], [-w * (1 + j1()), h * (1 + j1())]], closed: true, fill: col });
    l.anchorPoint.setValue([0, 0]);
    periodic(l, edgeX(), 30 + rnd() * (H - 60));
    FX.blur(l, 0.7);
  }
  // curly ribbons (purple / magenta / red squiggles)
  var RC = ["9046E0", "C040C0", "E04060", "7A3CD0"];
  for (var j = 0; j < 26; j++) {
    var r = FX.shape(c, "ribbon" + j), sz = 10 + rnd() * 10;
    sz = 16 + rnd() * 14;                                         // a curled streamer: one loop and a tail
    var pts = [[-sz, sz * 0.7], [-sz * 0.1, -sz * 0.2], [-sz * 0.45, -sz * 0.6], [-sz * 0.6, -sz * 0.1], [sz * 0.4, 0], [sz, -sz * 0.7]];
    var ti = [[0, 0], [-sz * 0.3, sz * 0.3], [sz * 0.25, 0], [0, -sz * 0.25], [-sz * 0.3, 0], [-sz * 0.2, sz * 0.2]];
    var to = [[sz * 0.3, -sz * 0.2], [sz * 0.3, -sz * 0.3], [-sz * 0.25, 0], [0, sz * 0.25], [sz * 0.3, 0], [0, 0]];
    FX.group(r, "path", { points: pts, inT: ti, outT: to, stroke: FX.rgb(RC[j % RC.length]), width: 4, taper: [20, 30] });
    r.anchorPoint.setValue([0, 0]);
    periodic(r, edgeX(), 30 + rnd() * (H - 60));
  }
  // tiny rainbow dash glints (the faint dotted streaks beside the column)
  for (var k = 0; k < 10; k++) {
    var gl = FX.shape(c, "glint" + k), len = 30 + rnd() * 30;
    FX.group(gl, "path", { points: [[-len / 2, 0], [len / 2, 0]], stroke: FX.rgb(["FFE080", "80E0FF", "FF80C0"][k % 3]), width: 1.6, taper: [60, 60] });
    gl.anchorPoint.setValue([0, 0]);
    gl.position.setValue([XR + 20 + rnd() * 110, 60 + rnd() * (H - 120)]);
    if (k % 2) gl.position.setValue([XL - 20 - rnd() * 110, 60 + rnd() * (H - 120)]);
    gl.rotation.setValue(-8 + rnd() * 16);
    gl.opacity.expression = "var v = Math.sin(2 * Math.PI * time * " + (2 + k % 3) + " / " + D + " + " + (rnd() * 6.28) + "); 70 * Math.max(0, v)";
  }
  return FX.done(c);
}
