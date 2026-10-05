/*TEMPLATE {"name":"saber","doc":"A native port of Video Copilot's Saber look (energy beams, lightsabers, lasers, neon tubes, electric and fire outlines, haze) built from AE's own effects only, so it renders with aerender on any machine with no plug-in. A hot core line follows a line, a polyline, a circle, a rounded rectangle or the outline of a text; a stack of `glow_layers` blurred copies at doubling radii, weighted so the brightness falls off as (core / distance)^bias (bias 1 = the realistic 1/r falloff of a glowing tube; lower = a wider haze), gives Saber's glow falloff; turbulent distortion with a cycled evolution tears the core (electric, fire, energy), the glow flickers on integer cycles, and the beam can draw on and off (Saber's start / end offset). `preset` picks one of the presets below; any style parameter you pass wins over the preset (style parameters default to null = take the preset). Renders on black: additive (mode=\"additive\"). Loops exactly when draw is none. Pair with fx_recipe recipe=saber (its ae_hint carries these parameters).","params":{"width":768,"height":256,"duration":2.0,"fps":24,"preset":"default","core":"line","start":null,"end":null,"points":null,"closed":false,"radius":null,"rect":null,"text":"SABER","font":"Arial-BoldMT","font_size":120,"color":null,"core_color":null,"core_size":null,"intensity":null,"spread":null,"bias":null,"glow_layers":6,"distortion":null,"noise_size":null,"noise_speed":null,"flicker":null,"haze":null,"draw":"none","draw_time":0.6,"seed":7}} */
var PRESETS = /*PRESETS*/{
 "default":  {"color": "0A64FF", "core_color": "F4FAFF", "core_size": 6.0, "intensity": 1.0, "spread": 1.0, "bias": 1.0, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 2, "flicker": 0.04, "haze": 0.0},
 "red":      {"color": "FF1A12", "core_color": "FFF0EC", "core_size": 6.0, "intensity": 1.0, "spread": 1.0, "bias": 1.0, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 2, "flicker": 0.05, "haze": 0.0},
 "green":    {"color": "22FF44", "core_color": "F0FFF2", "core_size": 6.0, "intensity": 1.0, "spread": 1.0, "bias": 1.0, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 2, "flicker": 0.04, "haze": 0.0},
 "purple":   {"color": "A230FF", "core_color": "FBF0FF", "core_size": 6.0, "intensity": 1.0, "spread": 1.0, "bias": 1.0, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 2, "flicker": 0.04, "haze": 0.0},
 "gold":     {"color": "FFB21F", "core_color": "FFF8E0", "core_size": 5.0, "intensity": 1.0, "spread": 1.0, "bias": 0.95, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 2, "flicker": 0.03, "haze": 0.1},
 "neon":     {"color": "FF2E9A", "core_color": "FFE2F1", "core_size": 5.0, "intensity": 0.9, "spread": 0.8, "bias": 1.15, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 1, "flicker": 0.02, "haze": 0.0},
 "laser":    {"color": "FF2010", "core_color": "FFF4F0", "core_size": 2.5, "intensity": 1.2, "spread": 0.6, "bias": 1.3, "distortion": 0.0, "noise_size": 40.0, "noise_speed": 4, "flicker": 0.08, "haze": 0.0},
 "electric": {"color": "6FB8FF", "core_color": "FFFFFF", "core_size": 3.0, "intensity": 1.1, "spread": 0.9, "bias": 0.95, "distortion": 18.0, "noise_size": 30.0, "noise_speed": 6, "flicker": 0.35, "haze": 0.0},
 "fire":     {"color": "FF6A10", "core_color": "FFE7A0", "core_size": 7.0, "intensity": 1.0, "spread": 1.2, "bias": 0.85, "distortion": 14.0, "noise_size": 60.0, "noise_speed": 2, "flicker": 0.15, "haze": 0.5},
 "energy":   {"color": "19E6FF", "core_color": "E8FFFF", "core_size": 6.0, "intensity": 1.1, "spread": 1.0, "bias": 0.95, "distortion": 6.0, "noise_size": 90.0, "noise_speed": 3, "flicker": 0.1, "haze": 0.3},
 "plasma":   {"color": "C040FF", "core_color": "FFE8FF", "core_size": 5.0, "intensity": 1.1, "spread": 1.1, "bias": 0.9, "distortion": 10.0, "noise_size": 50.0, "noise_speed": 4, "flicker": 0.2, "haze": 0.4},
 "haze":     {"color": "FFB060", "core_color": "FFF2DC", "core_size": 4.0, "intensity": 0.7, "spread": 1.6, "bias": 0.7, "distortion": 4.0, "noise_size": 120.0, "noise_speed": 1, "flicker": 0.06, "haze": 1.0}
}/*END*/;
if (!PRESETS[P.preset]) throw new Error("preset must be one of: " + (function () { var a = []; for (var k in PRESETS) a.push(k); return a.join(", "); })());
var S = PRESETS[P.preset];
function pick(k) { return (P[k] === null || P[k] === undefined) ? S[k] : P[k]; }
var W = P.width, H = P.height, D = P.duration, name = P.comp || ("saber_" + P.preset);
var col = AEFX.rgb(pick("color")), hot = AEFX.rgb(pick("core_color"));
var CORE = pick("core_size"), I = pick("intensity"), SPREAD = pick("spread"), BIAS = pick("bias");
var DIST = pick("distortion"), NSIZE = pick("noise_size"), NSPEED = Math.max(1, Math.round(pick("noise_speed")));
var FLICK = pick("flicker"), HAZE = pick("haze");
var N = Math.max(1, Math.round(P.glow_layers));
if (!(CORE > 0) || !(SPREAD > 0) || !(BIAS > 0) || !(I >= 0)) throw new Error("core_size, spread and bias must be > 0, intensity >= 0");
if ({"line": 1, "points": 1, "circle": 1, "rect": 1, "text": 1}[P.core] !== 1) throw new Error("core must be line | points | circle | rect | text");
if ({"none": 1, "on": 1, "off": 1, "on_off": 1}[P.draw] !== 1) throw new Error("draw must be none | on | off | on_off");

// ---- the core: one white-hot shape (or text outline) in its own comp; every glow layer samples it, so the glow
// follows the distortion and the draw-on exactly
var core = AEFX.comp(name + "_core", W, H, P.fps, D);
var src;
if (P.core === "text") {
  src = core.layers.addText(String(P.text));
  var st = src.property("ADBE Text Properties").property("ADBE Text Document");
  var td = st.value;
  td.fontSize = P.font_size; td.font = P.font;
  td.applyFill = false; td.applyStroke = true; td.strokeColor = hot; td.strokeWidth = CORE;
  td.justification = ParagraphJustification.CENTER_JUSTIFY;
  st.setValue(td);
  src.position.setValue([W / 2, H / 2 + P.font_size * 0.35]);
  if (P.draw !== "none") {                                         // text has no trim paths: wipe it on left to right
    var wp = AEFX.fx(src, "ADBE Linear Wipe");
    AEFX.set(wp, "Wipe Angle", 270); AEFX.set(wp, "Feather", P.font_size * 0.4);
    var tc = AEFX.find(wp, "Transition Completion"), T0 = P.draw_time;
    var wk = [];
    if (P.draw === "on" || P.draw === "on_off") wk = wk.concat([[0, 100], [T0, 0]]); else wk.push([0, 0]);
    if (P.draw === "off" || P.draw === "on_off") wk = wk.concat([[D - T0, 0], [D, 100]]);
    AEFX.keys(tc, wk, true);
  }
} else {
  src = AEFX.shape(core, "core");
  var grp = src.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
  var cv = grp.property("ADBE Vectors Group");
  var kind = P.core === "circle" ? "ADBE Vector Shape - Ellipse" : (P.core === "rect" ? "ADBE Vector Shape - Rect" : "ADBE Vector Shape - Group");
  cv.addProperty(kind);
  cv.addProperty("ADBE Vector Graphic - Stroke");
  cv.addProperty("ADBE Vector Filter - Trim");
  var cc = src.property("ADBE Root Vectors Group").property(1).property("ADBE Vectors Group");
  if (P.core === "circle") {
    var R = P.radius || Math.min(W, H) * 0.32;
    cc.property(kind).property("ADBE Vector Ellipse Size").setValue([2 * R, 2 * R]);
  } else if (P.core === "rect") {
    var rc = P.rect || [W * 0.7, H * 0.6, Math.min(W, H) * 0.08];
    cc.property(kind).property("ADBE Vector Rect Size").setValue([rc[0], rc[1]]);
    cc.property(kind).property("ADBE Vector Rect Roundness").setValue(rc[2] || 0);
  } else {
    var pts = P.core === "points" ? P.points : [P.start || [W * 0.1, H / 2], P.end || [W * 0.9, H / 2]];
    if (!pts || pts.length < 2) throw new Error("core=points needs points=[[x, y], ...] (2 or more, comp pixels)");
    var sh = new Shape();
    var v = [];
    for (var i = 0; i < pts.length; i++) v.push([pts[i][0] - W / 2, pts[i][1] - H / 2]);
    sh.vertices = v; sh.closed = !!P.closed;
    cc.property(kind).property("ADBE Vector Shape").setValue(sh);
  }
  src.position.setValue([W / 2, H / 2]);
  var stroke = cc.property("ADBE Vector Graphic - Stroke");
  stroke.property("ADBE Vector Stroke Color").setValue(hot);
  stroke.property("ADBE Vector Stroke Width").setValue(CORE);
  stroke.property("ADBE Vector Stroke Line Cap").setValue(2);      // round caps: a beam has no square ends
  stroke.property("ADBE Vector Stroke Line Join").setValue(2);
  var trim = cc.property("ADBE Vector Filter - Trim"), T1 = P.draw_time;
  var tE = trim.property("ADBE Vector Trim End"), tS = trim.property("ADBE Vector Trim Start");
  if (P.draw === "on" || P.draw === "on_off") AEFX.keys(tE, [[0, 0], [T1, 100]], true);
  if (P.draw === "off" || P.draw === "on_off") AEFX.keys(tS, [[D - T1, 0], [D, 100]], true);
}
if (DIST > 0) {                                                     // Saber's core distortion: cycled, so it loops
  var tdz = AEFX.fx(src, "ADBE Turbulent Displace");
  AEFX.set(tdz, "Amount", DIST); AEFX.set(tdz, "Size", NSIZE); AEFX.set(tdz, "Complexity", 4);
  AEFX.set(tdz, "Random Seed", P.seed);
  var ev = AEFX.find(tdz, "Evolution");
  ev.setValueAtTime(0, 0); ev.setValueAtTime(D, 360 * NSPEED);
  AEFX.set(tdz, "Cycle Evolution", 1); AEFX.set(tdz, "Cycle (in Revolutions)", NSPEED);
}

// ---- the glow: N blurred copies at radii r_k = 1.6 core spread 2^k. A blurred line of width w peaks at ~ w/(r sqrt pi),
// so to make the PEAKS fall as (r0/r_k)^bias the opacities are o_k ~ (r_k/r0)^(1 - bias) (capped at 100): with bias 1
// every octave carries the same light and the sum falls off as 1/distance, like a real glowing tube.
var comp = AEFX.comp(name, W, H, P.fps, D);
var r0 = 1.6 * CORE * SPREAD, maxR = Math.max(W, H) * 0.6;
var flick = function (a, b, p1, p2) {
  return "value * (1 - " + FLICK + " * (0.5 + 0.5 * Math.sin(2 * Math.PI * " + a + " * time / " + D + " + " + p1 + "))" +
         " * (0.5 + 0.5 * Math.sin(2 * Math.PI * " + b + " * time / " + D + " + " + p2 + ")))";
};
for (var k = N - 1; k >= 0; k--) {                                  // widest first (back), core last (front)
  var rk = Math.min(maxR, r0 * Math.pow(2, k));
  var gl = comp.layers.add(core); gl.name = "glow_" + k;
  var fill = AEFX.fx(gl, "ADBE Fill");
  fill.property("Color").setValue(col);
  var gb = AEFX.fx(gl, "ADBE Gaussian Blur 2");
  AEFX.set(gb, "Blurriness", rk);
  AEFX.set(gb, "Repeat Edge Pixels", 0);
  if (HAZE > 0 && k >= N - 2) {                                     // haze: the outer glows churn slowly
    var hz = AEFX.fx(gl, "ADBE Turbulent Displace");
    AEFX.set(hz, "Amount", 25 * HAZE); AEFX.set(hz, "Size", rk * 1.5); AEFX.set(hz, "Random Seed", P.seed + 20 + k);
    var hev = AEFX.find(hz, "Evolution"); hev.setValueAtTime(0, 0); hev.setValueAtTime(D, 360);
    AEFX.set(hz, "Cycle Evolution", 1); AEFX.set(hz, "Cycle (in Revolutions)", 1);
  }
  var ok_ = Math.min(100, 100 * I * 0.9 * Math.pow(rk / r0, 1 - BIAS) * (1 + 0.35 * k));
  gl.opacity.setValue(ok_);
  if (FLICK > 0) gl.opacity.expression = flick(7, 13, 0.3 + k, 1.1 + 2 * k);
  gl.blendingMode = BlendingMode.ADD;
}
var top = comp.layers.add(core); top.name = "core";               // the core itself, tinted toward the glow at its rim
var tint = AEFX.fx(top, "ADBE Glo2");
tint.property("Glow Threshold").setValue(40); tint.property("Glow Radius").setValue(CORE * 1.2); tint.property("Glow Intensity").setValue(0.6 * I);
top.blendingMode = BlendingMode.ADD;
if (FLICK > 0) top.opacity.expression = flick(5, 11, 0.7, 2.3);
return AEFX.done(comp, '"mode":"additive","preset":"' + P.preset + '","seq_mode":"' + (P.draw === "none" ? "loop" : "once") + '"');
