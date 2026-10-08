// ca_coin_glow (clip A, t 2.79..3.59): the light on the WIN bar when the X5 lands and the win jumps 21,000 -> 105,000.
// Coins, plumeria flowers and the number are ART; this comp is only the light (additive):
//  - 2.80-2.88 the bar (clip y 1672-1795) is blown out white-cyan, turning pink-white at 2.86, fading by ~2.97
//  - a hot white streak along the top rail (y ~1668) and magenta fringes above (y 1625-1660) / below (y ~1790)
//    from 2.84, the band above turning a purple haze 2.88-2.98
//  - glints popping along the top rail 2.94-3.27 (white glares with purple/blue halos, a few dot sparkles)
// Comp = clip box (0,1560)-(684,1836), S = 1. Comp t=0 = clip 2.79.
function BUILD(V) {
  var W = 684, H = 276, OY = 1560;
  var name = "ca_coin_glow_v" + V;
  var D = 0.8, fps = 30;
  var c = FX.comp(name, W, H, fps, D);
  function T(t) { return t - 2.79; }
  function Y(y) { return y - OY; }

  // soft horizontal band: rect, blurred
  function band(nm, y, h, color, keysOp, blur, wid) {
    var l = FX.shape(c, nm);
    var g = FX.group(l, "rect", { size: [wid || W + 200, h], fill: color });
    l.position.setValue([W / 2, Y(y)]);
    FX.blur(l, blur);
    FX.keys(l.opacity, keysOp, false);
    return { layer: l, g: g };
  }

  // 1. purple haze above the bar (wide, soft) and magenta fringe lines
  var haze = band("purple_haze", 1642, 64, FX.rgb("C04098"), [[T(2.83), 0], [T(2.87), 45], [T(2.92), 70], [T(2.96), 55], [T(3.02), 0]], 18);
  var fT = band("fringe_top", 1652, 12, FX.rgb("FF3CC8"), [[T(2.83), 0], [T(2.85), 80], [T(2.92), 70], [T(2.97), 0]], 5);
  var fB = band("fringe_bottom", 1798, 8, FX.rgb("FF3CC8"), [[T(2.83), 0], [T(2.85), 70], [T(2.93), 60], [T(2.99), 0]], 4);
  var fB2 = band("fringe_base", 1832, 16, FX.rgb("F030C0"), [[T(2.83), 0], [T(2.85), 90], [T(2.93), 80], [T(2.99), 0]], 4);

  // 2. the bar wash: cyan-white blow-out, pinker at the peak
  var wash = band("bar_wash", 1734, 124, FX.rgb("A0E0F0"), [[T(2.795), 0], [T(2.80), 95], [T(2.90), 92], [T(2.94), 55], [T(2.98), 20], [T(3.01), 0]], 8);
  FX.keys(wash.g.fillC, [[T(2.82), FX.rgb("A0E0F0")], [T(2.86), FX.rgb("D8E8F0")], [T(2.92), FX.rgb("A8D4F0")]], false);
  var core = band("wash_core", 1705, 50, FX.rgb("FFFFFF"), [[T(2.795), 0], [T(2.80), 35], [T(2.85), 55], [T(2.88), 40], [T(2.92), 0]], 18, 900);

  // 3. hot streak along the top rail + the rail brightened
  var rail = band("rail_glow", 1670, 22, FX.rgb("C8E0FF"), [[T(2.795), 0], [T(2.80), 55], [T(2.88), 60], [T(2.95), 30], [T(3.0), 0]], 6);
  var streak = FX.shape(c, "rail_streak");
  var sg = FX.group(streak, "path", { points: [[-420, 0], [420, 0]], stroke: [1, 1, 1], width: 6, taper: [60, 60] });
  streak.position.setValue([W / 2, Y(1667)]);
  FX.keys(streak.position, [[T(2.80), [W / 2 - 60, Y(1667)]], [T(2.95), [W / 2 + 60, Y(1667)]]], false);
  FX.keys(streak.opacity, [[T(2.795), 0], [T(2.80), 100], [T(2.9), 80], [T(2.96), 0]], false);
  FX.glow(streak, 10, 1.2, 30, FX.rgb("FFFFFF"), FX.rgb("FFE08A"));

  // 4. glints popping along the top rail: [x, y, t0, t1, w, h, core colour, halo colour]
  var GL = [[60, 1675, 2.93, 3.0, 90, 18, "FFFFFF", "FFE08A"],
            [640, 1665, 2.94, 3.05, 80, 30, "FFF6C8", "B048E0"],
            [465, 1648, 2.98, 3.22, 30, 30, "FFFFFF", "A040E0"],
            [395, 1672, 3.03, 3.18, 120, 20, "FFFFFF", "70B8FF"],
            [665, 1662, 3.16, 3.26, 80, 56, "FFFAC0", "E0E040"],
            [25, 1668, 3.17, 3.28, 110, 24, "FFFFFF", "9AC8FF"]];
  for (var i = 0; i < GL.length; i++) {
    var g = GL[i], t0 = T(g[2]), t1 = T(g[3]), tm = t0 + (t1 - t0) * 0.35;
    var halo = FX.shape(c, "glint_halo" + i);
    FX.group(halo, "ellipse", { size: [g[4] * 2.2, g[5] * 2.6], fill: FX.rgb(g[7]) });
    halo.position.setValue([g[0], Y(g[1])]);
    FX.blur(halo, 16);
    FX.keys(halo.opacity, [[t0, 0], [tm, 60], [t1, 0]], false);
    var cr = FX.shape(c, "glint_core" + i);
    FX.group(cr, "ellipse", { size: [g[4], g[5]], fill: FX.rgb(g[6]) });
    cr.position.setValue([g[0], Y(g[1])]);
    FX.blur(cr, 5);
    FX.keys(cr.scale, [[t0, [40, 60]], [tm, [100, 100]], [t1, [70, 50]]], false);
    FX.keys(cr.opacity, [[t0, 0], [tm, 100], [t1, 0]], false);
  }
  // star flare (4-point) on the purple glint at x 465
  var fl = FX.shape(c, "flare_star");
  var fg = FX.group(fl, "star", { points: 4, r1: 22, r2: 4, fill: [1, 1, 1] });
  FX.blur(fl, 1.5);
  fl.position.setValue([465, Y(1648)]);
  FX.keys(fl.scale, [[T(2.99), [20, 20]], [T(3.05), [100, 100]], [T(3.12), [70, 70]], [T(3.19), [110, 110]], [T(3.24), [10, 10]]], false);
  FX.keys(fl.opacity, [[T(2.98), 0], [T(3.03), 100], [T(3.21), 80], [T(3.24), 0]], false);
  FX.keys(fl.rotation, [[T(2.98), 0], [T(3.24), 30]], false);
  FX.glow(fl, 8, 1.5, 30, FX.rgb("FFFFFF"), FX.rgb("C060FF"));

  // 5. dot sparkles
  var DOTS = [[305, 1628, 3.07, 3.18], [360, 1641, 3.04, 3.12], [150, 1690, 2.97, 3.05], [540, 1700, 2.96, 3.04]];
  for (var k = 0; k < DOTS.length; k++) {
    var d = DOTS[k], dl = FX.shape(c, "dot" + k);
    FX.group(dl, "ellipse", { size: [6, 6], fill: [1, 1, 1] });
    dl.position.setValue([d[0], Y(d[1])]);
    FX.keys(dl.opacity, [[T(d[2]), 0], [T(d[2]) + 0.02, 100], [T(d[3]), 0]], false);
    FX.glow(dl, 6, 1.5, 20, FX.rgb("FFFFFF"), FX.rgb("FFE8B0"));
  }
  return FX.done(c);
}
