/*TEMPLATE {"name":"metal_sparks","doc":"Realistic metal-on-metal impact sparks (a sword on a coin, a hammer on an anvil): one frame of CC Particle World births thrown out explosively, slowed by drag and pulled down by gravity, cooling white-hot -> orange -> red. The streaks are ADBE Echo (Maximum operator, sub-frame echoes) on the particle layer, which smears every spark along its own gravity-curved path WITHOUT dimming it (CC Force Motion Blur / a long-shutter average turned them invisible). Plus a few heavier, slower molten droplets and a tiny white-hot contact flash gone in ~5 frames (keep the big light native Spine). Light on black: mode=\"additive\", one-shot. Tuned at 30 fps / 512 px: rate is particles per birth frame (0.7 = a few dozen sparks; 30 is a solid white ball). velocity / gravity / drag / extra / life are CC Particle World units (they scale with the comp, so size changes nothing but resolution). droplets is the droplet birth rate as a fraction of rate (0 = none), flash the contact-flash strength (0 = none), echoes the streak length (number of 1/240 s echoes). center_x / center_y place the contact point (fractions of the comp, y down). In Spine: additive slot, one import and copies=[[x, y, start, scale, rotation], ...] for every other hit (escalating hits: scale 1 / 1.3 / 1.7).","params":{"size":512,"duration":0.8,"fps":30,"rate":0.7,"velocity":1.9,"gravity":1.6,"drag":1.3,"extra":1.6,"life":0.55,"hot":"FFF0C8","cool":"E8500C","droplets":0.25,"droplet_hot":"FFE6A0","droplet_cool":"B8280A","echoes":14,"glow":1.6,"flash":1.0,"seed":17,"center_x":0.5,"center_y":0.5}} */
var W = P.size, D = P.duration, F = P.fps, k = W / 512, name = P.comp || "metal_sparks";
var VIEW = 2 * Math.tan(22.5 * Math.PI / 180);     // CCPW's default camera (distance 1, FOV 45) sees this many units across
var cx = W * P.center_x, cy = W * P.center_y;

// CC Particle World keeps every property FLAT on the effect (Producer / Physics / Particle are only labels): set them by
// matchName. 0050 and 0062 are GROUPS with no value (setting them throws); 0055 / 0060 / 0061 turn the UI grid, horizon
// and axis box off.
function particleWorld(L, o) {
  var f = AEFX.fx(L, "CC Particle World");
  function S(id, v) { f.property("CC Particle World-" + id).setValue(v); }
  S("0055", 0); S("0060", 0); S("0061", 0);
  S("0005", o.life);                                         // longevity (s)
  S("0007", (P.center_x - 0.5) * VIEW); S("0008", (P.center_y - 0.5) * VIEW);
  S("0010", 0.004); S("0011", 0.004); S("0012", 0.004);      // producer radius: a point of contact
  S("0015", 1);                                              // animation 1 = Explosive
  S("0016", o.vel); S("0018", o.grav); S("0041", o.drag); S("0019", o.extra); S("0020", 360);
  S("0023", o.type);                                         // 1 = Line (velocity-aligned), 4 = Faded Sphere
  S("0024", o.size0); S("0025", o.size1); S("0026", o.sizeVar); S("0027", 100);
  S("0029", AEFX.rgb(o.c0)); S("0030", AEFX.rgb(o.c1));
  S("0104", o.seed);
  // the burst: births on frame 1, a quarter on frame 3, none from frame 4 (HOLD keys: no ramp between them)
  var br = f.property("CC Particle World-0004");
  br.setValuesAtTimes([0, 1 / F, 3 / F, 4 / F], [0, o.rate, o.rate * 0.25, 0]);
  for (var i = 1; i <= br.numKeys; i++) br.setInterpolationTypeAtKey(i, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
  return f;
}
function glow(L, radius, intensity) {
  var g = AEFX.fx(L, "ADBE Glo2");
  g.property("Glow Threshold").setValue(30); g.property("Glow Radius").setValue(radius * k); g.property("Glow Intensity").setValue(intensity);
}

var comp = AEFX.comp(name, W, W, F, D);
comp.motionBlur = true; comp.shutterAngle = 300; comp.shutterPhase = -150; comp.motionBlurSamplesPerFrame = 24;

// 03_SECONDARY: the spark streaks
var sp = comp.layers.addSolid([0, 0, 0], "03_SECONDARY_sparks", W, W, 1, D);
sp.motionBlur = true;
particleWorld(sp, {life: P.life, vel: P.velocity, grav: P.gravity, drag: P.drag, extra: P.extra, type: 1, size0: 0.03,
                   size1: 0.008, sizeVar: 80, c0: P.hot, c1: P.cool, seed: P.seed, rate: P.rate});
// streaks: real sparks read as light trails smeared along their curved path; Echo with the Maximum operator stacks
// earlier sub-frame positions without dimming them
if (P.echoes > 0) {
  var ec = AEFX.fx(sp, "ADBE Echo");
  AEFX.set(ec, "Echo Time (seconds)", -1 / 240); AEFX.set(ec, "Number Of Echoes", Math.round(P.echoes));
  AEFX.set(ec, "Starting Intensity", 1); AEFX.set(ec, "Decay", 0.86); AEFX.set(ec, "Echo Operator", 2);   // 2 = Maximum
}
if (P.glow > 0) glow(sp, 10, P.glow);

// 03_SECONDARY: molten droplets, fewer, heavier, slower, glowing
if (P.droplets > 0) {
  var dr = comp.layers.addSolid([0, 0, 0], "03_SECONDARY_droplets", W, W, 1, D);
  dr.motionBlur = true; dr.blendingMode = BlendingMode.ADD;
  // tuned values scaled by the spark ones (defaults give exactly the tuned pair: life 0.8, vel 0.75, grav 1.4, drag 1.0,
  // extra 0.8, seed 17 -> 5)
  particleWorld(dr, {life: P.life * 0.8 / 0.55, vel: P.velocity * 0.75 / 1.9, grav: P.gravity * 1.4 / 1.6,
                     drag: P.drag * 1.0 / 1.3, extra: P.extra * 0.5, type: 4, size0: 0.022, size1: 0.006, sizeVar: 60,
                     c0: P.droplet_hot, c1: P.droplet_cool, seed: Math.abs(P.seed - 12), rate: P.rate * P.droplets});
  if (P.glow > 0) glow(dr, 14, P.glow * 0.75);
}

// 02_CORE: the contact flash, white-hot and tiny, gone in 5 frames: a solid with a radial ramp as its own luma
if (P.flash > 0) {
  var fs = Math.round(150 * k), hot = AEFX.rgb(P.hot);
  var core = comp.layers.addSolid(hot, "02_CORE_contact", fs, fs, 1, D);
  var rp = AEFX.fx(core, "ADBE Ramp");
  AEFX.set(rp, "ADBE Ramp-0005", 2);                                        // radial
  AEFX.set(rp, "ADBE Ramp-0001", [fs / 2, fs / 2]); AEFX.set(rp, "ADBE Ramp-0002", [1, 1, 1, 1]);
  AEFX.set(rp, "ADBE Ramp-0003", [fs / 2, 0]); AEFX.set(rp, "ADBE Ramp-0004", [0, 0, 0, 1]);
  var tn = AEFX.fx(core, "ADBE Tint");
  AEFX.set(tn, "Map Black To", [0, 0, 0]); AEFX.set(tn, "Map White To", hot);
  core.blendingMode = BlendingMode.ADD;
  core.position.setValue([cx, cy]);
  var fo = Math.min(100, 100 * P.flash);
  AEFX.keys(core.opacity, [[0, 0], [1 / F, fo], [2 / F, fo * 0.85], [6 / F, 0]], false);
  AEFX.keys(core.scale, [[0, [40, 40]], [1 / F, [100, 100]], [6 / F, [70, 70]]], false);
  core.moveToEnd();
}
return AEFX.done(comp, '"mode":"additive","seq_mode":"once"');
