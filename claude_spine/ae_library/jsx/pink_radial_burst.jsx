// pink_radial_burst (085853, 500x500): pink/magenta light rays around a dark centre hole (r ~ 40 GIF px), mirrored
// left/right, in two tiers: tier A rays start as thin tips at r ~ 52 and swell into bold teardrop heads around
// r ~ 90-120 before fading by r ~ 160; tier B starts abruptly at r ~ 165 and fades out into the corners. Rounded dark
// wedges/arches eat into tier A at 12, 6, 3 and 9 o'clock (+ smaller ones on the diagonals). Brightness varies a lot
// from ray to ray. SEAMLESS 1.92 s loop (every motion is a sine of time with period L).
// v13 rebuild (procedural, no noise): RECT space (x = angle, x = 0 at 12 o'clock going clockwise; y = radius,
// y = 4.8 * r_gif) holds explicit spindle-shaped rays (seeded random) + rounded dark arches; a radial profile texture
// (ae/tex/pr_profile2.png, hand-set control points) shapes the tiers; the left half is mirrored; Rect->Polar on an
// 1800 px layer (radius 375 GIF px, so the burst fades into the corners instead of stopping at a circle), zoom
// Radial Blur, CC Toner pentone (black shadows, for additive use), Glow.
function BUILD(V) {
  var S = 2.4, W = 1200, H = 1200, fps = 25, L = 1.92, tag = "pr_pink_burst_v" + V;
  var RW = 1800, RH = 1800, YR = 4.8;                 // rect comp; y = YR * r_gif
  var TEX = FXLIB_TEX;
  var rnd = FX.rng(1013);
  function xOf(deg) { return ((deg - 270 + 720) % 360) / 360 * RW; }   // deg: 0 = 3 o'clock, clockwise
  var TWO = "2 * Math.PI * time / " + L;

  var R = FX.comp(tag + "_rect", RW, RH, fps, L, "fxlib_density");
  FX.solid(R, "black", [0, 0, 0]);
  // ---- rays: spindle polygons, thin tip at the inner end, fat body, soft outer end
  function spindle(layer, x, yT, yE, w, peak, g) {
    var n = 14, Lp = [], Rp = [];
    for (var i = 0; i <= n; i++) {
      var s = i / n, y = yT + (yE - yT) * s, e;
      if (s < peak) e = Math.pow(Math.sin(Math.PI / 2 * s / peak), 0.75);
      else e = 1 - 0.65 * Math.pow((s - peak) / (1 - peak), 1.2);
      Lp.push([x - w / 2 * e, y]); Rp.push([x + w / 2 * e, y]);
    }
    var pts = Lp; for (var k = Rp.length - 1; k >= 0; k--) pts.push(Rp[k]);
    return FX.group(layer, "path", { points: pts, closed: true, fill: [g, g, g] });
  }
  function rayLayer(name, count, tier) {
    var l = FX.shape(R, name); l.position.setValue([0, 0]);
    for (var i = 0; i < count; i++) {
      var bold = rnd() < BOLD;
      var x = rnd() * RW / 2;
      var w = tier === "A" ? (bold ? 40 + rnd() * 34 : 16 + rnd() * 20) : (bold ? 26 + rnd() * 26 : 12 + rnd() * 14);
      var g = bold ? 0.68 + rnd() * 0.27 : 0.25 + rnd() * 0.35;
      var yT, yE, pk;
      if (tier === "A") { yT = (50 + rnd() * 14) * YR; yE = (150 + rnd() * 25) * YR; pk = 0.35 + rnd() * 0.2; }
      else { yT = (163 + rnd() * 8) * YR; yE = (240 + rnd() * 60) * YR; pk = 0.08 + rnd() * 0.1; }
      var gr = spindle(l, x, yT, yE, w, pk, g);
      var ph = (rnd() * 2 * Math.PI).toFixed(3), ph2 = (rnd() * 2 * Math.PI).toFixed(3);
      var amp = (tier === "A" ? 40 : 60) * (0.5 + rnd()), fq = rnd() < 0.5 ? 1 : 2, fq2 = rnd() < 0.5 ? 1 : 2;
      var dx = 8 * (rnd() - 0.5);
      gr.xf.property("ADBE Vector Position").expression = "[" + dx.toFixed(1) + " * Math.sin(" + TWO + " + " + ph2 + "), " + amp.toFixed(1) + " * Math.sin(" + fq + " * " + TWO + " + " + ph + ")]";
      gr.xf.property("ADBE Vector Group Opacity").expression = "100 * (" + (1 - FLICK) + " + " + FLICK + " * (0.5 + 0.5 * Math.sin(" + fq2 + " * " + TWO + " + " + ph2 + ")))";
    }
    FX.blur(l, 5, 2);                                                          // 2 = horizontal: soft sides
    FX.blur(l, 26, 3);                                                         // 3 = vertical: soft ends
    l.blendingMode = BlendingMode.SCREEN;
    return l;
  }
  var BOLD = 0.4, FLICK = 0.7;
  rayLayer("rays_A", 30, "A");
  rayLayer("rays_B", 26, "B");
  // thin hot needles (bright cores) in both tiers
  var nd = FX.shape(R, "needles"); nd.position.setValue([0, 0]);
  for (var q = 0; q < 26; q++) {
    var tierA = q < 14, nx = rnd() * RW / 2;
    var ny0 = (tierA ? 52 + rnd() * 20 : 164 + rnd() * 6) * YR, ny1 = (tierA ? 120 + rnd() * 40 : 215 + rnd() * 40) * YR;
    var gn = spindle(nd, nx, ny0, ny1, 6 + rnd() * 6, 0.3, 0.8 + rnd() * 0.2);
    gn.xf.property("ADBE Vector Group Opacity").expression = "100 * (0.4 + 0.6 * (0.5 + 0.5 * Math.sin(" + TWO + " + " + (rnd() * 6.28).toFixed(2) + ")))";
  }
  FX.blur(nd, 2.5, 2); nd.blendingMode = BlendingMode.SCREEN;
  var hz = FX.adj(R, "haze"); var hzl = FX.fx(hz, "ADBE Pro Levels2");
  hzl.property("ADBE Pro Levels2-0007").setValue(HAZE);
  var pimg = FX.imp(TEX + "pr_profile2.png"); try { pimg.mainSource.reload(); } catch (x) {}
  var prof = R.layers.add(pimg); prof.name = "profile"; prof.blendingMode = BlendingMode.MULTIPLY;
  // ---- dark rounded arches (rounded rects in rect space = rounded wedges in polar), breathing slowly
  var ar = FX.shape(R, "arches"); ar.position.setValue([0, 0]);
  // [deg, angular width deg, r0, r1 (gif px), roundness px]
  var AR = [[270, 38, 88, 168, 70], [90, 34, 84, 168, 70], [0, 18, 92, 166, 40], [315, 10, 58, 104, 30], [45, 12, 62, 108, 30],
            [295, 8, 172, 205, 22], [25, 9, 176, 212, 22]];
  for (var a = 0; a < AR.length; a++) {
    var cx = xOf(AR[a][0]), wpx = AR[a][1] / 360 * RW, y0 = AR[a][2] * YR, y1 = AR[a][3] * YR;
    var copies = (cx < 1 || Math.abs(cx - RW / 2) < 1) ? [cx] : [cx];
    var gA = FX.group(ar, "rect", { size: [wpx, y1 - y0], fill: [0, 0, 0] });
    gA.round.setValue(Math.min(wpx, y1 - y0) / 2);
    gA.xf.property("ADBE Vector Position").setValue([cx, (y0 + y1) / 2]);
    var ph3 = (a * 1.7).toFixed(2);
    gA.xf.property("ADBE Vector Scale").expression = "var k = 100 + 6 * Math.sin(" + TWO + " + " + ph3 + "); [k, k]";
  }
  FX.blur(ar, 10);
  ar.opacity.setValue(ARCH);

  // ---- mirror comp: left half + flipped copy (mirror lines at 12 and 6 o'clock)
  var M = FX.comp(tag + "_mirror", RW, RH, fps, L, "fxlib_density");
  for (var i2 = 0; i2 < 2; i2++) {
    var lm = M.layers.add(R); lm.name = i2 ? "right_flipped" : "left";
    var mk = lm.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    var sh = new Shape(); sh.vertices = [[0, 0], [RW / 2, 0], [RW / 2, RH], [0, RH]]; sh.closed = true;
    mk.property("ADBE Mask Shape").setValue(sh);
    if (i2) lm.scale.setValue([-100, 100]);
  }

  var c = FX.comp(tag, W, H, fps, L);
  var m = c.layers.add(M); m.name = "rays";
  var pc = FX.fx(m, "ADBE Polar Coordinates");
  FX.set(pc, "Interpolation", 1); FX.set(pc, "Type of Conversion", 1);       // 1 = Rect to Polar
  var rb = FX.fx(m, "ADBE Radial Blur");
  FX.set(rb, "Amount", 14); FX.set(rb, "Type", 2);                                 // 2 = Zoom
  var tn = FX.fx(m, "CC Toner");
  FX.set(tn, "Tones", 3);                                                         // 3 = Pentone
  FX.set(tn, "Highlights", FX.rgb("FFCDE8")); FX.set(tn, "Brights", FX.rgb("EB76AA"));
  FX.set(tn, "Midtones", FX.rgb("AA466E")); FX.set(tn, "Darktones", FX.rgb("40224E")); FX.set(tn, "Shadows", [0, 0, 0]);
  FX.glow(m, 18 * S, 0.3, 60);
  return FX.done(c);
}
var HAZE = 0.17, ARCH = 85;
