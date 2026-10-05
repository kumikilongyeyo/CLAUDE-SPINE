/*TEMPLATE {"name":"glow_pulse","doc":"Soft round glow that swells and fades, with a hot core. Behind a symbol, or on a win.","params":{"size":512,"duration":1.0,"fps":24,"color":"FFB020","core_color":"FFF2C0","radius":0.5,"pulses":1,"peak":1.0,"soften":0.04,"intensity":1.0}} */
var W = P.size, comp = AEFX.comp(P.comp || "glow_pulse", W, W, P.fps, P.duration);
var D = P.duration, n = P.pulses, I = Math.min(1.2, P.intensity);
function pulse(name, color, rad, op) {
  var g = AEFX.radialGlow(comp, name, AEFX.rgb(color), W / 2, W / 2, W * P.radius * rad, W * P.soften);
  var sc = [[0, [55, 55]]], oc = [[0, 0]];
  for (var i = 0; i < n; i++) {
    var t1 = D * (i + 0.42) / n, t2 = D * (i + 1) / n;
    sc.push([t1, [P.peak * 100, P.peak * 100]]); oc.push([t1, op * 100 * I]);
    if (i < n - 1) { sc.push([t2, [78, 78]]); oc.push([t2, op * 50 * I]); }
  }
  sc.push([D, [P.peak * 130, P.peak * 130]]); oc.push([D, 0]);
  AEFX.keys(g.matte.scale, sc, true); AEFX.keys(g.fill.opacity, oc, true);
}
pulse("halo", P.color, 1.0, 0.6);
pulse("body", P.color, 0.62, 0.95);
pulse("core", P.core_color, 0.3, 1.0);
return AEFX.done(comp);
