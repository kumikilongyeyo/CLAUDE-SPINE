// ca_rainbow_burst (clip A, t 1.84..2.59): the full-board radial burst behind the X5 multiplier. The burst is
// CENTRED ON THE X5 and travels down with it (clip y 540 at 1.84 -> 1210 at 2.45, x ~320). White/yellow core with a
// cyan ring, streaky radial rays in white, yellow, orange, pink, magenta and purple that fill the whole board by
// ~1.95, turn translucent by 2.2, shrink to r ~200 around the X5 by 2.39 and are gone by ~2.50. Additive.
// Comp = clip box (0,380)-(684,1480), S = 1. Comp t=0 = clip 1.84.
function BUILD(V) {
  var W = 684, H = 1100, OX = 0, OY = 380;
  var name = "ca_rainbow_burst_v" + V;
  var D = 0.75, fps = 30;
  var c = FX.comp(name, W, H, fps, D);
  var rnd = FX.rng(31);
  function T(clipT) { return clipT - 1.84; }

  // the X5 path (clip px, measured) -> comp px
  var path = [[1.84, 540], [1.90, 620], [1.96, 662], [2.02, 750], [2.08, 840], [2.15, 905], [2.21, 950], [2.27, 1050],
              [2.33, 1110], [2.39, 1165], [2.45, 1225], [2.51, 1320], [2.57, 1390]];
  var ctr = c.layers.addNull(D); ctr.name = "centre";
  var pk = []; for (var i = 0; i < path.length; i++) pk.push([T(path[i][0]), [320 - OX, path[i][1] - OY]]);
  FX.keys(ctr.position, pk, false);
  var FOLLOW = 'var p = thisComp.layer("centre").transform.position; p';

  // rays: polar-mapped stretched fractal noise (vertical streaks -> radial rays), luma-matted by a radial ramp
  function rays(nm, color, o) {
    var SZ = 1600;
    var n = FX.solid(c, nm, [0, 0, 0], SZ, SZ);
    var fn = FX.fx(n, "ADBE Fractal Noise");
    FX.set(fn, "Fractal Type", 1); FX.set(fn, "Noise Type", 3);
    FX.set(fn, "Contrast", o.contrast || 260); FX.set(fn, "Brightness", o.bright || -40);
    FX.set(fn, "Uniform Scaling", 0); FX.set(fn, "Scale Width", o.sw); FX.set(fn, "Scale Height", o.sh || 6000);
    FX.set(fn, "Complexity", o.cx || 1.5); FX.set(fn, "Random Seed", o.seed);
    FX.keys(FX.find(fn, "Evolution"), [[0, 0], [D, o.evo || 90]], false);
    var pc = FX.fx(n, "ADBE Polar Coordinates");
    FX.set(pc, "Interpolation", 1); FX.set(pc, "Type of Conversion", 1);   // rect -> polar
    FX.keys(n.rotation, [[0, o.rot0 || 0], [D, (o.rot0 || 0) + (o.spin || 6)]], false);
    var sc = FX.fx(n, "ADBE Shift Channels"); FX.set(sc, "Take Alpha From", 5);
    var fl = FX.fx(n, "ADBE Fill"); FX.set(fl, "Color", color);
    n.position.expression = FOLLOW;
    // matte: radial ramp, white centre -> black at radius r (keyed), soft
    var m = FX.solid(c, nm + "_matte", [0, 0, 0], SZ, SZ);
    var r = FX.fx(m, "ADBE Ramp");
    r.property("ADBE Ramp-0001").setValue([SZ / 2, SZ / 2]);
    r.property("ADBE Ramp-0002").setValue([1, 1, 1, 1]);
    r.property("ADBE Ramp-0004").setValue([0, 0, 0, 1]);
    r.property("ADBE Ramp-0005").setValue(2);
    var ek = []; for (var k = 0; k < o.radius.length; k++) ek.push([o.radius[k][0], [SZ / 2 + Math.max(1, o.radius[k][1]), SZ / 2]]);
    FX.keys(r.property("ADBE Ramp-0003"), ek, false);
    m.position.expression = FOLLOW;
    n.setTrackMatte(m, TrackMatteType.LUMA);
    FX.keys(n.opacity, o.opacity, false);
    return n;
  }

  // 1. warm haze washing the board (normal, low alpha; reads as additive warm light)
  var haze = FX.shape(c, "haze");
  var hg = FX.group(haze, "ellipse", { size: [900, 900], fill: FX.rgb("FFB487") });
  haze.position.expression = FOLLOW;
  FX.blur(haze, 160);
  FX.keys(haze.scale, [[0, [30, 30]], [0.08, [110, 110]], [0.3, [150, 150]], [0.47, [70, 70]], [0.62, [40, 40]]], "out");
  FX.keys(hg.fillC, [[0.25, FX.rgb("FFB487")], [0.45, FX.rgb("C46AD8")]], false);
  FX.keys(haze.opacity, [[0, 0], [0.04, 0], [0.09, 35], [0.3, 32], [0.42, 22], [0.55, 15], [0.66, 0]], false);

  // 2. ray layers, outermost first (purple/magenta long, pink, orange, yellow, white short)
  var R_BIG = [[0, 50], [0.035, 150], [0.07, 380], [0.11, 820], [0.3, 900], [0.4, 660], [0.47, 420], [0.55, 340], [0.62, 250], [0.7, 160]];
  function scaleR(f) { var o = []; for (var i = 0; i < R_BIG.length; i++) o.push([R_BIG[i][0], R_BIG[i][1] * f]); return o; }
  function OPk(p) { return [[0, 0], [0.02, p], [0.3, p], [0.4, p * 0.8], [0.55, p * 0.7], [0.64, p * 0.3], [0.7, 0]]; }
  rays("rays_purple", FX.rgb("7A1CD0"), { sw: 70, seed: 3, radius: scaleR(1.25), opacity: OPk(55), contrast: 300, bright: -30, rot0: 4 });
  rays("rays_magenta", FX.rgb("E81CA8"), { sw: 55, seed: 7, radius: scaleR(1.12), opacity: OPk(85), contrast: 320, bright: -48, rot0: -3 });
  rays("rays_pink", FX.rgb("FF4CB4"), { sw: 40, seed: 11, radius: scaleR(1.0), opacity: OPk(75), contrast: 320, bright: -50 });
  rays("rays_orange", FX.rgb("FF8C1E"), { sw: 60, seed: 17, radius: scaleR(1.1), opacity: OPk(92), contrast: 280, bright: -12, rot0: 9 });
  rays("rays_yellow", FX.rgb("FFD436"), { sw: 46, seed: 23, radius: scaleR(1.0), opacity: OPk(92), contrast: 280, bright: -10, rot0: -7 });
  // streaky texture: short broken streaks (noise varies along the radius), warm white, inner region
  rays("streaks_warm", FX.rgb("FFF0B0"), { sw: 9, sh: 260, seed: 41, radius: scaleR(0.7), opacity: OPk(70), contrast: 300, bright: -30, cx: 3, evo: 300, rot0: 1 });
  rays("rays_white", FX.rgb("FFFBEA"), { sw: 40, seed: 29, radius: scaleR(0.45), opacity: OPk(60), contrast: 340, bright: -50, rot0: 2 });

  // 3. cyan ring hugging the core (the prismatic edge around the X5)
  var ring = FX.shape(c, "cyan_ring");
  var rg = FX.group(ring, "ellipse", { size: [150, 130], fill: FX.rgb("20D4F0") });
  ring.position.expression = FOLLOW;
  FX.blur(ring, 30);
  FX.keys(rg.size, [[0.04, [90, 80]], [0.12, [170, 150]], [0.3, [190, 165]], [0.5, [170, 150]], [0.62, [140, 120]]], "out");
  FX.keys(ring.opacity, [[0.03, 0], [0.08, 85], [0.4, 80], [0.55, 55], [0.64, 0]], false);

  // 4. hot core: white centre over a wide yellow glow
  var cy1 = FX.shape(c, "core_glow");
  var cgl = FX.group(cy1, "ellipse", { size: [320, 290], fill: FX.rgb("FFE27A") });
  cy1.position.expression = FOLLOW;
  FX.blur(cy1, 90);
  FX.keys(cy1.scale, [[0, [30, 30]], [0.06, [100, 100]], [0.3, [120, 120]], [0.47, [70, 70]], [0.62, [45, 45]]], "out");
  FX.keys(cy1.opacity, [[0, 0], [0.035, 15], [0.08, 60], [0.32, 55], [0.45, 35], [0.6, 18], [0.68, 0]], false);
  var core = FX.shape(c, "core");
  FX.group(core, "ellipse", { size: [90, 80], fill: FX.rgb("FFFFF6") });
  core.position.expression = FOLLOW;
  FX.blur(core, 24);
  FX.keys(core.scale, [[0, [40, 40]], [0.05, [110, 110]], [0.3, [100, 100]], [0.5, [70, 70]], [0.62, [50, 50]]], "out");
  FX.keys(core.opacity, [[0, 0], [0.02, 100], [0.35, 95], [0.5, 60], [0.66, 0]], false);

  // 5. light ribbons: long thin bright streaks shooting out from the core
  for (var s = 0; s < 7; s++) {
    var a = s * (360 / 7) + (rnd() - 0.5) * 18, t0 = 0.03 + rnd() * 0.12;
    var col = [FX.rgb("FFFFFF"), FX.rgb("FFF2A0"), FX.rgb("FFB0E8")][s % 3];
    var st = FX.streak(c, "ribbon" + s, 320 - OX, 700 - OY, a, 60, 380 + rnd() * 220, t0, t0 + 0.28 + rnd() * 0.12, 140 + rnd() * 120, 8 + rnd() * 6, col);
    st.opacity.expression = 'value * 0.55';
    st.position.expression = 'var p = thisComp.layer("centre").transform.position; p + value - [' + (320 - OX) + ',' + (700 - OY) + ']';
  }

  // 6. flakes: a few yellow / white confetti flakes tumbling out
  for (var q = 0; q < 12; q++) {
    var aq = rnd() * 360, ar = aq * Math.PI / 180, r0 = 40 + rnd() * 40, r1 = 260 + rnd() * 240, tq = 0.06 + rnd() * 0.12, te = tq + 0.3 + rnd() * 0.2;
    var fk = FX.shape(c, "flake" + q);
    FX.group(fk, "rect", { size: [10 + rnd() * 8, 6 + rnd() * 4], fill: (q % 3 ? FX.rgb("FFE070") : FX.rgb("FFFFFF")) });
    FX.keys(fk.position, [[tq, [Math.cos(ar) * r0, Math.sin(ar) * r0]], [te, [Math.cos(ar) * r1, Math.sin(ar) * r1 + 60]]], "out");
    fk.position.expression = 'var p = thisComp.layer("centre").transform.position; p + value';
    FX.keys(fk.rotation, [[tq, rnd() * 360], [te, rnd() * 720 - 360]], false);
    FX.keys(fk.scale, [[tq, [100, 100]], [te, [100, 30]]], false);
    FX.keys(fk.opacity, [[tq - 0.01, 0], [tq, 100], [te - 0.08, 90], [te, 0]], false);
  }

  // 7. bloom
  var g = FX.adj(c, "bloom");
  FX.glow(g, 24, 0.2, 75, FX.rgb("FFF4D0"), FX.rgb("FF60C0"));
  ctr.moveToBeginning();
  return FX.done(c);
}
