// el_kit: shared helpers for the realistic ELEMENT set (el_fire_burst, el_fire_loop, el_water_splash, el_ice_shatter,
// el_lightning_strike, el_earth_rock_burst, el_wind_swirl, el_poison_bubbles). Loaded after fxlib + times (run.jsx)
// and re_kit (textures, ellipse masks, tint/fill helpers).
$.evalFile(FXLIB_DIR + "re_kit.jsx");
var EL = {};
EL.FOLDER = "fxlib_realistic";
EL.KS = RE.KS; EL.K = RE.K; EL.R = RE.R;

// main / sub comp with real motion blur. Remove older versions of THIS element only (prefix "el_<name>_v").
EL.comp = function (name, w, h, dur) {
  var c = FX.comp(name, w, h, 25, dur, EL.FOLDER);
  c.motionBlur = true; c.shutterAngle = 200; c.shutterPhase = -100;
  try { c.motionBlurSamplesPerFrame = 16; c.motionBlurAdaptiveSampleLimit = 64; } catch (x) {}
  return c;
};
EL.purge = function (prefix) {
  if (!/^el_[a-z_]+_v$/.test(prefix)) throw new Error("unsafe purge prefix " + prefix);
  RE.purge(prefix);
};
// footage layer, NORMAL blend unless o.blend given. o: pos, scale, rot, op, mask (feather px), inset, anchor
EL.tex = function (comp, path, name, o) {
  o = o || {};
  var l = RE.tex(comp, path, name, { pos: o.pos, scale: o.scale, rot: o.rot, op: o.op, mask: o.mask, inset: o.inset,
                                     blend: o.blend === undefined ? BlendingMode.NORMAL : o.blend });
  if (o.anchor) l.anchorPoint.setValue(o.anchor);
  return l;
};
EL.layerOf = function (comp, src, name, blend) { var l = comp.layers.add(src); l.name = name; if (blend !== undefined) l.blendingMode = blend; return l; };

// --- expressions ---------------------------------------------------------------------------------------------
// ballistic flight with linear drag k (1/s) and gravity g (px/s^2, +down), from p0 at t0 with velocity v (px/s).
// Before t0 the layer sits at p0.
EL.ballExpr = function (p0, v, g, k, t0) {
  k = Math.max(0.001, k);
  return "var t = Math.max(0, time - " + t0 + "), k = " + k + ", e = (1 - Math.exp(-k * t)) / k;\n" +
         "[" + p0[0] + " + " + v[0] + " * e, " + p0[1] + " + " + v[1] + " * e + " + g + " / k * (t - e)]";
};
EL.ball = function (layer, p0, v, g, k, t0) { layer.position.expression = EL.ballExpr(p0, v, g, k, t0); return layer; };
// rotation that spins at w deg/s, slowed by the same drag
EL.spin = function (layer, r0, w, k, t0) {
  k = Math.max(0.001, k);
  layer.rotation.expression = "var t = Math.max(0, time - " + t0 + "), k = " + k + "; " + r0 + " + " + w + " * (1 - Math.exp(-k * t)) / k";
  return layer;
};
// life opacity: 0 before t0, pops to peak in `fin` s, holds, fades over the last `fout` s of `life`
EL.life = function (layer, t0, life, peak, fin, fout) {
  fin = fin === undefined ? 0.04 : fin; fout = fout === undefined ? life * 0.5 : fout;
  FX.keys(layer.opacity, [[Math.max(0, t0 - 0.001), 0], [t0 + fin, peak], [t0 + life - fout, peak], [t0 + life, 0]], false);
  return layer;
};

// --- materials -----------------------------------------------------------------------------------------------
// CC Toner pentone heat map on a layer: luma -> shadows..highlights
EL.toner = function (l, hi, br, mid, dk, sh) {
  var t = FX.fx(l, "CC Toner");
  t.property("CC Toner-0005").setValue(3);       // pentone
  t.property("CC Toner-0001").setValue(hi); t.property("CC Toner-0006").setValue(br);
  t.property("CC Toner-0002").setValue(mid); t.property("CC Toner-0007").setValue(dk);
  t.property("CC Toner-0003").setValue(sh);
  return t;
};
EL.HEAT = [FX.rgb("FFFBEA"), FX.rgb("FFD45A"), FX.rgb("FF7A12"), FX.rgb("B82406"), FX.rgb("1A0602")];
EL.heat = function (l) { return EL.toner(l, EL.HEAT[0], EL.HEAT[1], EL.HEAT[2], EL.HEAT[3], EL.HEAT[4]); };
EL.bevel = function (l, thick, angle, inten, color) {
  var b = FX.fx(l, "ADBE Bevel Alpha");
  b.property("ADBE Bevel Alpha-0001").setValue(thick); b.property("ADBE Bevel Alpha-0002").setValue(angle === undefined ? -50 : angle);
  b.property("ADBE Bevel Alpha-0004").setValue(inten === undefined ? 0.6 : inten);
  if (color) b.property("ADBE Bevel Alpha-0003").setValue(color);
  return b;
};
EL.hueSat = function (l, sat, light, colorize, hue, csat) {
  var h = FX.fx(l, "ADBE HUE SATURATION");
  if (colorize) { h.property("ADBE HUE SATURATION-0007").setValue(1); h.property("ADBE HUE SATURATION-0008").setValue(hue || 0);
    h.property("ADBE HUE SATURATION-0009").setValue(csat === undefined ? 25 : csat); h.property("ADBE HUE SATURATION-0010").setValue(light || 0); }
  else { h.property("ADBE HUE SATURATION-0005").setValue(sat || 0); h.property("ADBE HUE SATURATION-0006").setValue(light || 0); }
  return h;
};
EL.levels = function (l, inB, inW, gamma) {
  var lv = FX.fx(l, "ADBE Pro Levels2");
  lv.property("ADBE Pro Levels2-0004").setValue(inB); lv.property("ADBE Pro Levels2-0005").setValue(inW);
  if (gamma) lv.property("ADBE Pro Levels2-0006").setValue(gamma);
  return lv;
};
// turbulent displace that evolves `revs` turns over `dur`; cycle=true makes it loop over dur
EL.turb = function (l, amount, size, dur, revs, cycle, complexity) {
  var td = FX.fx(l, "ADBE Turbulent Displace");
  FX.set(td, "Amount", amount); FX.set(td, "Size", size); FX.set(td, "Complexity", complexity || 2);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [dur, 360 * (revs || 1)]], false);
  if (cycle) { FX.set(td, "Cycle Evolution", 1); FX.set(td, "Cycle (in Revolutions)", revs || 1); }
  return td;
};
// polygon shape layer (closed), points in layer space
EL.poly = function (comp, name, pts, fill, stroke, sw) {
  var l = FX.shape(comp, name);
  FX.group(l, "path", { points: pts, closed: true, fill: fill, stroke: stroke, width: sw || 1 });
  return l;
};
// a closed mask from a point list on a layer (layer space). feather px.
EL.mask = function (l, pts, feather, mode) {
  var s = new Shape(); s.vertices = pts; s.closed = true;
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  m.property("ADBE Mask Shape").setValue(s);
  if (feather) m.property("ADBE Mask Feather").setValue([feather, feather]);
  if (mode) m.maskMode = mode;
  return m;
};
// soft radial light blob (solid + feathered ellipse mask), additive
EL.blob = function (comp, name, color, cx, cy, r, feather, blend) {
  var l = FX.solid(comp, name, color, Math.round(r * 2 + feather * 2), Math.round(r * 2 + feather * 2));
  var w = l.source.width, h = l.source.height;
  RE.ellMask(l, feather, feather);
  l.position.setValue([cx, cy]);
  l.blendingMode = blend === undefined ? BlendingMode.ADD : blend;
  return l;
};
// jagged polygon around 0,0: n points, radius r, roughness 0..1, rng
EL.jag = function (n, rx, ry, rough, rnd) {
  var p = [];
  for (var i = 0; i < n; i++) { var a = (i + (rnd() - 0.5) * 0.5) / n * Math.PI * 2, rr = 1 - rough * rnd();
    p.push([Math.cos(a) * rx * rr, Math.sin(a) * ry * rr]); }
  return p;
};
EL.done = function (c, blend, anchor, loop) {
  return FX.done(c, '"blend":"' + blend + '","anchor_px":[' + anchor[0] + ',' + anchor[1] + '],"loop":' + (loop ? "true" : "false"));
};
// feathered ellipse mask with its own centre/radii in layer space
EL.ell = function (l, cx, cy, rx, ry, feather) {
  var k = 0.5523, s = new Shape();
  s.vertices = [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]];
  s.inTangents = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]];
  s.outTangents = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]];
  s.closed = true;
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([feather, feather]);
  return m;
};
// alpha = luminance (for grey noise fields that will be coloured afterwards: keeps black truly transparent)
EL.lumaAlpha = function (l) { var sc = FX.fx(l, "ADBE Shift Channels"); FX.set(sc, "Take Alpha From", 5); return sc; };
// a small filled ellipse particle (for embers, droplets, pebbles)
EL.dot = function (comp, name, w, h, color) {
  var l = FX.shape(comp, name);
  var g = FX.group(l, "ellipse", { size: [w, h], fill: color });
  return { layer: l, fill: g.fillC };
};
// luminance key that MULTIPLIES the existing alpha (keeps masks): darks fade out over `soft` (0..255 levels)
EL.extract = function (l, soft) {
  var ex = FX.fx(l, "ADBE Extract");
  FX.set(ex, "Black Point", 0); FX.set(ex, "Black Softness", soft === undefined ? 160 : soft);
  return ex;
};
// bloom without the Glow effect: the finished body comp + a thresholded, blurred, additive copy of itself.
// (Glow on a layer/adjustment in el_fire_burst tore into horizontal hatching under aerender multi-frame rendering.)
// o: {blur, lo (levels input black 0..1), opacity (number or keys), tint}
EL.wrapBloom = function (body, name, o) {
  o = o || {};
  var m = EL.comp(name, body.width, body.height, body.duration);
  var b = EL.layerOf(m, body, "body");
  var g = EL.layerOf(m, body, "bloom", BlendingMode.ADD);
  EL.levels(g, o.lo === undefined ? 0.45 : o.lo, 1, 1);
  if (o.tint) RE.tint(g, o.tint);
  FX.blur(g, o.blur || 18);
  if (o.opacity instanceof Array) FX.keys(g.opacity, o.opacity, false); else g.opacity.setValue(o.opacity === undefined ? 60 : o.opacity);
  return m;
};
// group the layers of `comp` whose name passes test(name) into a precomp (keyframes and expressions move with
// them). Splitting a heavy stack this way removed the horizontal render hatching that el_fire_burst showed when
// ~150 textured layers sat in one comp (every subset rendered clean; only the full stack hatched).
EL.group = function (comp, name, test) {
  var idx = [];
  for (var i = 1; i <= comp.numLayers; i++) if (test(comp.layer(i).name)) idx.push(i);
  if (!idx.length) return null;
  var pc = comp.layers.precompose(idx, name, true);
  pc.parentFolder = FX.folder(EL.FOLDER);
  pc.motionBlur = comp.motionBlur; pc.shutterAngle = comp.shutterAngle; pc.shutterPhase = comp.shutterPhase;
  return pc;
};
// final wrapper whose border is GUARANTEED alpha 0: the body comp under a feathered rounded-rect mask inset
// `inset` px with feather `feather` px (AE feather is centred on the mask edge, so inset >= feather / 2 + 2).
EL.edgeSafe = function (body, name, inset, feather) {
  var m = EL.comp(name, body.width, body.height, body.duration);
  var l = EL.layerOf(m, body, "body");
  var w = body.width, h = body.height, i = inset;
  EL.mask(l, [[i, i], [w - i, i], [w - i, h - i], [i, h - i]], feather);
  // the feather has a long faint tail: a hard mask 2 px in, intersected, makes the outer ring exactly 0
  EL.mask(l, [[2, 2], [w - 2, 2], [w - 2, h - 2], [2, h - 2]], 0, MaskMode.INTERSECT);
  return m;
};
// closed smooth (Catmull-Rom) filled/stroked path; sharp[i] = true keeps a corner at point i (finger tips)
EL.smoothPoly = function (comp, name, pts, sharp, fill, stroke, sw, k) {
  k = k === undefined ? 0.2 : k;
  var n = pts.length, inT = [], outT = [];
  for (var i = 0; i < n; i++) {
    var a = pts[(i - 1 + n) % n], b = pts[(i + 1) % n];
    var tx = (b[0] - a[0]) * k, ty = (b[1] - a[1]) * k;
    if (sharp && sharp[i]) { tx = 0; ty = 0; }
    inT.push([-tx, -ty]); outT.push([tx, ty]);
  }
  var l = FX.shape(comp, name);
  FX.group(l, "path", { points: pts, closed: true, inT: inT, outT: outT, fill: fill, stroke: stroke, width: sw || 1 });
  return l;
};
