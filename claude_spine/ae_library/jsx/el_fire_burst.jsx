// el_fire_burst: realistic fire explosion, 512x512, 1.2 s one-shot.
// Physics: a white-hot flash, the fireball expands fast and is braked by drag (exp ease), then RISES on buoyancy
// (accelerating), cools white -> yellow -> orange -> red while tongues of flame peel off its top and accelerate
// upward; embers fly out ballistic with drag (hot ones float, heavy ones fall); soot smoke billows behind and
// finally over the dying fire.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, D = 1.2, CX = 256, CY = 318, F = 0.04;
  EL.purge("el_fire_burst_v");
  var tag = "el_fire_burst_v" + V, rnd = FX.rng(1008 + V);
  var WHITE = FX.rgb("FFF9EC"), YEL = FX.rgb("FFD66A"), ORA = FX.rgb("FF7A18"), RED = FX.rgb("B02A08");
  var RISE = 560;                                   // buoyant acceleration of the hot gas, px/s^2 (up)
  var riseExpr = function (x, y, t0) { return "var t = Math.max(0, time - " + t0 + "); [" + x + ", " + y + " - 0.5 * " + RISE + " * t * t]"; };

  // ---------- fireball material precomp (centre 256,256): photo fireball + Kenney explosion cards + roiling heat
  var ball = EL.comp(tag + "_ball", 512, 512, D);
  var ph = EL.tex(ball, EL.R + "explosion_02.png", "photo_fireball", { pos: [256, 256], anchor: [930, 650] });
  EL.ell(ph, 930, 650, 520, 500, 230);
  FX.keys(ph.scale, [[F * 1, [5, 5]], [F * 3, [17, 17]], [F * 6, [24, 24]], [F * 12, [28, 28]], [D, [31, 31]]], "out");
  FX.keys(ph.rotation, [[0, -8], [D, 14]], false);
  // no Turbulent Displace on this 1920 px photo: under aerender multi-frame rendering it tore the ball into
  // horizontal hatching (frames 10-19); the roil overlay and the spinning cards carry the gas motion instead
  var cards = ["explosion00", "explosion03", "explosion04", "explosion06", "explosion08", "explosion02"];
  for (var i = 0; i < cards.length; i++) {
    var a = (i / cards.length) * Math.PI * 2 + rnd() * 0.6, rr = 34 + rnd() * 26;
    var c = EL.tex(ball, EL.KS + "Explosion/" + cards[i] + ".png", "kcard" + i, { blend: BlendingMode.SCREEN });
    FX.keys(c.position, [[F * 1, [256, 256]], [F * 4, [256 + Math.cos(a) * rr * 0.75, 256 + Math.sin(a) * rr * 0.75]], [D, [256 + Math.cos(a) * rr * 1.25, 256 + Math.sin(a) * rr * 1.25 - 10]]], "out");
    var s0 = 30 + rnd() * 12;
    FX.keys(c.scale, [[F * 1, [6, 6]], [F * 4, [s0, s0]], [D, [s0 * 1.35, s0 * 1.35]]], "out");
    EL.spin(c, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * (60 + rnd() * 60), 2, F);
    FX.keys(c.opacity, [[F * 1 - 0.001, 0], [F * 2, 60], [D, 60]], false);
  }
  // roiling detail: rising turbulent noise laid over the fireball only
  var roil = FX.noise(ball, "roil", { type: 6, noise: 3, contrast: 150, brightness: 0, sw: 26, sh: 40, complexity: 5, seed: 4, evo: [[0, 0], [D, 520]] });
  FX.find(roil.fx, "Offset Turbulence").expression = "[value[0], value[1] - time * 140]";
  roil.layer.blendingMode = BlendingMode.OVERLAY; roil.layer.opacity.setValue(70); roil.layer.preserveTransparency = true;

  // ---------- fractal fire luma (rising tall noise inside a soft teardrop that rides the fireball)
  var fl = EL.comp(tag + "_fireluma", 512, 512, D);
  FX.solid(fl, "black", [0, 0, 0]);
  var fn = FX.noise(fl, "flame_noise", { type: 1, noise: 3, contrast: 190, brightness: -12, sw: 32, sh: 100, complexity: 4, seed: 9, evo: [[0, 0], [D, 600]] });
  FX.find(fn.fx, "Offset Turbulence").expression = "[value[0], value[1] - time * 420]";
  var lick = FX.noise(fl, "lick_noise", { type: 1, noise: 3, contrast: 190, brightness: -25, sw: 16, sh: 55, complexity: 4, seed: 21, evo: [[0, 0], [D, 900]] });
  FX.find(lick.fx, "Offset Turbulence").expression = "[value[0], value[1] - time * 700]";
  lick.layer.blendingMode = BlendingMode.SCREEN; lick.layer.opacity.setValue(55);
  var body = EL.blob(fl, "body", [1, 1, 1], 256, 256, 120, 110, BlendingMode.NORMAL);
  body.position.expression = riseExpr(256, 250, 0.12);
  FX.keys(body.scale, [[F * 2, [25, 30]], [F * 6, [62, 90]], [F * 14, [70, 120]], [D, [50, 130]]], "out");
  body.blendingMode = BlendingMode.NORMAL;          // used as the noise's alpha track matte
  fn.layer.setTrackMatte(body, TrackMatteType.ALPHA);
  var body2 = body.duplicate(); body2.name = "body_lick"; body2.moveBefore(lick.layer);
  lick.layer.setTrackMatte(body2, TrackMatteType.ALPHA);

  // ================= main comp
  var c0 = EL.comp(tag + "_body", W, H, D);

  // 1. smoke behind (soot from cooled gas): Kenney black smoke + photo smoke, born from f5, billowing and rising
  var bs = ["blackSmoke00", "blackSmoke06", "blackSmoke12", "blackSmoke18", "blackSmoke24", "blackSmoke09", "blackSmoke21"];
  for (var s = 0; s < bs.length; s++) {
    var t0 = F * (5 + s * 1.3), ang = -Math.PI / 2 + (s - 3) * 0.42, r0 = 50 + rnd() * 25;
    var sm = EL.tex(c0, EL.KS + "Black smoke/" + bs[s] + ".png", "smoke" + s);
    EL.ball(sm, [CX + Math.cos(ang) * r0 * 0.6, CY + Math.sin(ang) * r0 * 0.6], [Math.cos(ang) * 150, Math.sin(ang) * 110 - 170], -160, 1.6, t0);
    var sc = 40 + rnd() * 18;
    FX.keys(sm.scale, [[t0, [sc * 0.45, sc * 0.45]], [D, [sc * 1.45, sc * 1.45]]], "out");
    EL.spin(sm, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * 30, 1, t0);
    FX.keys(sm.opacity, [[t0 - 0.001, 0], [t0 + 0.12, 88], [D - 0.25, 75], [D, 0]], false);
  }
  var ps = EL.tex(c0, EL.R + "smoke_04.png", "smoke_photo", { mask: 200, inset: 120 });
  RE.tint(ps, FX.rgb("4A3F38"));
  ps.position.expression = riseExpr(CX, CY - 70, 0.3);
  FX.keys(ps.scale, [[F * 7, [22, 22]], [D, [42, 42]]], "out");
  FX.keys(ps.opacity, [[F * 7, 0], [F * 12, 55], [D - 0.2, 45], [D, 0]], false);

  // 2. fireball: hot flash grade -> natural -> cooling to red; rises on buoyancy; burns out from f12
  var bl = EL.layerOf(c0, ball, "fireball");
  bl.position.expression = riseExpr(CX, CY, 0.14);
  FX.keys(bl.scale, [[0, [100, 100]], [D, [125, 112]]], false);
  var hot = RE.tint(bl, WHITE, FX.rgb("5A1404"));
  FX.keys(FX.find(hot, "Amount to Tint"), [[F * 1, 85], [F * 3, 55], [F * 6, 0]], false);
  var cool = RE.tint(bl, FX.rgb("C8400C"), [0, 0, 0]);
  FX.keys(FX.find(cool, "Amount to Tint"), [[F * 7, 0], [F * 13, 50], [F * 19, 100]], false);
  var dim = EL.levels(bl, 0, 1, 1); FX.keys(dim.property("ADBE Pro Levels2-0008"), [[F * 12, 1], [F * 22, 0.35]], false);
  FX.keys(bl.opacity, [[F * 12, 100], [F * 18, 80], [F * 26, 0]], false);

  // 3. fractal fire: rising tongues coloured by heat (alpha from density so thin gas vanishes)
  var ff = EL.layerOf(c0, fl, "fractal_fire");
  EL.levels(ff, 0.34, 0.82, 1.0);
  EL.lumaAlpha(ff);
  EL.heat(ff);
  ff.blendingMode = BlendingMode.ADD;
  FX.keys(ff.opacity, [[F * 2, 0], [F * 4, 100], [F * 14, 95], [F * 26, 0]], false);

  // 4. tongues of flame peeling off the top and accelerating up (Kenney flame cards)
  for (var k = 0; k < 7; k++) {
    var tk = F * (3 + k * 0.9 + rnd()), ak = -Math.PI / 2 + (rnd() - 0.5) * 1.9, rk = 55 + rnd() * 30;
    var lifeK = 0.32 + rnd() * 0.22, nm = ["flame_05", "flame_06"][k % 2], wisp = false;
    var bx = CX + Math.cos(ak) * rk, by = CY + Math.sin(ak) * rk * 0.8 - 0.5 * RISE * Math.pow(Math.max(0, tk - 0.14), 2);
    for (var pass = 0; pass < 2; pass++) {
      var tg = EL.tex(c0, EL.K + nm + ".png", "tongue" + k + (pass ? "_core" : ""), { anchor: [258, 360], blend: BlendingMode.ADD });
      RE.fill(tg, pass ? FX.rgb("FFE9A8") : FX.rgb("FF8A1E"));
      FX.blur(tg, wisp ? 2 : 5);
      EL.ball(tg, [bx, by], [Math.cos(ak) * 60, -170], -900, 0.4, tk);
      var sx = (wisp ? (pass ? 26 : 40) : (pass ? 20 : 34)) * (0.8 + rnd() * 0.4), sy = sx * (wisp ? 0.9 : 1.0);
      FX.keys(tg.scale, [[tk, [sx, sy * 0.4]], [tk + lifeK * 0.5, [sx, sy * 1.05]], [tk + lifeK, [sx * 0.55, sy * 1.35]]], false);
      tg.rotation.setValue((ak + Math.PI / 2) * 180 / Math.PI * 0.2);
      FX.keys(tg.opacity, [[tk - 0.001, 0], [tk + 0.05, pass ? 80 : 75], [tk + lifeK * 0.55, 60], [tk + lifeK, 0]], false);
      tg.motionBlur = !wisp;
    }
  }

  // 5. embers: ballistic with drag; small = buoyant, big = heavy; colour cools yellow -> orange -> red
  for (var e = 0; e < 64; e++) {
    var te = F * (1 + rnd() * 3), ae = rnd() * Math.PI * 2, spd = 380 + rnd() * 620, heavy = rnd() < 0.4;
    var sz = heavy ? 4 + rnd() * 2.5 : 2.2 + rnd() * 1.8, lifeE = 0.45 + rnd() * 0.65;
    var d = EL.dot(c0, "ember" + e, sz, sz, YEL);
    d.layer.blendingMode = BlendingMode.ADD; d.layer.motionBlur = true;
    var r0e = 25 + rnd() * 25;
    EL.ball(d.layer, [CX + Math.cos(ae) * r0e, CY + Math.sin(ae) * r0e], [Math.cos(ae) * spd, Math.sin(ae) * spd * 0.85 - 120], heavy ? 520 : -90, heavy ? 2.2 : 3.4, te);
    FX.keys(d.fill, [[te, FX.rgb("FFF6D0")], [te + lifeE * 0.35, FX.rgb("FFB43A")], [te + lifeE * 0.75, FX.rgb("F0560E")], [te + lifeE, FX.rgb("8A1A04")]], false);
    FX.keys(d.layer.opacity, [[te - 0.001, 0], [te, 100], [te + lifeE * 0.7, 90], [te + lifeE, 0]], false);
    d.layer.opacity.expression = "value * (0.75 + 0.25 * Math.sin(time * " + (40 + rnd() * 30).toFixed(1) + " + " + (rnd() * 6).toFixed(2) + "))";
  }
  var sk = EL.tex(c0, EL.R + "sparks_02.png", "sparkler", { pos: [CX, CY], anchor: [560, 380], blend: BlendingMode.ADD, mask: 160, inset: 150 });
  FX.keys(sk.scale, [[F * 1, [14, 14]], [F * 3, [42, 42]], [F * 7, [52, 52]]], "out");
  FX.keys(sk.opacity, [[F * 0.5, 0], [F * 1.5, 100], [F * 4, 80], [F * 8, 0]], false);

  // 6. soot that rolls OVER the dying fire (late), lit warm from below by what is left
  for (var s2 = 0; s2 < 3; s2++) {
    var t2 = F * (11 + s2 * 2), a2 = -Math.PI / 2 + (s2 - 1) * 0.6;
    var so = EL.tex(c0, EL.KS + "Black smoke/" + bs[(s2 * 2 + 1) % bs.length] + ".png", "soot_over" + s2);
    EL.ball(so, [CX + Math.cos(a2) * 50, CY - 120 + Math.sin(a2) * 30], [Math.cos(a2) * 80, -150], -150, 1.4, t2);
    FX.keys(so.scale, [[t2, [30, 30]], [D, [58, 58]]], "out");
    EL.spin(so, rnd() * 360, 25, 1, t2);
    FX.keys(so.opacity, [[t2 - 0.001, 0], [t2 + 0.2, 70], [D - 0.15, 60], [D, 0]], false);
  }

  // 7. flash (first 4 frames): Kenney flash card + flare + a big soft light
  var fc = EL.tex(c0, EL.KS + "Flash/flash00.png", "flash_card", { pos: [CX, CY], blend: BlendingMode.ADD });
  FX.keys(fc.scale, [[0, [12, 12]], [F * 2, [55, 55]], [F * 5, [68, 68]]], "out");
  FX.keys(fc.opacity, [[0, 0], [F * 0.5, 100], [F * 2, 100], [F * 5, 0]], false);
  var fw = EL.tex(c0, EL.K + "flare_01.png", "flash_flare", { pos: [CX, CY], blend: BlendingMode.ADD });
  RE.fill(fw, WHITE);
  FX.keys(fw.scale, [[0, [40, 40]], [F * 1.5, [160, 110]], [F * 4, [90, 60]]], "out");
  FX.keys(fw.opacity, [[0, 0], [F * 0.5, 100], [F * 4, 0]], false);

  // 8. air: heat shimmer + bloom
  // bloom per hot layer: a Glow ADJUSTMENT layer over this comp tears into horizontal strips under aerender's
  // multi-frame rendering (frames 17-19, reproducible); glows on the layers themselves do not
  EL.group(c0, tag + "_smoke", function (n) { return /^smoke/.test(n); });
  EL.group(c0, tag + "_flames", function (n) { return /^tongue/.test(n); });
  EL.group(c0, tag + "_embers", function (n) { return /^ember/.test(n) || n === "sparkler"; });
  EL.group(c0, tag + "_soot", function (n) { return /^soot_over/.test(n); });
  EL.group(c0, tag + "_flash", function (n) { return /^flash/.test(n); });
  var main = EL.wrapBloom(c0, tag, { blur: 22, lo: 0.35, tint: FX.rgb("FF8A2A"), opacity: [[0, 95], [F * 4, 75], [F * 16, 45], [D, 20]] });
  return EL.done(main, "normal", [CX, CY], false);
}
