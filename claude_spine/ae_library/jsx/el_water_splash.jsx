// el_water_splash: realistic water crown splash, 512x512, 1.1 s one-shot. Impact point on the surface at (256, 430).
// Physics: on impact a thin cylindrical liquid sheet (the crown) shoots up and flares out, decelerating under
// gravity; surface tension gathers its rim into a torus that breaks into fingers (Rayleigh-Plateau), each finger
// tip beading into a droplet that flies off on a parabola (gravity 1900 px/s^2, light drag); the crown then
// collapses (accelerating down) while the Worthington jet rises from the centre and pinches off a drop high above;
// ripple rings run out on the perspective-flattened surface, fast first, slowing.
// Look: CLEAR water. The sheet is a faint blue refraction tint with a real splash photo (water_02) keyed to its
// bright streaks only, Fresnel-bright side edges, white specular streaks and rim, beads with bevel speculars.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, D = 1.1, CX = 256, SY = 430, F = 0.04, G = 1900;
  EL.purge("el_water_splash_v");
  var tag = "el_water_splash_v" + V, rnd = FX.rng(4242 + V);
  var TINT = FX.rgb("8CCBF0"), DEEP = FX.rgb("1C5E8E"), PALE = FX.rgb("EAF8FF"), SPEC = [1, 1, 1], CAV = FX.rgb("2A6C9A");
  var CH = 250, LIP = 92, BASE = 50;                  // crown height, lip half-width, base half-width (precomp px)

  // ---------- clear-water material over a closed smooth silhouette `pts` (sharp corners where sharp[i])
  function water(comp, nm, pts, sharp, pos, o) {
    o = o || {};
    function shp(suffix, fill, stroke, sw) { var l = EL.smoothPoly(comp, nm + suffix, pts, sharp, fill, stroke, sw); l.position.setValue(pos); return l; }
    var body = shp("_tint", TINT); body.opacity.setValue(o.tint || 13);
    var dark = FX.ramp(comp, nm + "_depth", pos[0], pos[1], 0, [0.12, 0.36, 0.6, 1], [0.6, 0.85, 1, 1], BlendingMode.NORMAL, true, [pos[0], pos[1] - (o.h || 250)]);
    dark.layer.opacity.setValue(o.depth || 16);
    var dm = shp("_depth_matte", [1, 1, 1]); dm.moveBefore(dark.layer); dark.layer.setTrackMatte(dm, TrackMatteType.ALPHA);
    var tex = EL.tex(comp, EL.R + "water_02.png", nm + "_streaks", { anchor: o.anchor || [640, 330] });
    tex.position.setValue(o.texPos || pos); tex.scale.setValue(o.texScale || [26, 40]);
    if (o.texRot) tex.rotation.setValue(o.texRot);
    RE.tint(tex, SPEC, DEEP);
    EL.extract(tex, 140);                             // only the bright liquid streaks; the rest stays clear
    var mt = shp("_matte", [1, 1, 1]); mt.moveBefore(tex);
    tex.setTrackMatte(mt, TrackMatteType.ALPHA);
    tex.opacity.setValue(o.texOp || 75);
    // Fresnel: a wide soft bright band just INSIDE the outline (the sheet seen edge-on), then a thin crisp edge
    var fr = shp("_fresnel", null, PALE, o.fresW || 12); FX.blur(fr, 5); fr.opacity.setValue(65);
    var fm = shp("_fresnel_matte", [1, 1, 1]); fm.moveBefore(fr); fr.setTrackMatte(fm, TrackMatteType.ALPHA);
    var edge = shp("_edge", null, PALE, o.edgeW || 1.6); FX.blur(edge, 0.6); edge.opacity.setValue(80);
    return body;
  }

  // ---------- crown precomp (impact at 256, 440 inside it): a smooth tulip-shaped sheet, irregular rim fingers
  var cr = EL.comp(tag + "_crown", 512, 512, D);
  var PX = 256, PY = 440;
  var rim = [], rimSharp = [], tips = [], NS = 17;
  for (var q = 0; q <= NS; q++) {
    var u = q / NS, xx = -LIP + 2 * LIP * u, sag = 10 * Math.sin(u * Math.PI);
    if (q % 2) { rim.push([xx + (rnd() - 0.5) * 6, -CH + 6 + rnd() * 14 + sag]); rimSharp.push(false); }
    else { var tp = [xx + (rnd() - 0.5) * 8 + (xx / LIP) * 14, -CH - (8 + rnd() * 44) + sag]; rim.push(tp); rimSharp.push(true); tips.push(tp); }
  }
  // flanks: rise from a wide base, pinch a little, then flare out to the lip (tulip)
  var left = [[-BASE - 6, 6], [-BASE + 2, -CH * 0.3], [-BASE - 10, -CH * 0.62], [-LIP + 4, -CH * 0.9]];
  var right = [[LIP - 4, -CH * 0.9], [BASE + 10, -CH * 0.62], [BASE - 2, -CH * 0.3], [BASE + 6, 6]];
  var wall = left.concat(rim).concat(right).concat([[0, 14]]);
  var wsharp = [true, false, false, false].concat(rimSharp).concat([false, false, false, true]).concat([false]);
  var cav = FX.shape(cr, "cavity");
  FX.group(cav, "ellipse", { size: [2 * LIP - 16, 30], fill: CAV });
  cav.position.setValue([PX, PY - CH + 6]); cav.opacity.setValue(35); FX.blur(cav, 3);
  water(cr, "wall", wall, wsharp, [PX, PY], { texPos: [PX, PY - CH * 0.5], texScale: [24, 44], h: CH });
  // specular streaks running up the sheet (it is stretched vertically), curving with the flare
  for (var st = 0; st < 5; st++) {
    var sx = (st - 2) * 17 + (rnd() - 0.5) * 6, k0 = 0.12 + rnd() * 0.2, k1 = 0.72 + rnd() * 0.18;   // stays inside the flanks
    var ss = FX.shape(cr, "spec_streak" + st);
    FX.group(ss, "path", { points: [[sx, -CH * k0], [sx * 1.25, -CH * (k0 + k1) / 2], [sx * 1.75, -CH * k1]], stroke: SPEC, width: 1.6 + rnd() * 1.4, taper: [80, 80],
                           inT: [[0, 0], [0, CH * 0.12], [0, 0]], outT: [[0, 0], [0, -CH * 0.12], [0, 0]] });
    ss.position.setValue([PX, PY]); FX.blur(ss, 0.7); ss.opacity.setValue(45 + rnd() * 35);
  }
  for (var b = 0; b < tips.length; b++) {
    var bs = 6 + rnd() * 5;
    var bd = EL.dot(cr, "bead" + b, bs, bs * 1.2, TINT);
    bd.layer.position.setValue([PX + tips[b][0], PY + tips[b][1] - 1]);
    EL.bevel(bd.layer, bs * 0.35, -50, 1.0, SPEC);
    var sp = EL.dot(cr, "bead_spec" + b, bs * 0.32, bs * 0.32, SPEC);
    sp.layer.position.setValue([PX + tips[b][0] - bs * 0.2, PY + tips[b][1] - bs * 0.3]);
  }
  var crAdj = FX.adj(cr, "liquid_wobble"); EL.turb(crAdj, 9, 36, D, 2, false, 2);

  // ---------- jet precomp: tall tapered column, clear water, pinching at the top
  var jt = EL.comp(tag + "_jet", 512, 512, D);
  var jpts = [[-24, 6], [-12, -60], [-7, -150], [-5, -230], [-10, -262], [0, -284], [10, -262], [5, -230], [7, -150], [12, -60], [24, 6]];
  var jsh = []; for (var ji = 0; ji < jpts.length; ji++) jsh.push(ji === 0 || ji === jpts.length - 1 || ji === 5);
  water(jt, "jet", jpts, jsh, [256, 440], { texPos: [256, 300], texScale: [16, 50], texRot: 90, tint: 24, fresW: 7, h: 284 });
  var jsp = FX.shape(jt, "jet_spec");
  FX.group(jsp, "path", { points: [[-6, -20], [-3, -140], [-4, -250]], stroke: SPEC, width: 3, taper: [60, 60] });
  jsp.position.setValue([256, 440]); FX.blur(jsp, 0.8); jsp.opacity.setValue(85);
  var jw = FX.adj(jt, "jet_wobble"); EL.turb(jw, 5, 14, D, 3, false, 2);

  // ================= main
  var c = EL.comp(tag + "_body", W, H, D);

  // 1. faint mist (pale blue, very light: water, not white spray)
  var puffs = [];                                     // no mist: clear water, not white spray
  for (var m = 0; m < puffs.length; m++) {
    var tm = F * (3 + m * 2), am = Math.PI + (m / (puffs.length - 1)) * Math.PI;
    var mp = EL.tex(c, EL.KS + "White puff/" + puffs[m] + ".png", "mist" + m);
    RE.tint(mp, FX.rgb("CFEBFA"), FX.rgb("6FA8CC")); FX.blur(mp, 8);
    EL.ball(mp, [CX + Math.cos(am) * 40, SY - 40 + Math.sin(am) * 20], [Math.cos(am) * 120, -40], -40, 2.4, tm);
    var ms = 28 + rnd() * 8;
    FX.keys(mp.scale, [[tm, [ms * 0.5, ms * 0.4]], [D, [ms * 1.5, ms]]], "out");
    FX.keys(mp.opacity, [[tm - 0.001, 0], [tm + 0.15, 14], [D - 0.3, 9], [D, 0]], false);
  }
  // 2. ripple rings on the surface (perspective-squashed): bright crest over a darker trough
  for (var r = 0; r < 4; r++) {
    var tr0 = F * (1 + r * 3.2), rp = FX.shape(c, "ripple" + r);
    FX.group(rp, "ellipse", { size: [40, 40], stroke: PALE, width: 5 });
    FX.group(rp, "ellipse", { size: [34, 34], stroke: FX.rgb("2C7AAE"), width: 6 });
    var gp = function (i) { var cc = rp.property("ADBE Root Vectors Group").property(i).property("ADBE Vectors Group");
      return { size: cc.property("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size"),
               strokeW: cc.property("ADBE Vector Graphic - Stroke").property("ADBE Vector Stroke Width") }; };
    var e1 = gp(1), e2 = gp(2);
    rp.position.setValue([CX, SY + 6]); rp.scale.setValue([100, 24]);
    var R1 = 300 + r * 80;
    FX.keys(e1.size, [[tr0, [60, 60]], [D, [R1, R1]]], "out");
    FX.keys(e2.size, [[tr0, [50, 50]], [D, [R1 - 18, R1 - 18]]], "out");
    FX.keys(e1.strokeW, [[tr0, 7], [D, 2]], false); FX.keys(e2.strokeW, [[tr0, 8], [D, 2]], false);
    FX.keys(rp.opacity, [[tr0 - 0.001, 0], [tr0 + 0.05, 80 - r * 12], [D, 0]], false);
    FX.blur(rp, 1.2);
  }
  // 3. crown: shoots up decelerating (thin), flares, then collapses accelerating down and spreading
  var cl = EL.layerOf(c, cr, "crown");
  cl.anchorPoint.setValue([256, 444]); cl.position.setValue([CX, SY + 4]);
  var CK = [[0, [55, 0]], [F * 2, [62, 45]], [F * 5, [80, 88]], [F * 8, [92, 100]], [F * 11, [100, 98]], [F * 14, [110, 80]], [F * 18, [122, 42]], [F * 22, [130, 8]]];
  FX.keys(cl.scale, CK, false);
  FX.keys(cl.opacity, [[0, 0], [F * 1, 100], [F * 16, 100], [F * 22, 0]], false);
  // 4. droplets: each finger tip lets go of its bead around the crown's peak and flies outward on a parabola
  function sAt(t) {                                   // crown scale at time t (linear between keys, like the layer)
    for (var i = 0; i < CK.length - 1; i++) if (t <= CK[i + 1][0]) { var a = (t - CK[i][0]) / (CK[i + 1][0] - CK[i][0]);
      return [CK[i][1][0] + (CK[i + 1][1][0] - CK[i][1][0]) * a, CK[i][1][1] + (CK[i + 1][1][1] - CK[i][1][1]) * a]; }
    return CK[CK.length - 1][1];
  }
  var nd = 0;
  for (var pass = 0; pass < 3; pass++) {
    for (var ti = 0; ti < tips.length; ti++) {
      var tk = F * (6 + pass * 2.5 + rnd() * 2), sc = sAt(tk), tip = tips[ti];
      var p0 = [CX + tip[0] * sc[0] / 100, SY + 4 + (tip[1] - 4) * sc[1] / 100];
      var side = tip[0] / LIP, spd = 220 + rnd() * 300;
      var vx = side * (90 + rnd() * 200) + (rnd() - 0.5) * 40, vy = -(spd * (0.7 + 0.3 * (1 - Math.abs(side))));
      var sz = pass === 0 ? 6 + rnd() * 4 : 3 + rnd() * 4;
      var dk = EL.dot(c, "drop" + nd, sz, sz * 1.15, TINT);
      dk.layer.opacity.setValue(85);
      EL.bevel(dk.layer, Math.max(1, sz * 0.4), -50, 1.0, SPEC);
      dk.layer.motionBlur = true;
      EL.ball(dk.layer, p0, [vx, vy], G, 0.4, tk);
      var lifeK = 0.5 + rnd() * 0.3;
      FX.keys(dk.layer.opacity, [[tk - 0.001, 0], [tk, 95], [Math.min(D, tk + lifeK) - 0.08, 90], [Math.min(D, tk + lifeK), 0]], false);
      nd++;
    }
  }
  // 5. Worthington jet: rises from the centre as the crown falls; a drop pinches off high above
  var jl = EL.layerOf(c, jt, "jet");
  jl.anchorPoint.setValue([256, 440]); jl.position.setValue([CX, SY + 2]);
  FX.keys(jl.scale, [[F * 9, [80, 0]], [F * 12, [100, 75]], [F * 15, [92, 100]], [F * 19, [100, 60]], [F * 25, [120, 0]]], "both");
  FX.keys(jl.opacity, [[F * 9, 0], [F * 10, 100], [F * 23, 100], [F * 25, 0]], false);
  var dp = EL.dot(c, "pinch_drop", 13, 16, TINT);
  EL.bevel(dp.layer, 4.5, -50, 1.0, SPEC); dp.layer.motionBlur = true;
  var dps = EL.dot(c, "pinch_drop_spec", 4, 4, SPEC); dps.layer.parent = dp.layer; dps.layer.position.setValue([-3, -4]);
  dp.layer.position.expression = "var t0 = " + F * 15 + ", t = Math.max(0, time - t0); [" + CX + ", " + (SY - 288) + " - 330 * t + 0.5 * " + G + " * t * t]";
  FX.keys(dp.layer.opacity, [[F * 14.9, 0], [F * 15.1, 100], [F * 26, 100], [F * 27, 0]], false);
  // 6. specular sparkle on the crown at its peak (sun glint), small
  var gl = EL.tex(c, EL.K + "star_06.png", "glint", { blend: BlendingMode.ADD, pos: [CX - 60, SY - 200] });
  RE.fill(gl, SPEC);
  FX.keys(gl.scale, [[F * 6, [0, 0]], [F * 8, [14, 14]], [F * 11, [0, 0]]], false);
  var main = EL.edgeSafe(c, tag, 24, 30);
  return EL.done(main, "normal", [CX, SY], false);
}
