// Shared helpers for every template. P (the merged parameters) is defined above this file when it runs.
var AEFX = {};
AEFX.rgb = function (hex) {
  hex = String(hex).replace("#", "");
  return [parseInt(hex.substr(0, 2), 16) / 255, parseInt(hex.substr(2, 2), 16) / 255, parseInt(hex.substr(4, 2), 16) / 255];
};
AEFX.rng = function (seed) {           // mulberry32: same seed, same effect, on every machine
  var a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    var t = Math.imul ? Math.imul(a ^ (a >>> 15), 1 | a) : (a ^ (a >>> 15)) * (1 | a);
    t = (t + (Math.imul ? Math.imul(t ^ (t >>> 7), 61 | t) : (t ^ (t >>> 7)) * (61 | t))) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};
AEFX.folder = function () {
  for (var i = 1; i <= app.project.numItems; i++) {
    var it = app.project.item(i);
    if (it instanceof FolderItem && it.name === "ae_fx_templates") return it;
  }
  return app.project.items.addFolder("ae_fx_templates");
};
AEFX.exists = function (name) {
  for (var i = 1; i <= app.project.numItems; i++) if (app.project.item(i).name === name) return true;
  return false;
};
AEFX.uniq = function (name) {
  if (!AEFX.exists(name)) return name;
  var n = 2; while (AEFX.exists(name + "_" + n)) n++;
  return name + "_" + n;
};
AEFX.comp = function (name, w, h, fps, dur) {
  var c = app.project.items.addComp(AEFX.uniq(name), w, h, 1, dur, fps);
  c.parentFolder = AEFX.folder();
  c.bgColor = [0, 0, 0];
  return c;
};
AEFX.fx = function (layer, match) { return layer.property("ADBE Effect Parade").addProperty(match); };
AEFX.setv = function (fx, name, v) { fx.property(name).setValue(v); };
// keys: [[time, value], ...]; ease: true gives Easy Ease on every key
AEFX.keys = function (prop, keys, ease) {
  var t = [], v = [];
  for (var i = 0; i < keys.length; i++) { t.push(keys[i][0]); v.push(keys[i][1]); }
  prop.setValuesAtTimes(t, v);
  if (ease) {
    var e = new KeyframeEase(0, 60);
    for (var k = 1; k <= prop.numKeys; k++) {
      try { prop.setTemporalEaseAtKey(k, [e], [e]); } catch (x) { try { prop.setTemporalEaseAtKey(k, [e, e, e], [e, e, e]); } catch (y) {} }
    }
  }
};
// Depth-first search for a property by display name or match name anywhere under an effect or group.
AEFX.find = function (group, name) {
  for (var i = 1; i <= group.numProperties; i++) {
    var p = group.property(i);
    if (p.name === name || p.matchName === name) return p;
    if (p.propertyType !== PropertyType.PROPERTY) { var r = AEFX.find(p, name); if (r) return r; }
  }
  return null;
};
AEFX.set = function (fx, name, v) {
  var p = AEFX.find(fx, name);
  if (!p) throw new Error("effect " + fx.name + " has no property " + name);
  p.setValue(v); return p;
};
// Particles flying on baked parabolas (no particle plug-in, so it renders the same everywhere).
// o: {n, cx, cy, speed, speed_var, angle, spread (deg, around angle; 360 = all round), gravity, life, life_var,
//     size, size_var, stretch, color, color2, shape ("drop"|"circle"|"spark"), seed, delay_spread, glow}
AEFX.burst = function (comp, o) {
  var rnd = AEFX.rng(o.seed), D = comp.duration, fps = comp.frameRate;
  for (var i = 0; i < o.n; i++) {
    var l = AEFX.shape(comp, "p" + i);
    var sz = o.size * (1 + (rnd() * 2 - 1) * o.size_var);
    var g = l.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
    var c = g.property("ADBE Vectors Group");
    if (o.shape === "spark") { c.addProperty("ADBE Vector Shape - Rect"); } else { c.addProperty("ADBE Vector Shape - Ellipse"); }
    c.addProperty("ADBE Vector Graphic - Fill");
    var cc = l.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
    var shp = o.shape === "spark" ? cc.property("ADBE Vector Shape - Rect").property("ADBE Vector Rect Size") : cc.property("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size");
    shp.setValue(o.shape === "spark" ? [sz * 2.4, sz * 0.5] : [sz, sz]);
    cc.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue(rnd() < 0.35 ? o.color2 : o.color);
    var a = (o.angle + (rnd() * 2 - 1) * o.spread / 2) * Math.PI / 180;
    var sp = o.speed * (1 + (rnd() * 2 - 1) * o.speed_var);
    var vx = Math.cos(a) * sp, vy = -Math.sin(a) * sp;               // AE y points down: up is negative
    var t0 = D * o.delay_spread * rnd(), life = Math.min(D - t0, o.life * (1 + (rnd() * 2 - 1) * o.life_var));
    var steps = Math.max(4, Math.round(life * fps / 2)), pt = [], rt = [], st = [], ot = [];
    for (var k = 0; k <= steps; k++) {
      var t = life * k / steps, x = o.cx + vx * t, y = o.cy + vy * t + 0.5 * o.gravity * t * t;
      var dx = vx, dy = vy + o.gravity * t, ang = Math.atan2(dy, dx) * 180 / Math.PI;
      var spd = Math.sqrt(dx * dx + dy * dy);
      pt.push([t0 + t, [x, y]]); rt.push([t0 + t, ang]);
      var sq = 1 + o.stretch * Math.min(1, spd / (o.speed + 1));
      var fade = k / steps, sc = 100 * (1 - 0.55 * fade * fade);
      st.push([t0 + t, [sc * sq, sc / Math.sqrt(sq)]]);
      ot.push([t0 + t, Math.max(0, fade > 0.7 ? 100 * (1 - (fade - 0.7) / 0.3) : 100)]);
    }
    AEFX.keys(l.position, pt, false);
    if (o.stretch > 0 || o.shape === "spark") AEFX.keys(l.rotation, rt, false);
    AEFX.keys(l.scale, st, false);
    AEFX.keys(l.opacity, (t0 > 0.002 ? [[0, 0], [t0 - 0.001, 0]] : []).concat(ot), false);
    if (o.glow) { var gl = AEFX.fx(l, "ADBE Glo2"); gl.property("Glow Threshold").setValue(35); gl.property("Glow Radius").setValue(sz * 1.2); gl.property("Glow Intensity").setValue(o.glow); }
  }
};
AEFX.shape = function (comp, name) {
  var l = comp.layers.addShape(); l.name = name; return l;
};
AEFX.ellipse = function (layer, size, fill, stroke, strokeW) {
  // Property references go invalid after addProperty, so everything is re-fetched by path at the end.
  var g = layer.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
  var c = g.property("ADBE Vectors Group");
  c.addProperty("ADBE Vector Shape - Ellipse");
  if (fill) c.addProperty("ADBE Vector Graphic - Fill");
  if (stroke) c.addProperty("ADBE Vector Graphic - Stroke");
  var cc = layer.property("ADBE Root Vectors Group").property(layer.property("ADBE Root Vectors Group").numProperties).property("ADBE Vectors Group");
  var out = { size: cc.property("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size"), stroke: null, fill: null };
  out.size.setValue([size, size]);
  if (fill) { out.fill = cc.property("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color"); out.fill.setValue(fill); }
  if (stroke) {
    var s = cc.property("ADBE Vector Graphic - Stroke");
    s.property("ADBE Vector Stroke Color").setValue(stroke);
    out.stroke = s.property("ADBE Vector Stroke Width");
    out.stroke.setValue(strokeW || 4);
  }
  return out;
};
// A soft round light with no blur clipping: a coloured full-comp solid matted by a radial ramp. Animate
// .matte (scale about the centre) for size and .fill (opacity) for brightness.
AEFX.radialGlow = function (comp, name, color, cx, cy, radius, soften) {
  var fill = comp.layers.addSolid(color, name, comp.width, comp.height, 1);
  var matte = comp.layers.addSolid([1, 1, 1], name + "_matte", comp.width, comp.height, 1);
  var r = AEFX.fx(matte, "ADBE Ramp");
  r.property("ADBE Ramp-0001").setValue([comp.width / 2, comp.height / 2]);
  r.property("ADBE Ramp-0002").setValue([1, 1, 1, 1]);
  r.property("ADBE Ramp-0003").setValue([comp.width / 2 + radius, comp.height / 2]);
  r.property("ADBE Ramp-0004").setValue([0, 0, 0, 1]);
  r.property("ADBE Ramp-0005").setValue(2);
  if (soften) AEFX.fx(matte, "ADBE Gaussian Blur 2").property("Blurriness").setValue(soften);
  matte.position.setValue([cx, cy]);       // the solid's centre is the ramp's centre, so scaling pivots on it
  fill.moveAfter(matte);
  fill.setTrackMatte(matte, TrackMatteType.LUMA);
  return { fill: fill, matte: matte };
};
AEFX.done = function (comp, extra) {
  var s = '{"comp":"' + comp.name + '","width":' + comp.width + ',"height":' + comp.height + ',"fps":' + comp.frameRate +
          ',"frames":' + Math.round(comp.duration * comp.frameRate);
  if (extra) s += "," + extra;
  return s + "}";
};
