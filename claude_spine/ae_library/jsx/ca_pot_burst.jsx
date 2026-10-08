// ca_pot_burst (clip A, t 1.64..2.10): the white explosion when a candy pot bursts. Measured on the top-middle pot
// (clip px): translucent crack flash ~70 px at 1.64, 1.66 hot blob r~50, 1.68 cloud ~175x155 with spiky blue-white
// shard-light around it, 1.70-1.78 ~220x190 white-hot, 1.80-1.84 turning warm yellow/orange and thinning,
// then gone (the board-wide rainbow burst takes over at 1.85). Comp centre = clip (320, 532). S = 1.5 comp px / clip px.
function BUILD(V) {
  var S = 1.5, W = 360 * S, H = 330 * S, cx = W / 2, cy = H / 2;
  var name = "ca_pot_burst_v" + V;
  var D = 0.5, fps = 30;
  var c = FX.comp(name, W, H, fps, D);
  var WHITE = FX.rgb("FFFEF8"), WARM = FX.rgb("FFF0B8"), GOLD = FX.rgb("FFD27A"), ORA = FX.rgb("F7A85A");
  var ICE = FX.rgb("D6E4FF"), ICE2 = FX.rgb("AFC4EE");
  var rnd = FX.rng(7);
  function P(x, y) { return [cx + x * S, cy + y * S]; }

  // 1. rim: pale blue-white soft lobed cloud slightly larger than the body, behind it
  var rim = FX.shape(c, "rim");
  var rs = FX.group(rim, "star", { points: 11, r1: 104 * S, r2: 80 * S, fill: ICE });
  rs.star.property("ADBE Vector Star Outer Roundess").setValue(70);
  rs.star.property("ADBE Vector Star Inner Roundess").setValue(30);
  rim.position.setValue(P(0, 4));
  FX.keys(rim.scale, [[0.017, [40, 35]], [0.033, [90, 80]], [0.05, [100, 87]], [0.07, [104, 90]], [0.14, [110, 96]], [0.26, [116, 100]]], "out");
  FX.keys(rim.opacity, [[0.015, 0], [0.04, 55], [0.12, 50], [0.2, 25], [0.28, 0]], false);
  FX.keys(rim.rotation, [[0, -8], [D, 10]], false);
  var td0 = FX.fx(rim, "ADBE Turbulent Displace"); FX.set(td0, "Amount", 40); FX.set(td0, "Size", 26 * S);
  FX.keys(FX.find(td0, "Evolution"), [[0, 0], [D, 220]], false);
  FX.blur(rim, 7 * S);

  // 2. shard light: thin translucent white/blue spikes radiating from the cloud (crystal-like streaks)
  for (var i = 0; i < 30; i++) {
    var a = i * 12 + (rnd() - 0.5) * 10, ar = a * Math.PI / 180;
    var low = (a % 360) > 80 && (a % 360) < 220;
    var len = (28 + rnd() * 45) * (low ? 1.4 : 1), wid = (8 + rnd() * 12) * (low ? 1.3 : 1), r0 = 60 + rnd() * 25;
    var sp = FX.shape(c, "shard" + i);
    FX.group(sp, "path", { points: [[0, -wid / 2 * S], [len * S, 0], [0, wid / 2 * S], [-6 * S, 0]], closed: true, fill: (i % 3 === 0 ? WHITE : (i % 3 === 1 ? ICE : (low ? FX.rgb("95A6CC") : ICE2))) });
    sp.rotation.setValue(a);
    var t0 = 0.035 + rnd() * 0.04, t1 = t0 + 0.10 + rnd() * 0.08;
    FX.keys(sp.position, [[t0, P(Math.cos(ar) * r0 * 0.7, 4 + Math.sin(ar) * r0 * 0.62)], [t1, P(Math.cos(ar) * (r0 + 22), 4 + Math.sin(ar) * (r0 + 22) * 0.88)]], "out");
    FX.keys(sp.scale, [[t0, [40, 100]], [t0 + 0.04, [100, 100]], [t1, [70, 50]]], false);
    FX.keys(sp.opacity, [[t0 - 0.01, 0], [t0, 75], [t0 + 0.06, 55], [t1, 0]], false);
    FX.blur(sp, 2 * S);
  }

  // 3. body: white-hot billowing cloud, turning warm and thinning out
  var body = FX.shape(c, "body");
  var bs = FX.group(body, "star", { points: 9, r1: 96 * S, r2: 74 * S, fill: FX.rgb("FFFCEE") });
  bs.star.property("ADBE Vector Star Outer Roundess").setValue(80);
  bs.star.property("ADBE Vector Star Inner Roundess").setValue(25);
  body.position.setValue(P(0, 4));
  FX.keys(body.scale, [[0.005, [12, 10]], [0.017, [40, 35]], [0.033, [86, 76]], [0.05, [96, 85]], [0.07, [100, 88]], [0.14, [106, 92]], [0.24, [112, 96]], [0.34, [116, 100]]], "out");
  FX.keys(bs.fillC, [[0.10, FX.rgb("FFFCEE")], [0.16, WARM], [0.24, FX.rgb("FFE8B8")]], false);
  FX.keys(body.opacity, [[0.004, 0], [0.006, 78], [0.13, 78], [0.18, 58], [0.24, 22], [0.29, 4], [0.31, 0]], false);
  FX.keys(body.rotation, [[0, 12], [D, -6]], false);
  var td = FX.fx(body, "ADBE Turbulent Displace"); FX.set(td, "Amount", 90); FX.set(td, "Size", 13 * S); FX.set(td, "Complexity", 3);
  FX.keys(FX.find(td, "Evolution"), [[0, 30], [D, 260]], false);
  FX.blur(body, 6 * S);

  // 4. hot core (brighter, warm late), and the first translucent crack flash
  var core = FX.shape(c, "core");
  var cg = FX.group(core, "ellipse", { size: [150 * S, 125 * S], fill: [1, 1, 1] });
  core.position.setValue(P(0, 6));
  FX.keys(core.scale, [[0.017, [50, 50]], [0.04, [100, 100]], [0.2, [110, 110]]], "out");
  FX.keys(cg.fillC, [[0.04, [1, 1, 1]], [0.07, FX.rgb("FFE58A")], [0.18, FX.rgb("FFF2C0")], [0.26, FX.rgb("FFF4D8")]], false);
  FX.keys(core.opacity, [[0.01, 0], [0.03, 100], [0.16, 100], [0.21, 40], [0.25, 0]], false);
  FX.blur(core, 18 * S);
  var crack = FX.shape(c, "crack_flash");
  FX.group(crack, "ellipse", { size: [60 * S, 70 * S], fill: [1, 1, 1] });
  crack.position.setValue(P(4, 6));
  FX.keys(crack.scale, [[0, [100, 100]], [0.03, [160, 150]], [0.05, [200, 180]]], "out");
  FX.keys(crack.opacity, [[0, 70], [0.025, 80], [0.05, 0]], false);
  FX.blur(crack, 10 * S);

  // 5. small white sparkles flying out
  for (var k = 0; k < 16; k++) {
    var ak = rnd() * 360, akr = ak * Math.PI / 180, r1 = 90 + rnd() * 70, tk = 0.04 + rnd() * 0.05, te = tk + 0.16 + rnd() * 0.14;
    var s = FX.shape(c, "spark" + k);
    var sz = (2.5 + rnd() * 3) * S;
    FX.group(s, "ellipse", { size: [sz, sz], fill: (k % 4 ? [1, 1, 1] : FX.rgb("FFF2B0")) });
    FX.keys(s.position, [[tk, P(Math.cos(akr) * 40, 4 + Math.sin(akr) * 34)], [te, P(Math.cos(akr) * r1, 4 + Math.sin(akr) * r1 * 0.85 + 10)]], "out");
    FX.keys(s.opacity, [[tk - 0.01, 0], [tk, 100], [te - 0.06, 90], [te, 0]], false);
    FX.glow(s, 4 * S, 1.2, 30, [1, 1, 1], FX.rgb("FFE9A0"));
  }

  // 6. bloom on the whole thing
  var g = FX.adj(c, "bloom");
  var gl = FX.glow(g, 16 * S, 0.6, 60, FX.rgb("FFFFFF"), FX.rgb("FFE2A0"));
  rim.moveToEnd();
  return FX.done(c);
}
