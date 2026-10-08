// re_reel_fire: realistic version of cb_reel_fire_v9 (clip B reel-4 anticipation column). Same frame (600x1320,
// centre clip px 1079,760, edge lines at local x 141 / 459), same 1.0 s seamless loop and the same breathing
// (bright 0.1-0.45 s, dim 0.6-1.0 s). Real fire: a vertically TILING strip of Kenney flame tongues + fire_01 photo
// flames (every sprite has a twin one strip-height away, so the strip wraps exactly), streamed UP 2 strips per loop
// with the Offset effect, gas-displaced (Turbulent Displace, cycled evolution), vertically motion-blurred and
// heat-mapped (CC Toner: white-hot > yellow > orange > deep red, alpha from heat). Heat haze over the fire, rising
// embers, the edge lines as neon/plasma tubes (white core, magenta tube, filaments streaming inside, 3-stage bloom),
// motion-blurred spark streaks shooting up and out.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var W = 600, H = 1320, D = 1.0, FPS = 30, XL = 141, XR = 459, SW = 330;
  var tag = "re_cb_reel_fire_v" + V;
  var rnd = FX.rng(41);
  function comp(n, w, h) { var c = FX.comp(n, w, h, FPS, D, RE.FOLDER); c.motionBlur = true; c.shutterAngle = 180; c.shutterPhase = -90; return c; }
  function per(f, ph) { return "Math.sin(2 * Math.PI * (" + f + " * time / " + D + ") + " + ph + ")"; }   // integer cycles per loop

  // ---- 1. tiling flame strip (330 x 1320; x = across the column, wraps vertically)
  var strip = comp(tag + "_strip", SW, H);
  FX.solid(strip, "black", [0, 0, 0]);
  function place(path, nm, x, y, sx, sy, rot, op, fl) {
    for (var tw = -1; tw <= 1; tw++) {
      var yy = y + tw * H;
      if (yy < -450 || yy > H + 450) continue;
      var l = strip.layers.add(FX.imp(path)); l.name = nm + "_" + (tw + 1);
      l.position.setValue([x, yy]); l.scale.setValue([sx, sy]); l.rotation.setValue(rot);
      l.blendingMode = BlendingMode.ADD;
      l.opacity.expression = op + " * (0.72 + 0.28 * " + per(fl[0], fl[1]) + ")";
      l.scale.expression = "[" + sx + ", " + sy + " * (1 + 0.12 * " + per(fl[2], fl[1] + 1.3) + ")]";
    }
  }
  var FL = ["flame_05.png", "flame_06.png"];
  for (var i = 0; i < 44; i++) {
    var fx = 18 + rnd() * (SW - 36), fy = rnd() * H, s = 45 + rnd() * 45;
    place(RE.K + FL[i % 2], "tongue" + i, fx, fy, s * (rnd() < 0.5 ? -1 : 1), s * (2.2 + rnd() * 1.6),
          (rnd() - 0.5) * 8, 20 + rnd() * 20, [2 + Math.floor(rnd() * 4), rnd() * 6.28, 1 + Math.floor(rnd() * 3)]);
  }
  for (var p = 0; p < 7; p++) {            // real flame photo: billowing detail
    var py = (p + rnd() * 0.5) * H / 7, px = 60 + rnd() * (SW - 120);
    for (var tw2 = -1; tw2 <= 1; tw2++) {
      var ph = strip.layers.add(FX.imp(RE.R + "fire_01.png")); ph.name = "photo" + p + "_" + (tw2 + 1);
      RE.ellMask(ph, 160, 40);
      ph.position.setValue([px, py + tw2 * H]); ph.scale.setValue([42, 90]); ph.rotation.setValue(p % 2 ? 0 : 180);
      ph.blendingMode = BlendingMode.ADD;
      ph.opacity.expression = "38 * (0.75 + 0.25 * " + per(3 + p % 3, p) + ")";
    }
  }

  // ---- 2. flowing fire (strip streamed up, gas displaced, motion blurred, heat-mapped)
  var flow = comp(tag + "_flow", SW, H);
  var fl = flow.layers.add(strip); fl.name = "strip";
  var of = FX.fx(fl, "ADBE Offset");
  of.property("ADBE Offset-0001").expression = "var y = (" + (H / 2) + " - time / " + D + " * " + (2 * H) + ") % " + H + "; if (y < 0) y += " + H + "; [" + (SW / 2) + ", y]";
  var td = FX.fx(fl, "ADBE Turbulent Displace"); FX.set(td, "Amount", 38); FX.set(td, "Size", 46); FX.set(td, "Complexity", 3);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [D, 360]], false); FX.set(td, "Cycle Evolution", 1); FX.set(td, "Cycle (in Revolutions)", 1);
  var td2 = FX.fx(fl, "ADBE Turbulent Displace"); FX.set(td2, "Amount", 14); FX.set(td2, "Size", 14); FX.set(td2, "Complexity", 2);
  FX.keys(FX.find(td2, "Evolution"), [[0, 0], [D, 720]], false); FX.set(td2, "Cycle Evolution", 1); FX.set(td2, "Cycle (in Revolutions)", 2);
  var mb = FX.fx(fl, "ADBE Motion Blur"); FX.set(mb, "Direction", 0); FX.set(mb, "Blur Length", 55);

  var c = comp(tag, W, H);
  var WH = FX.rgb("FFFBEA"), YEL = FX.rgb("FFD23C"), ORA = FX.rgb("FF7414"), RED = FX.rgb("B41616"), MAG = FX.rgb("FF2EA8"), PNK = FX.rgb("FF78C8");
  function toner(l, a, b, cc, d, e) { var t = FX.fx(l, "CC Toner"); FX.set(t, "Tones", 3);
    FX.set(t, "Highlights", a); FX.set(t, "Brights", b); FX.set(t, "Midtones", cc); FX.set(t, "Darktones", d); FX.set(t, "Shadows", e); return t; }
  function colMask(l, inset, feather, ox) {        // ox: layer-space offset (masks live in LAYER coordinates)
    ox = ox || 0;
    var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom"), s = new Shape();
    s.vertices = [[XL + inset - ox, -60], [XR - inset - ox, -60], [XR - inset - ox, H + 60], [XL + inset - ox, H + 60]]; s.closed = true;
    m.property("ADBE Mask Shape").setValue(s); m.property("ADBE Mask Feather").setValue([feather, 0]);
  }
  var BREATH = [[0, 75], [0.17, 100], [0.42, 92], [0.58, 35], [0.7, 18], [0.88, 18], [1.0, 75]];

  // tube bloom spilling outside (behind everything): wide red-magenta
  function vline(nm, x, w, col, blur, op) {
    var l = FX.shape(c, nm);
    FX.group(l, "path", { points: [[x, -60], [x, H + 60]], stroke: col, width: w, cap: 1 });
    l.anchorPoint.setValue([0, 0]); l.position.setValue([0, 0]);
    if (blur) FX.blur(l, blur);
    l.opacity.setValue(op === undefined ? 100 : op);
    l.blendingMode = BlendingMode.ADD;
    return l;
  }
  vline("bloom_wideL", XL, 80, FX.rgb("F0602E"), 45, 50); vline("bloom_wideR", XR, 80, FX.rgb("F0602E"), 45, 50);

  // fire body: heat-mapped, alpha = heat
  var body = c.layers.add(flow); body.name = "fire_body"; body.position.setValue([W / 2, H / 2]);
  var lv = FX.fx(body, "ADBE Pro Levels2"); lv.property("ADBE Pro Levels2-0004").setValue(0.05); lv.property("ADBE Pro Levels2-0005").setValue(1.0);
  toner(body, FX.rgb("FFF2A8"), FX.rgb("FFC52E"), FX.rgb("FF6E12"), FX.rgb("A81414"), [0, 0, 0]);
  RE.lumAlpha(body);
  colMask(body, 2, 14, (W - SW) / 2);
  FX.keys(body.opacity, BREATH, "both");
  // glowing gas filling the gaps between tongues during the surge (no sooty black holes)
  var gasb = FX.solid(c, "gas_glow", FX.rgb("FFA02C"));
  colMask(gasb, 4, 22);
  gasb.opacity.expression = "Math.max(0, thisComp.layer(\"fire_body\").transform.opacity - 30) * 0.65";
  gasb.moveAfter(body);
  // white-hot core: the hottest part of the same flow, added, plus a hot band hugging each tube
  var hot = c.layers.add(flow); hot.name = "white_hot"; hot.position.setValue([W / 2, H / 2]);
  var lh = FX.fx(hot, "ADBE Pro Levels2"); lh.property("ADBE Pro Levels2-0004").setValue(0.7); lh.property("ADBE Pro Levels2-0005").setValue(1.0);
  RE.tint(hot, FX.rgb("FFF4C8"));
  FX.blur(hot, 3);
  hot.blendingMode = BlendingMode.ADD; colMask(hot, 6, 18, (W - SW) / 2);
  hot.opacity.expression = "Math.max(0, thisComp.layer(\"fire_body\").transform.opacity - 40) * 0.7";
  var bandL = vline("hot_bandL", XL + 26, 40, FX.rgb("FFC840"), 16, 60), bandR = vline("hot_bandR", XR - 26, 40, FX.rgb("FFC840"), 16, 60);
  bandL.blendingMode = bandR.blendingMode = BlendingMode.SCREEN;
  bandL.opacity.expression = bandR.opacity.expression = "Math.max(0, (thisComp.layer(\"fire_body\").transform.opacity - 30) * 1.1)";
  // dim phase: the column smoulders dark magenta between surges
  var tint = FX.solid(c, "dim_tint", FX.rgb("8E2050")); tint.blendingMode = BlendingMode.NORMAL;
  colMask(tint, 2, 16);
  tint.opacity.expression = "Math.max(0, 70 - thisComp.layer(\"fire_body\").transform.opacity) * 0.4";

  // rising embers (periodic life, wrap twins)
  for (var e = 0; e < 34; e++) {
    var ex = XL + 14 + rnd() * (XR - XL - 28), ey0 = H + 20 - rnd() * 200, rise = 700 + rnd() * 700, ep = rnd(), esz = 2.5 + rnd() * 3.5;
    var em = FX.shape(c, "ember" + e);
    FX.group(em, "ellipse", { size: [esz, esz], fill: rnd() < 0.4 ? FX.rgb("FFE08A") : FX.rgb("FF9A30") });
    em.anchorPoint.setValue([0, 0]);
    em.position.expression = "var a = (time / " + D + " + " + ep + ") % 1; [" + ex + " + 10 * Math.sin(a * 9 + " + e + "), " + ey0 + " - " + rise + " * a - " + (rnd() * 600) + "]";
    em.opacity.expression = "var a = (time / " + D + " + " + ep + ") % 1; 100 * Math.sin(Math.PI * a)";
    em.motionBlur = true; em.blendingMode = BlendingMode.ADD;
  }

  // heat haze over the fire and the air around it
  var haze = FX.adj(c, "heat_haze");
  var hz = FX.fx(haze, "ADBE Turbulent Displace"); FX.set(hz, "Amount", 9); FX.set(hz, "Size", 28); FX.set(hz, "Complexity", 2);
  FX.keys(FX.find(hz, "Evolution"), [[0, 0], [D, 720]], false); FX.set(hz, "Cycle Evolution", 1); FX.set(hz, "Cycle (in Revolutions)", 2);

  // ---- 3. neon / plasma tubes
  var fil = comp(tag + "_filament", W, H);
  var fn = FX.noise(fil, "filaments", { type: 1, noise: 2, contrast: 300, brightness: -80, sw: 3, sh: 400, complexity: 3, seed: 3, evo: [[0, 0], [D, 1080]], cycle: 3 });
  var fof = FX.fx(fn.layer, "ADBE Offset");                       // filaments race upward one comp height per loop (Offset wraps -> exact loop)
  fof.property("ADBE Offset-0001").expression = "[" + (W / 2) + ", " + (H / 2) + " - time * " + H + "]";
  for (var t = 0; t < 2; t++) {
    var X = t ? XR : XL;
    vline("bloom_mid" + t, X, 30, MAG, 14, 75);
    var tube = vline("tube" + t, X, 11, MAG, 1.5, 100);
    var fm = c.layers.add(fil); fm.name = "filament" + t;
    var mk = fm.property("ADBE Mask Parade").addProperty("ADBE Mask Atom"), ms = new Shape();
    ms.vertices = [[X - 5, -60], [X + 5, -60], [X + 5, H + 60], [X - 5, H + 60]]; ms.closed = true;
    mk.property("ADBE Mask Shape").setValue(ms); mk.property("ADBE Mask Feather").setValue([3, 0]);
    RE.tint(fm, PNK); fm.blendingMode = BlendingMode.ADD; fm.opacity.setValue(90);
    var core = vline("core" + t, X, 4, WH, 0.8, 100);
    core.opacity.expression = "88 + 12 * " + per(9 + t, t * 2);
    tube.opacity.expression = "90 + 10 * " + per(5 + t, t);
  }

  // ---- 4. spark streaks shooting up and out (Kenney trace sprite, motion blurred, periodic births)
  var N = 26;
  for (var k = 0; k < N; k++) {
    var side = k % 2 ? 1 : -1, x0 = (side < 0 ? XL : XR) + side * (rnd() * 40 - 25), y0 = 140 + rnd() * (H - 280);
    var ang = -90 + side * (25 + rnd() * 30), dist = 140 + rnd() * 160, life = 0.14 + rnd() * 0.1, tb = (k + rnd() * 0.6) * D / N;
    var ar = ang * Math.PI / 180, sc = 18 + rnd() * 16;
    for (var w = 0; w < 2; w++) {
      var t0 = tb - w * D; if (t0 + life < 0) continue;
      var sp = c.layers.add(FX.imp(RE.K + "trace_01.png")); sp.name = "spark" + k + "_" + w;
      RE.fill(sp, FX.rgb("FFF2D8"));
      sp.rotation.setValue(ang + 90); sp.scale.setValue([sc, sc * 1.6]);
      FX.keys(sp.position, [[t0, [x0, y0]], [t0 + life, [x0 + Math.cos(ar) * dist, y0 + Math.sin(ar) * dist]]], "out");
      FX.keys(sp.opacity, [[t0 - 0.001, 0], [t0, 100], [t0 + life * 0.6, 90], [t0 + life, 0]], false);
      sp.blendingMode = BlendingMode.ADD; sp.motionBlur = true;
    }
  }
  var bl = FX.adj(c, "bloom"); FX.glow(bl, 10, 0.45, 78, FX.rgb("FFC060"), FX.rgb("FF7A20"));
  return FX.done(c);
}
