// ae_library helper library. Built on the claude-spine AEFX ideas, extended for cel (toon) effects.
// Every builder file does: $.evalFile(LIB); then defines build() returning a JSON string.
var FX = {};
FX.rgb = function (hex) {
  hex = String(hex).replace("#", "");
  return [parseInt(hex.substr(0, 2), 16) / 255, parseInt(hex.substr(2, 2), 16) / 255, parseInt(hex.substr(4, 2), 16) / 255];
};
FX.rng = function (seed) {
  var a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    var t = Math.imul ? Math.imul(a ^ (a >>> 15), 1 | a) : (a ^ (a >>> 15)) * (1 | a);
    t = (t + (Math.imul ? Math.imul(t ^ (t >>> 7), 61 | t) : (t ^ (t >>> 7)) * (61 | t))) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
FX.folder = function (name) {
  for (var i = 1; i <= app.project.numItems; i++) {
    var it = app.project.item(i);
    if (it instanceof FolderItem && it.name === name) return it;
  }
  return app.project.items.addFolder(name);
};
// Remove every item whose name starts with prefix (a rebuild replaces the old comps; AE caches by NAME, so callers
// still bump _vN when the look changes).
FX.purge = function (prefix) {
  for (var i = app.project.numItems; i >= 1; i--) {
    var it = app.project.item(i);
    if (it.name.indexOf(prefix) === 0 && !(it instanceof FolderItem)) it.remove();
  }
  FX.cleanSolids();
};
FX.cleanSolids = function () {
  for (var i = app.project.numItems; i >= 1; i--) {
    var it = app.project.item(i);
    if (it instanceof FootageItem && it.mainSource instanceof SolidSource && it.usedIn.length === 0) it.remove();
  }
};
FX.comp = function (name, w, h, fps, dur, folder) {
  for (var i = app.project.numItems; i >= 1; i--) { var it = app.project.item(i); if (it.name === name && it instanceof CompItem) it.remove(); }
  var c = app.project.items.addComp(name, Math.round(w / 2) * 2, Math.round(h / 2) * 2, 1, dur, fps);
  c.parentFolder = FX.folder(folder || "fxlib");
  c.bgColor = [0, 0, 0];
  return c;
};
FX.fx = function (layer, match) { return layer.property("ADBE Effect Parade").addProperty(match); };
FX.find = function (group, name) {
  for (var i = 1; i <= group.numProperties; i++) {
    var p = group.property(i);
    if (p.name === name || p.matchName === name) return p;
    if (p.propertyType !== PropertyType.PROPERTY) { var r = FX.find(p, name); if (r) return r; }
  }
  return null;
};
FX.set = function (fx, name, v) {
  var p = FX.find(fx, name);
  if (!p) throw new Error("effect " + fx.name + " has no property " + name);
  p.setValue(v); return p;
};
// keys: [[t, v], ...]. ease: undefined/false = linear, "out" = fast then settle, "in" = slow then fast,
// "both" = easy ease, "hold" = stepped.
FX.keys = function (prop, keys, ease, infl) {
  var t = [], v = [];
  for (var i = 0; i < keys.length; i++) { t.push(keys[i][0]); v.push(keys[i][1]); }
  try { prop.setValuesAtTimes(t, v); } catch (e) { throw new Error("keys on " + prop.name + " (" + prop.matchName + "): " + e.toString()); }
  if (!ease) return prop;
  infl = infl || 75;
  var dims = (prop.value instanceof Array) ? prop.value.length : 1;
  if (prop.propertyValueType === PropertyValueType.TwoD_SPATIAL || prop.propertyValueType === PropertyValueType.ThreeD_SPATIAL) dims = 1;
  for (var k = 1; k <= prop.numKeys; k++) {
    if (ease === "hold") { prop.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD); continue; }
    var lin = new KeyframeEase(0, 0.1), e = new KeyframeEase(0, infl);
    var inE = ease === "out" ? e : (ease === "in" ? lin : e), outE = ease === "out" ? lin : (ease === "in" ? e : e);
    var a = [], b = [];
    for (var d = 0; d < dims; d++) { a.push(inE); b.push(outE); }
    try { prop.setTemporalEaseAtKey(k, a, b); } catch (x) {}
  }
  return prop;
};
FX.solid = function (comp, name, color, w, h) {
  return comp.layers.addSolid(color || [0, 0, 0], name, w || comp.width, h || comp.height, 1);
};
FX.adj = function (comp, name) { var l = FX.solid(comp, name, [1, 1, 1]); l.adjustmentLayer = true; return l; };
FX.shape = function (comp, name) { var l = comp.layers.addShape(); l.name = name; return l; };
// Add a vector group to a shape layer. kind: "ellipse" | "rect" | "path" | "star". Returns accessors re-fetched by path.
FX.group = function (layer, kind, o) {
  o = o || {};
  var root = layer.property("ADBE Root Vectors Group");
  var g = root.addProperty("ADBE Vector Group");
  var gi = root.numProperties;
  var c = g.property("ADBE Vectors Group");
  var mn = { ellipse: "ADBE Vector Shape - Ellipse", rect: "ADBE Vector Shape - Rect", path: "ADBE Vector Shape - Group", star: "ADBE Vector Shape - Star" }[kind];
  c.addProperty(mn);
  if (o.trim) c.addProperty("ADBE Vector Filter - Trim");
  if (o.wiggle) c.addProperty("ADBE Vector Filter - Roughen");
  if (o.repeat) c.addProperty("ADBE Vector Filter - Repeater");
  if (o.stroke) c.addProperty("ADBE Vector Graphic - Stroke");
  if (o.fill) c.addProperty("ADBE Vector Graphic - Fill");
  var cc = layer.property("ADBE Root Vectors Group").property(gi).property("ADBE Vectors Group");
  var tr = layer.property("ADBE Root Vectors Group").property(gi).property("ADBE Vector Transform Group");
  var out = { contents: cc, xf: tr, shape: cc.property(mn) };
  if (kind === "ellipse") { out.size = out.shape.property("ADBE Vector Ellipse Size"); if (o.size) out.size.setValue(o.size); }
  if (kind === "rect") { out.size = out.shape.property("ADBE Vector Rect Size"); if (o.size) out.size.setValue(o.size); out.round = out.shape.property("ADBE Vector Rect Roundness"); }
  if (kind === "path") {
    out.path = out.shape.property("ADBE Vector Shape");
    if (o.points) { var s = new Shape(); s.vertices = o.points; s.closed = !!o.closed; if (o.inT) s.inTangents = o.inT; if (o.outT) s.outTangents = o.outT; out.path.setValue(s); }
  }
  if (kind === "star") {
    out.star = out.shape;
    out.shape.property("ADBE Vector Star Type").setValue(o.polygon ? 2 : 1);
    out.shape.property("ADBE Vector Star Points").setValue(o.points || 5);
    if (o.r1) out.shape.property("ADBE Vector Star Outer Radius").setValue(o.r1);
    if (o.r2 && !o.polygon) out.shape.property("ADBE Vector Star Inner Radius").setValue(o.r2);
  }
  if (o.stroke) {
    var s2 = cc.property("ADBE Vector Graphic - Stroke");
    s2.property("ADBE Vector Stroke Color").setValue(o.stroke);
    out.strokeW = s2.property("ADBE Vector Stroke Width"); out.strokeW.setValue(o.width || 4);
    out.strokeO = s2.property("ADBE Vector Stroke Opacity");
    s2.property("ADBE Vector Stroke Line Cap").setValue(o.cap || 2);    // 2 = round
    s2.property("ADBE Vector Stroke Line Join").setValue(2);
    if (o.taper) {
      try {
        var tp = s2.property("ADBE Vector Stroke Taper");
        tp.property("ADBE Vector Taper Start Length").setValue(o.taper[0]);
        tp.property("ADBE Vector Taper End Length").setValue(o.taper[1]);
      } catch (x) {}
    }
    out.strokeProp = s2;
  }
  if (o.fill) {
    out.fillC = cc.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color"); out.fillC.setValue(o.fill);
    out.fillO = cc.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Opacity");
  }
  if (o.trim) {
    var t = cc.property("ADBE Vector Filter - Trim");
    out.tStart = t.property("ADBE Vector Trim Start"); out.tEnd = t.property("ADBE Vector Trim End"); out.tOff = t.property("ADBE Vector Trim Offset");
  }
  if (o.wiggle) {
    var w = cc.property("ADBE Vector Filter - Roughen");
    out.wSize = w.property("ADBE Vector Roughen Size"); out.wDetail = w.property("ADBE Vector Roughen Detail");
    out.wSpeed = w.property("ADBE Vector Temporal Freq"); out.wSeed = w.property("ADBE Vector Random Seed");
    out.wSize.setValue(o.wiggle[0]); out.wDetail.setValue(o.wiggle[1]); out.wSpeed.setValue(o.wiggle[2]);
    try { w.property("ADBE Vector Correlation").setValue(o.wiggle[3] === undefined ? 50 : o.wiggle[3]); } catch (x) {}
    try { w.property("ADBE Vector Roughen Points").setValue(o.wigglePoints || 2); } catch (x) {}   // 2 = smooth
    if (o.seed !== undefined) out.wSeed.setValue(o.seed);
  }
  if (o.repeat) {
    var r = cc.property("ADBE Vector Filter - Repeater");
    out.rCopies = r.property("ADBE Vector Repeater Copies"); out.rCopies.setValue(o.repeat);
    var rt = r.property("ADBE Vector Repeater Transform");
    rt.property("ADBE Vector Repeater Position").setValue([0, 0]);
    out.rRot = rt.property("ADBE Vector Repeater Rotation"); out.rRot.setValue(360 / o.repeat);
    out.rAnchor = rt.property("ADBE Vector Repeater Anchor");
  }
  return out;
};
// Glow: two passes (tight + wide), coloured A&B. intensity, radius in px.
FX.glow = function (layer, radius, intensity, threshold, colA, colB) {
  var g = FX.fx(layer, "ADBE Glo2");
  FX.set(g, "Glow Threshold", threshold === undefined ? 40 : threshold);
  FX.set(g, "Glow Radius", radius); FX.set(g, "Glow Intensity", intensity);
  if (colA) {
    FX.set(g, "Glow Colors", 2);     // A & B colours
    FX.set(g, "Color A", colA); FX.set(g, "Color B", colB || colA);
  }
  return g;
};
FX.blur = function (layer, amount, dims) {
  var b = FX.fx(layer, "ADBE Gaussian Blur 2"); FX.set(b, "Blurriness", amount);
  if (dims) FX.set(b, "Blur Dimensions", dims);
  try { FX.set(b, "Repeat Edge Pixels", 0); } catch (x) {}
  return b;
};
// Fractal noise on a full-comp solid. o: {type, noise, contrast, brightness, scale, sw, sh, complexity, seed,
//   evo:[[t,deg],..], offset expression, invert, blend, opacity, cycle}
FX.noise = function (comp, name, o) {
  var n = FX.solid(comp, name, [0, 0, 0]);
  var fn = FX.fx(n, "ADBE Fractal Noise");
  FX.set(fn, "Fractal Type", o.type || 1); FX.set(fn, "Noise Type", o.noise || 3);
  FX.set(fn, "Contrast", o.contrast || 100); FX.set(fn, "Brightness", o.brightness || 0);
  if (o.sw) { FX.set(fn, "Uniform Scaling", 0); FX.set(fn, "Scale Width", o.sw); FX.set(fn, "Scale Height", o.sh); }
  else FX.set(fn, "Scale", o.scale || 100);
  FX.set(fn, "Complexity", o.complexity || 4);
  FX.set(fn, "Random Seed", o.seed || 1);
  if (o.invert) FX.set(fn, "Invert", 1);
  if (o.evo) FX.keys(FX.find(fn, "Evolution"), o.evo);
  if (o.cycle) { FX.set(fn, "Cycle Evolution", 1); FX.set(fn, "Cycle (in Revolutions)", o.cycle); }
  if (o.offsetExpr) FX.find(fn, "Offset Turbulence").expression = o.offsetExpr;
  if (o.blend) n.blendingMode = o.blend;
  if (o.opacity !== undefined) n.opacity.setValue(o.opacity);
  return { layer: n, fx: fn };
};
// Radial ramp solid (white centre -> black at radius), for shaping noise into blobs.
FX.ramp = function (comp, name, cx, cy, radius, inner, outer, blend, linear, to) {
  var s = FX.solid(comp, name, [0, 0, 0]);
  var r = FX.fx(s, "ADBE Ramp");
  r.property("ADBE Ramp-0001").setValue([cx, cy]);
  r.property("ADBE Ramp-0002").setValue(inner || [1, 1, 1, 1]);
  r.property("ADBE Ramp-0003").setValue(to || [cx + radius, cy]);
  r.property("ADBE Ramp-0004").setValue(outer || [0, 0, 0, 1]);
  r.property("ADBE Ramp-0005").setValue(linear ? 1 : 2);
  if (blend) s.blendingMode = blend;
  return { layer: s, fx: r };
};
// A hard-edged colour band cut from a grey density comp: luma >= lo is coloured `color` (alpha from luma threshold).
// soft = edge softness in 0..1 luma. Returns the layer (in `comp`).
FX.band = function (comp, density, name, lo, color, soft, hi) {
  var l = comp.layers.add(density); l.name = name;
  var lv = FX.fx(l, "ADBE Easy Levels2");
  FX.set(lv, "Input Black", lo); FX.set(lv, "Input White", Math.min(1, lo + (soft || 0.02)));
  if (hi !== undefined) {                       // keep only lo..hi: subtract the part above hi
    // implemented by the caller stacking bands instead (top band covers this one)
  }
  var sc = FX.fx(l, "ADBE Shift Channels");
  FX.set(sc, "Take Alpha From", 5);             // 5 = luminance... (1 alpha,2 red,3 green,4 blue,5 luminance)
  var fill = FX.fx(l, "ADBE Fill");
  FX.set(fill, "Color", color);
  return l;
};
FX.text = function (comp, name, str, size, font, fill, stroke, strokeW) {
  var t = comp.layers.addText(str); t.name = name;
  var sp = t.property("ADBE Text Properties").property("ADBE Text Document");
  var d = sp.value; d.resetCharStyle(); d.fontSize = size; if (font) d.font = font;
  d.applyFill = true; d.fillColor = fill || [1, 1, 1];
  if (stroke) { d.applyStroke = true; d.strokeColor = stroke; d.strokeWidth = strokeW || 4; d.strokeOverFill = false; }
  d.justification = ParagraphJustification.CENTER_JUSTIFY;
  sp.setValue(d);
  var r = t.sourceRectAtTime(0, false);
  t.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([r.left + r.width / 2, r.top + r.height / 2]);
  t.position.setValue([comp.width / 2, comp.height / 2]);
  return t;
};
FX.done = function (comp, extra) {
  var s = '{"comp":"' + comp.name + '","width":' + comp.width + ',"height":' + comp.height + ',"fps":' + comp.frameRate +
          ',"frames":' + Math.round(comp.duration * comp.frameRate);
  if (extra) s += "," + extra;
  return s + "}";
};
FX.imp = function (path) {
  var f = new File(path); if (!f.exists) throw new Error("file not found: " + path);
  for (var i = 1; i <= app.project.numItems; i++) {
    var q = app.project.item(i);
    if (q instanceof FootageItem && q.mainSource instanceof FileSource && q.mainSource.file && q.mainSource.file.fsName === f.fsName) return q;
  }
  var it = app.project.importFile(new ImportOptions(f)); it.parentFolder = FX.folder("fxlib_textures"); return it;
};
// spark streak flying out on a straight line (ease out), stretching then shrinking. Returns layer.
FX.streak = function (comp, name, cx, cy, ang, r0, r1, t0, t1, len, width, color, glowR) {
  var l = FX.shape(comp, name);
  var g = FX.group(l, "path", { points: [[-len / 2, 0], [len / 2, 0]], stroke: color, width: width, taper: [100, 100] });
  l.position.setValue([cx, cy]);
  var a = ang * Math.PI / 180;
  FX.keys(l.position, [[t0, [cx + Math.cos(a) * r0, cy + Math.sin(a) * r0]], [t1, [cx + Math.cos(a) * r1, cy + Math.sin(a) * r1]]], "out");
  l.rotation.setValue(ang);
  FX.keys(l.scale, [[t0, [30, 100]], [t0 + (t1 - t0) * 0.25, [120, 100]], [t1, [10, 60]]], false);
  FX.keys(l.opacity, [[t0 - 0.001, 0], [t0, 100], [t1 - (t1 - t0) * 0.25, 100], [t1, 0]], false);
  return l;
};

// time of GIF cycle frame n (fractional n interpolates; past the end extrapolates at 25 fps)
FX.gt = function (hero) {
  var T = GIFT[hero];
  return function (n) {
    if (n <= 0) return n * 0.04;
    var i = Math.floor(n), fr = n - i;
    if (i >= T.length - 1) return T[T.length - 1] + (n - (T.length - 1)) * 0.04;
    return T[i] + (T[i + 1] - T[i]) * fr;
  };
};

// ---------------------------------------------------------------- cel (toon) helpers
// Set Matte: keep `layer` only where `matteLayer` has alpha (matteLayer may be hidden).
FX.setMatte = function (layer, matteLayer, invert) {
  var m = FX.fx(layer, "ADBE Set Matte3");
  FX.set(m, "Take Matte From Layer", matteLayer.index);
  FX.set(m, "Use For Matte", 1);                // 1 = alpha channel
  if (invert) FX.set(m, "Invert Matte", 1);
  return m;
};
// A hard band layer from a grey comp: alpha = luma above threshold `lo` (keyable via returned levels), colour fill.
// lo may be a number or [[t, v], ...] keys.
FX.cel = function (comp, density, name, lo, color, soft) {
  var l = comp.layers.add(density); l.name = name;
  var lv = FX.fx(l, "ADBE Pro Levels2");          // Easy Levels' inputs cannot be keyed in AE 26
  var ib = lv.property("ADBE Pro Levels2-0004"), iw = lv.property("ADBE Pro Levels2-0005");
  soft = soft || 0.025;
  if (lo instanceof Array) {
    FX.keys(ib, lo, false);
    var wk = []; for (var i = 0; i < lo.length; i++) wk.push([lo[i][0], Math.min(1, lo[i][1] + soft)]);
    FX.keys(iw, wk, false);
  } else { ib.setValue(lo); iw.setValue(Math.min(1, lo + soft)); }
  var sc = FX.fx(l, "ADBE Shift Channels"); FX.set(sc, "Take Alpha From", 5);
  var fl = FX.fx(l, "ADBE Fill"); FX.set(fl, "Color", color);
  return l;
};
// Grey density comp from a list of builders: each f(comp) adds layers. Black base.
FX.density = function (name, W, H, fps, D, build) {
  var d = FX.comp(name, W, H, fps, D, "fxlib_density");
  FX.solid(d, "black", [0, 0, 0]);
  build(d);
  return d;
};
// Scale a radial ramp (made with FX.ramp) about the comp centre over time: keys [[t, radiusPx], ...].
FX.rampRadius = function (rampObj, cx, cy, keys) {
  var end = FX.find(rampObj.fx, "ADBE Ramp-0003");
  var k = []; for (var i = 0; i < keys.length; i++) k.push([keys[i][0], [cx + Math.max(0.5, keys[i][1]), cy]]);
  FX.keys(end, k, false);
};
// Track matte (respects the matte layer's effects, unlike Set Matte). The matte layer is hidden by AE.
FX.matte = function (layer, matteLayer, inverted) {
  layer.setTrackMatte(matteLayer, inverted ? TrackMatteType.ALPHA_INVERTED : TrackMatteType.ALPHA);
  return layer;
};
// cel band limited to another cel band: returns the coloured layer (its matte is created right above it).
FX.celIn = function (comp, density, name, lo, color, soft, maskDensity, maskLo, maskInvert) {
  var l = FX.cel(comp, density, name, lo, color, soft);
  var m = FX.cel(comp, maskDensity, name + "_matte", maskLo, [1, 1, 1], 0.02);
  FX.matte(l, m, maskInvert);
  return l;
};
