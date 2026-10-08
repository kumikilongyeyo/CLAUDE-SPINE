// re_kit: shared helpers for the realistic (re_) builders of target_ring, sun_rune_burst, electric_star,
// electric_sphere and fire_rose_burst. Loaded by those builders after fxlib.jsx (run.jsx loads fxlib + times).
var RE = {};
RE.ROOT = FXLIB_TEXTURES;
RE.K = RE.ROOT + "kenney_particle-pack/PNG (Transparent)/";
RE.KS = RE.ROOT + "kenney_smoke-particles/PNG/";
RE.R = RE.ROOT + "ready/";
RE.FOLDER = "fxlib_realistic";

RE.findComp = function (name) {
  for (var i = 1; i <= app.project.numItems; i++) { var it = app.project.item(i); if (it instanceof CompItem && it.name === name) return it; }
  throw new Error("comp not found: " + name);
};
// remove my own older items: prefix must be specific to one hero (e.g. "re_target_ring_v"), never plain "re_"
RE.purge = function (prefix, keepVersionTag) {
  for (var i = app.project.numItems; i >= 1; i--) {
    var it = app.project.item(i);
    if (!(it instanceof FolderItem) && it.name.indexOf(prefix) === 0) it.remove();
  }
};
RE.comp = function (name, w, h, dur) {
  var c = FX.comp(name, w, h, 25, dur, RE.FOLDER);
  c.motionBlur = true; c.shutterAngle = 270; c.shutterPhase = -135;
  try { c.motionBlurSamplesPerFrame = 24; c.motionBlurAdaptiveSampleLimit = 128; } catch (x) {}
  return c;
};
// duplicate an exact comp keeping only layers whose name passes keep(name); glows etc. are dropped
RE.only = function (srcName, newName, keep, disableOnly) {
  for (var i = app.project.numItems; i >= 1; i--) { var it = app.project.item(i); if (it instanceof CompItem && it.name === newName) it.remove(); }
  var d = RE.findComp(srcName).duplicate();
  d.name = newName; d.parentFolder = FX.folder(RE.FOLDER);
  // disable (not remove) when layers may be parents of kept ones: removing a parent bakes its children's motion
  for (var j = d.numLayers; j >= 1; j--) if (!keep(d.layer(j).name)) { if (disableOnly) d.layer(j).enabled = false; else d.layer(j).remove(); }
  return d;
};
// a precomp/footage layer as light: tint (luma -> colour), blur, additive
RE.light = function (comp, src, name, color, blur, opacity) {
  var l = comp.layers.add(src); l.name = name;
  if (color) { var t = FX.fx(l, "ADBE Tint"); FX.set(t, "Map Black To", [0, 0, 0]); FX.set(t, "Map White To", color); }
  if (blur) FX.blur(l, blur);
  l.blendingMode = BlendingMode.ADD;
  if (opacity !== undefined) { if (opacity instanceof Array) FX.keys(l.opacity, opacity, false); else l.opacity.setValue(opacity); }
  return l;
};
// colour a white-on-alpha sprite (Kenney) keeping its alpha
RE.fill = function (l, color) { var f = FX.fx(l, "ADBE Fill"); FX.set(f, "Color", color); return f; };
RE.tint = function (l, color, black) { var t = FX.fx(l, "ADBE Tint"); FX.set(t, "Map Black To", black || [0, 0, 0]); FX.set(t, "Map White To", color); return t; };
// texture footage layer: o = {pos, scale (number or [x,y]), rot, blend, op (keys or number), mask feather px}
RE.tex = function (comp, path, name, o) {
  o = o || {};
  var l = comp.layers.add(FX.imp(path)); l.name = name;
  if (o.pos) l.position.setValue(o.pos);
  if (o.scale !== undefined) l.scale.setValue(o.scale instanceof Array ? o.scale : [o.scale, o.scale]);
  if (o.rot !== undefined) l.rotation.setValue(o.rot);
  l.blendingMode = o.blend === undefined ? BlendingMode.ADD : o.blend;
  if (o.op !== undefined) { if (o.op instanceof Array) FX.keys(l.opacity, o.op, false); else l.opacity.setValue(o.op); }
  if (o.mask) RE.ellMask(l, o.mask, o.inset || 0);
  return l;
};
// feathered ellipse mask over the layer's source rect (kills rectangular photo edges)
RE.ellMask = function (l, feather, inset) {
  var w = l.source.width, h = l.source.height, i = inset || 0;
  var rx = w / 2 - i, ry = h / 2 - i, cx = w / 2, cy = h / 2, k = 0.5523;
  var s = new Shape();
  s.vertices = [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]];
  s.inTangents = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]];
  s.outTangents = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]];
  s.closed = true;
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([feather, feather]);
  return m;
};
// one spark: a tapered hot streak flying from p0 along angle `ang` (deg) a distance `dist`, with a little gravity,
// motion blurred. o = {len, w, color, grav, glow}
RE.spark = function (comp, name, p0, ang, dist, t0, t1, o) {
  o = o || {};
  var len = o.len || 8, wd = o.w || 2;
  var l = FX.shape(comp, name);
  FX.group(l, "path", { points: [[-len / 2, 0], [len / 2, 0]], stroke: o.color || [1, 0.9, 0.6], width: wd, taper: [100, 30] });
  var a = ang * Math.PI / 180, g = o.grav || 0;
  var pm = [p0[0] + Math.cos(a) * dist * 0.7, p0[1] + Math.sin(a) * dist * 0.7 + g * 0.3];
  var p1 = [p0[0] + Math.cos(a) * dist, p0[1] + Math.sin(a) * dist + g];
  FX.keys(l.position, [[t0, p0], [t0 + (t1 - t0) * 0.4, pm], [t1, p1]], false);
  l.rotation.setValue(ang);
  l.motionBlur = true;
  FX.keys(l.opacity, [[t0 - 0.001, 0], [t0, 100], [t0 + (t1 - t0) * 0.6, 90], [t1, 0]], false);
  FX.keys(l.scale, [[t0, [100, 100]], [t1, [40, 70]]], false);
  l.blendingMode = BlendingMode.ADD;
  return l;
};
// heat shimmer / gas wobble adjustment over everything below
RE.shimmer = function (comp, amount, size, revs) {
  var a = FX.adj(comp, "heat_shimmer");
  var td = FX.fx(a, "ADBE Turbulent Displace");
  FX.set(td, "Amount", amount); FX.set(td, "Size", size); FX.set(td, "Complexity", 2);
  FX.keys(FX.find(td, "Evolution"), [[0, 0], [comp.duration, 360 * (revs || 2)]], false);
  return a;
};
// evolving fractal noise solid coloured black->c1->c2 (plasma / molten material), additive
RE.plasma = function (comp, name, o) {
  var n = FX.noise(comp, name, { type: o.type || 6, noise: 3, contrast: o.contrast || 180, brightness: o.brightness || -20, scale: o.scale || 40, complexity: o.complexity || 3, seed: o.seed || 7, evo: [[0, 0], [comp.duration, o.evo || 900]] });
  if (o.cycle) { FX.set(n.fx, "Cycle Evolution", 1); FX.set(n.fx, "Cycle (in Revolutions)", Math.round((o.evo || 900) / 360)); }
  if (o.rotKeys) FX.keys(FX.find(n.fx, "Rotation"), o.rotKeys, false);
  RE.tint(n.layer, o.color || [1, 0.7, 0.3]);
  n.layer.blendingMode = BlendingMode.ADD;
  return n.layer;
};
// a copy of a precomp's single stroke-shape layer with a short Trim Paths segment running around it (energy flow).
// segPct = segment length in %, offKeys = [[t, deg], ...]
RE.flow = function (srcComp, newName, layerName, segPct, offKeys) {
  for (var i = app.project.numItems; i >= 1; i--) { var it = app.project.item(i); if (it instanceof CompItem && it.name === newName) it.remove(); }
  var d = srcComp.duplicate(); d.name = newName; d.parentFolder = FX.folder(RE.FOLDER);
  var l = d.layer(layerName);
  var cc = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
  var tr = cc.addProperty("ADBE Vector Filter - Trim");
  tr.moveTo(2);
  cc = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
  tr = cc.property("ADBE Vector Filter - Trim");
  tr.property("ADBE Vector Trim Start").setValue(0); tr.property("ADBE Vector Trim End").setValue(segPct);
  FX.keys(tr.property("ADBE Vector Trim Offset"), offKeys, false);
  return d;
};
// feathered circular mask centred on a point of the layer's source (e.g. the burst in a photo)
RE.circMask = function (l, x, y, R, feather) {
  var k = 0.5523, s = new Shape();
  s.vertices = [[x, y - R], [x + R, y], [x, y + R], [x - R, y]];
  s.inTangents = [[-R * k, 0], [0, -R * k], [R * k, 0], [0, R * k]];
  s.outTangents = [[R * k, 0], [0, R * k], [-R * k, 0], [0, -R * k]]; s.closed = true;
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  m.property("ADBE Mask Shape").setValue(s); m.property("ADBE Mask Feather").setValue([feather, feather]);
  return m;
};
// alpha = luminance (for additive light layers built from opaque-black sources, which would otherwise make the
// whole frame opaque black in the exported RGBA)
RE.lumAlpha = function (l) { var sc = FX.fx(l, "ADBE Shift Channels"); FX.set(sc, "Take Alpha From", 5); return sc; };
// real-water treatment of a cel water precomp `drv` (its alpha = the water): the cel shading softened and run through
// CC Glass (refraction + specular from its own alpha), plus photo water material (water_02 screen, water_01 overlay)
// matted to it. o = {pos, scale: [[t, s], ...], glass: {height, soft, disp, amb, spec}, photoOp, foamOp, cut(layer)}
RE.waterize = function (c, drv, nm, o) {
  o = o || {}; var g = o.glass || {};
  var wb = c.layers.add(drv); wb.name = nm + "_body";
  FX.blur(wb, o.blur || 2);
  if (o.exposure) { var ex = FX.fx(wb, "ADBE Exposure2"); FX.set(ex, "Exposure", o.exposure); }
  var gl = FX.fx(wb, "CC Glass");
  FX.set(gl, "Bump Map", wb.index); FX.set(gl, "Softness", g.soft || 14); FX.set(gl, "Height", g.height || 35); FX.set(gl, "Displacement", g.disp === undefined ? 60 : g.disp);
  FX.set(gl, "Light Intensity", g.light || 85); FX.set(gl, "Light Direction", -45); FX.set(gl, "Light Height", 50);
  FX.set(gl, "Ambient", g.amb || 55); FX.set(gl, "Diffuse", 45); FX.set(gl, "Specular", g.spec || 100); FX.set(gl, "Roughness", 0.04); FX.set(gl, "Metal", 30);
  if (o.cut) o.cut(wb);
  var mats = [["water_02.png", BlendingMode.SCREEN, o.photoOp === undefined ? 26 : o.photoOp, FX.rgb("DFFBFF"), FX.rgb("0A3C44")],
              ["water_01.png", BlendingMode.OVERLAY, o.foamOp === undefined ? 40 : o.foamOp, FX.rgb("E8FFFF"), FX.rgb("0E5A60")]];
  var out = { body: wb, photos: [] };
  for (var i = 0; i < mats.length; i++) {
    var p = RE.tex(c, RE.R + mats[i][0], nm + "_" + mats[i][0].replace(".png", ""), { pos: o.pos || [c.width / 2, c.height / 2], blend: mats[i][1] });
    RE.tint(p, mats[i][3], mats[i][4]);
    if (o.scale) FX.keys(p.scale, o.scale, "out"); 
    FX.keys(p.rotation, [[0, -8 + i * 20], [c.duration, 14 + i * 20]], false);
    p.opacity.setValue(mats[i][2]);
    var m = c.layers.add(drv); m.name = p.name + "_matte"; if (o.cut) o.cut(m);
    FX.matte(p, m, false);
    out.photos.push(p);
  }
  return out;
};
// set an effect property if it exists (names differ between effects/versions); returns true when set
RE.trySet = function (fx, name, v) { var p = FX.find(fx, name); if (!p) return false; try { p.setValue(v); return true; } catch (e) { return false; } };
