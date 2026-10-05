/*TEMPLATE {"name":"splash","doc":"Water splash: a crown of droplets thrown up and falling back, flattened ripple rings on the surface and a soft mist puff. Drop, pour, landing in liquid.","params":{"size":512,"duration":1.1,"fps":24,"n":30,"color":"7FD0FF","color2":"EAFBFF","particle":20,"speed":880,"spread":78,"gravity":2300,"life":0.8,"ripples":3,"mist":0.5,"seed":11,"surface":0.8,"glow":0.5}} */
var W = P.size, D = P.duration, comp = AEFX.comp(P.comp || "splash", W, W, P.fps, D);
var col = AEFX.rgb(P.color), pale = AEFX.rgb(P.color2), sy = W * P.surface;
// mist puff behind everything
if (P.mist > 0) {
  var m = AEFX.radialGlow(comp, "mist", pale, W / 2, sy - W * 0.08, W * 0.3, W * 0.05);
  AEFX.keys(m.matte.scale, [[0, [40, 30]], [D * 0.5, [100, 70]], [D, [140, 90]]], true);
  AEFX.keys(m.fill.opacity, [[0, 0], [D * 0.12, 55 * P.mist], [D, 0]], true);
}
// droplets: a fan thrown up from the point of impact
AEFX.burst(comp, { n: P.n, cx: W / 2, cy: sy, speed: P.speed, speed_var: 0.45, angle: 90, spread: P.spread, gravity: P.gravity,
  life: P.life, life_var: 0.3, size: P.particle, size_var: 0.6, stretch: 1.0, color: col, color2: pale, shape: "drop",
  seed: P.seed, delay_spread: 0.06, glow: P.glow });
// ripple rings lying on the surface (squashed circles)
for (var i = 0; i < P.ripples; i++) {
  var r = AEFX.shape(comp, "ripple" + i), t0 = D * 0.08 * i;
  var e = AEFX.ellipse(r, W * 0.1, null, i % 2 ? pale : col, W * 0.012);
  r.position.setValue([W / 2, sy]);
  r.scale.setValue([100, 28]);
  AEFX.keys(e.size, [[t0, [W * 0.06, W * 0.06]], [D * 0.95, [W * (0.7 + 0.1 * i), W * (0.7 + 0.1 * i)]]], true);
  AEFX.keys(r.opacity, [[t0, 0], [t0 + D * 0.06, 100], [D * 0.9, 0]], true);
  AEFX.keys(e.stroke, [[t0, W * 0.02], [D * 0.95, W * 0.006]], true);
}
return AEFX.done(comp, '"mode":"alpha"');
