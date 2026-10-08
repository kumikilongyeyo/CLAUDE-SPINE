// el_lightning_strike: a realistic cloud-to-ground strike, 512x768, 1.0 s one-shot. Ground contact at (268, 700).
// Physics: a faint STEPPED LEADER jerks down in ~60 px steps (one per frame, branching fingers), an upward
// streamer rises from the ground to meet it, then the RETURN STROKE: the whole channel snaps white-hot and wide,
// the sky/cloud base and the whole frame flash, branches die first while the main channel cools, two re-strikes
// re-light the SAME channel (dart leaders, fewer branches), then it fades. At the ground: a blinding contact flash,
// molten sparks on parabolas that bounce off the ground, a scorch, and smoke/dust that billows up afterwards.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 768, D = 1.0, F = 0.04, GX = 268, GY = 700, OX = 236, OY = 46;      // origin INSIDE the comp: the border stays alpha 0
  var RS = F * 5, RE1 = F * 12, RE2 = F * 17;        // return stroke and re-strikes
  EL.purge("el_lightning_strike_v");
  var tag = "el_lightning_strike_v" + V, rnd = FX.rng(555 + V);
  var WHITE = FX.rgb("FFFFFF"), BLUE = FX.rgb("8FA8FF"), VIOLET = FX.rgb("B49CFF"), PALE = FX.rgb("E8EEFF"), HOT = FX.rgb("FFE6A0");

  function bolt(comp, name, o, from, to) {
    var l = FX.solid(comp, name, [0, 0, 0]);
    var al = FX.fx(l, "ADBE Lightning 2");
    al.property("ADBE Lightning 2-0001").setValue(2);             // Strike: origin -> control point
    al.property("ADBE Lightning 2-0002").setValue(from);
    al.property("ADBE Lightning 2-0003").setValue(to);
    al.property("ADBE Lightning 2-0008").setValue([1, 1, 1, 1]);
    al.property("ADBE Lightning 2-0013").setValue(o.glowColor || [0.5, 0.55, 1, 1]);
    al.property("ADBE Lightning 2-0016").setValue(o.turb || 1.1);
    al.property("ADBE Lightning 2-0018").setValue(o.decay === undefined ? 0.12 : o.decay);
    al.property("ADBE Lightning 2-0020").setValue(0);
    al.property("ADBE Lightning 2-0022").setValue(o.complexity || 7);
    al.property("ADBE Lightning 2-0023").setValue(o.minFork || 40);
    al.property("ADBE Lightning 2-0004").setValue(o.cond || 10);
    return { layer: l, fx: al, p: function (n) { return al.property("ADBE Lightning 2-00" + (n < 10 ? "0" + n : n)); } };
  }

  var c = EL.comp(tag + "_body", W, H, D);

  // 1. smoke & dust from the strike point (behind the bolt), billowing up after the stroke
  var sm = [["Black smoke/blackSmoke03", 0], ["White puff/whitePuff06", 1], ["Black smoke/blackSmoke12", 0], ["White puff/whitePuff18", 1], ["Black smoke/blackSmoke21", 0], ["White puff/whitePuff09", 1]];
  for (var s = 0; s < sm.length; s++) {
    var ts = RS + F * (1 + s * 1.2), as = -Math.PI / 2 + (s - 2.5) * 0.45;
    var p = EL.tex(c, EL.KS + sm[s][0] + ".png", "smoke" + s);
    if (sm[s][1]) RE.tint(p, FX.rgb("6E6C74"), FX.rgb("1E1C22")); FX.blur(p, 3);
    EL.ball(p, [GX + Math.cos(as) * 20, GY - 10], [Math.cos(as) * 170, Math.sin(as) * 160 - 60], -90, 2.4, ts);
    var sc = 22 + rnd() * 10;
    FX.keys(p.scale, [[ts, [sc * 0.35, sc * 0.3]], [D, [sc * 1.5, sc * 1.4]]], "out");
    EL.spin(p, rnd() * 360, (rnd() < 0.5 ? -1 : 1) * 40, 1, ts);
    FX.keys(p.opacity, [[ts - 0.001, 0], [ts + 0.1, 70], [D - 0.2, 55], [D, 0]], false);
  }
  var wisp = EL.tex(c, EL.R + "smoke_02.png", "smoke_wisp", { anchor: [555, 600], mask: 80, inset: 40 });
  RE.tint(wisp, FX.rgb("B8B4C0"), [0, 0, 0]);
  wisp.position.expression = "var t = Math.max(0, time - " + (RS + 0.1) + "); [" + GX + ", " + (GY - 10) + " - 60 * t]";
  FX.keys(wisp.scale, [[RS, [18, 18]], [D, [34, 34]]], "out");
  FX.keys(wisp.opacity, [[RS + 0.08, 0], [RS + 0.3, 55], [D, 20]], false);
  // scorch on the ground (dark, flattened) with a cooling glow
  var sco = EL.tex(c, EL.K + "scorch_01.png", "scorch", { pos: [GX, GY + 6] });
  RE.fill(sco, FX.rgb("1A1412")); sco.scale.setValue([40, 12]);
  FX.keys(sco.opacity, [[RS, 0], [RS + F, 80], [D, 70]], false);
  var hotg = EL.tex(c, EL.K + "scorch_02.png", "ground_glow", { pos: [GX, GY + 4], blend: BlendingMode.ADD });
  RE.fill(hotg, FX.rgb("FF8A30")); hotg.scale.setValue([30, 9]);
  FX.keys(hotg.opacity, [[RS, 0], [RS + F, 100], [RS + 0.45, 0]], false);

  // 2. photo lightning as channel glow: the real bolt + lit cloud from lightning_02, dark cloud crushed by Levels so
  // only the light remains, added along the upper channel at each stroke
  var sky = EL.tex(c, EL.R + "lightning_02.png", "photo_bolt_glow", { anchor: [265, 290], blend: BlendingMode.ADD });
  EL.ell(sky, 270, 300, 170, 150, 60);                 // only the photographed bolt, not its lit cloud
  EL.hueSat(sky, -60, 0);
  EL.levels(sky, 0.5, 1, 1).property("ADBE Pro Levels2-0032").setValue(0.9);   // straight-alpha photo: cut the faint cloud by ALPHA
  sky.position.setValue([OX + 8, 190]); sky.scale.setValue([95, 95]); sky.rotation.setValue(49);
  FX.keys(sky.opacity, [[RS - 0.001, 0], [RS, 100], [RS + F * 2, 50], [RS + F * 3, 70], [RS + F * 6, 0],
                        [RE1 - 0.001, 0], [RE1, 70], [RE1 + F * 3, 0], [RE2 - 0.001, 0], [RE2, 40], [RE2 + F * 3, 0]], false);
  var ph1 = EL.tex(c, EL.R + "lightning_01.png", "photo_bolt_glow2", { anchor: [470, 360], blend: BlendingMode.ADD });
  EL.ell(ph1, 450, 370, 240, 190, 70);
  EL.hueSat(ph1, -60, 0); EL.levels(ph1, 0.5, 1, 1).property("ADBE Pro Levels2-0032").setValue(0.6);
  ph1.position.setValue([GX - 14, 470]); ph1.scale.setValue([85, 85]); ph1.rotation.setValue(30);
  FX.keys(ph1.opacity, [[RS - 0.001, 0], [RS, 90], [RS + F * 3, 0], [RE1 - 0.001, 0], [RE1, 55], [RE1 + F * 2, 0]], false);

  // 3. whole-frame flash: a huge soft light (no rectangular edge) flickering with each stroke
  // the stroke's air-glow: a big soft radial glow around the channel that reaches 0 well inside the comp
  // (half extent 80+115 px wide, x 1.6 = 312 px tall; comp half 256 x 384)
  var fl = EL.blob(c, "channel_flash", PALE, (OX + GX) / 2, H * 0.5, 80, 230, BlendingMode.ADD);   // all falloff, no disc
  fl.scale.setValue([100, 160]);
  FX.keys(fl.opacity, [[RS - 0.001, 0], [RS, 42], [RS + F, 12], [RS + F * 2, 24], [RS + F * 4, 0], [RE1 - 0.001, 0], [RE1, 26], [RE1 + F * 2, 0], [RE2 - 0.001, 0], [RE2, 12], [RE2 + F * 2, 0]], false);

  // 4. stepped leader: the end point jerks down one step per frame, a new branch pattern each step
  var ld = bolt(c, "stepped_leader", { glowColor: [0.45, 0.45, 1, 1], complexity: 6, minFork: 30, decay: 0.05 }, [OX, OY], [OX, 120]);
  var steps = [[0, [OX + 10, 110]], [F, [OX - 18, 240]], [F * 2, [OX + 14, 370]], [F * 3, [OX + 30, 520]], [F * 4, [GX - 6, 640]]];
  FX.keys(ld.p(3), steps, "hold");
  FX.keys(ld.p(4), [[0, 10], [F, 23], [F * 2, 31], [F * 3, 47], [F * 4, 52]], "hold");
  ld.p(6).setValue(1.2); ld.p(7).setValue(70); ld.p(11).setValue(18); ld.p(12).setValue(45); ld.p(17).setValue(0.42);
  FX.keys(ld.layer.opacity, [[0, 70], [RS - 0.001, 80], [RS, 0]], "hold");
  var up = bolt(c, "upward_streamer", { complexity: 5, minFork: 25 }, [GX, GY], [GX - 4, GY - 70]);
  up.p(6).setValue(1); up.p(11).setValue(12); up.p(17).setValue(0.2);
  FX.keys(up.layer.opacity, [[0, 0], [F * 3, 80], [RS, 0]], "hold");

  // 5. main channel: the return stroke and two re-strikes down the same channel
  var mn = bolt(c, "return_stroke", { glowColor: [0.55, 0.58, 1, 1], complexity: 7, minFork: 36, decay: 0.08 }, [OX, OY], [GX, GY]);
  mn.p(4).setValue(52);                              // same seed as the final leader step: the stroke follows it
  FX.keys(mn.p(6), [[RS, 2.2], [RS + F * 2, 1.7], [RS + F * 5, 1.1], [RE1, 1.9], [RE1 + F * 3, 1.0], [RE2, 1.5], [RE2 + F * 3, 0.7]], false);
  FX.keys(mn.p(7), [[RS, 100], [RE2 + F * 3, 90]], false);
  FX.keys(mn.p(11), [[RS, 9], [RS + F * 3, 6], [RE1, 8], [RE1 + F * 3, 5], [RE2, 6], [RE2 + F * 3, 4]], false);
  FX.keys(mn.p(12), [[RS, 50], [RS + F * 3, 35], [RE1, 45], [RE2 + F * 3, 25]], false);
  FX.keys(mn.p(17), [[RS, 0.62], [RS + F * 2, 0.25], [RS + F * 4, 0.04], [RE1, 0.2], [RE1 + F * 2, 0.02], [RE2, 0.06], [RE2 + F, 0]], false);   // branches die first
  FX.keys(mn.layer.opacity, [[RS - 0.001, 0], [RS, 100], [RS + F * 2, 90], [RS + F * 5, 55], [RE1 - F, 25], [RE1, 100], [RE1 + F * 3, 40],
                             [RE2 - F, 20], [RE2, 90], [RE2 + F * 3, 30], [D - 0.12, 8], [D, 0]], false);
  // channel air-glow: the bolt itself blown wide (violet), and a white-hot inner copy
  var glowC = mn.layer.duplicate(); glowC.name = "channel_airglow"; FX.blur(glowC, 18); glowC.blendingMode = BlendingMode.ADD;
  RE.tint(glowC, VIOLET); glowC.opacity.expression = "value * 0.5";
  // vertical bolt texture on the channel at the stroke (Kenney spark_06, real-looking jagged secondary channel)
  var sp6 = EL.tex(c, EL.K + "spark_06.png", "channel_texture", { anchor: [256, 256], blend: BlendingMode.ADD });
  sp6.position.setValue([(OX + GX) / 2, (OY + GY) / 2 + 40]); sp6.scale.setValue([60, 150]); sp6.rotation.setValue(-2);
  RE.fill(sp6, PALE);
  FX.keys(sp6.opacity, [[RS - 0.001, 0], [RS, 45], [RS + F * 2, 0], [RE1 - 0.001, 0], [RE1, 30], [RE1 + F * 2, 0]], false);

  // 6. ground contact: blinding flash, then molten sparks that fall and bounce
  var cf = EL.tex(c, EL.KS + "Flash/flash02.png", "contact_flash", { pos: [GX, GY - 8], blend: BlendingMode.ADD });
  RE.tint(cf, WHITE, BLUE);
  FX.keys(cf.scale, [[RS, [10, 8]], [RS + F, [34, 24]], [RS + F * 4, [40, 26]]], "out");
  FX.keys(cf.opacity, [[RS - 0.001, 0], [RS, 100], [RS + F * 2, 70], [RS + F * 5, 0], [RE1 - 0.001, 0], [RE1, 60], [RE1 + F * 3, 0]], false);
  var fr = EL.tex(c, EL.K + "flare_01.png", "contact_flare", { pos: [GX, GY - 6], blend: BlendingMode.ADD });
  RE.fill(fr, PALE);
  FX.keys(fr.scale, [[RS, [60, 40]], [RS + F, [190, 90]], [RS + F * 4, [100, 50]]], "out");
  FX.keys(fr.opacity, [[RS - 0.001, 0], [RS, 100], [RS + F * 4, 0]], false);
  for (var k = 0; k < 40; k++) {
    var tk = RS + rnd() * F * 1.5, ak = (-90 + (rnd() - 0.5) * 150) * Math.PI / 180, spd = 250 + rnd() * 550;
    var sz = 1.8 + rnd() * 2.2, life = 0.3 + rnd() * 0.45;
    var d = EL.dot(c, "spark" + k, sz, sz, HOT);
    d.layer.blendingMode = BlendingMode.ADD; d.layer.motionBlur = true;
    // ballistic with a bounce on the ground plane (y clamps and reflects with energy loss)
    var vx = Math.cos(ak) * spd, vy = Math.sin(ak) * spd;
    d.layer.position.expression = "var t = Math.max(0, time - " + tk + "), g = 1700, k = 0.9, e = (1 - Math.exp(-k * t)) / k;\n" +
      "var x = " + GX + " + " + vx + " * e, y = " + (GY - 4) + " + " + vy + " * e + g / k * (t - e);\n" +
      "if (y > " + GY + ") y = " + GY + " - (y - " + GY + ") * 0.35;\n[x, y]";
    FX.keys(d.fill, [[tk, FX.rgb("FFFFFF")], [tk + life * 0.4, HOT], [tk + life, FX.rgb("FF6A1A")]], false);
    FX.keys(d.layer.opacity, [[tk - 0.001, 0], [tk, 100], [tk + life * 0.7, 90], [tk + life, 0]], false);
  }

  // 7. bloom tied to the strokes
  var gb = FX.adj(c, "bloom"); var g = FX.glow(gb, 22, 0.5, 72, PALE, BLUE);
  // cloud base glow where the channel leaves the cloud (origin), small and radial
  var cg = EL.blob(c, "cloud_glow", FX.rgb("C8C0FF"), OX, OY + 6, 50, 60, BlendingMode.ADD);
  cg.scale.setValue([180, 70]);
  FX.keys(cg.opacity, [[0, 25], [RS - 0.001, 30], [RS, 90], [RS + F * 3, 35], [RE1, 70], [RE1 + F * 3, 25], [RE2, 50], [D, 0]], false);
  FX.keys(FX.find(g, "Glow Intensity"), [[0, 0.25], [RS, 0.6], [RS + F * 3, 0.35], [RE1, 0.5], [RE1 + F * 3, 0.3], [RE2, 0.4], [D, 0.25]], false);
  var main = EL.edgeSafe(c, tag, 36, 40);
  return EL.done(main, "normal", [GX, GY], false);
}
