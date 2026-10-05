/*TEMPLATE {"name":"burst","doc":"Particles thrown out along true parabolas: sparks, coins-as-dots, confetti, embers. Baked keyframes (no particle plug-in), so it renders the same on every machine.","params":{"size":512,"duration":1.0,"fps":24,"n":28,"color":"FFC040","color2":"FFF4C0","particle":14,"particle_var":0.5,"speed":420,"speed_var":0.4,"angle":90,"spread":360,"gravity":700,"life":0.8,"life_var":0.3,"stretch":1.4,"shape":"spark","delay_spread":0.15,"glow":1.2,"seed":5,"center_x":0.5,"center_y":0.55}} */
var W = P.size, D = P.duration, comp = AEFX.comp(P.comp || "burst", W, W, P.fps, D);
AEFX.burst(comp, { n: P.n, cx: W * P.center_x, cy: W * P.center_y, speed: P.speed, speed_var: P.speed_var, angle: P.angle, spread: P.spread,
  gravity: P.gravity, life: P.life, life_var: P.life_var, size: P.particle, size_var: P.particle_var, stretch: P.stretch,
  color: AEFX.rgb(P.color), color2: AEFX.rgb(P.color2), shape: P.shape, seed: P.seed, delay_spread: P.delay_spread, glow: P.glow });
return AEFX.done(comp, '"mode":"alpha"');
