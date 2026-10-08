// re_aqua_impact: realistic version of aq_aqua_impact_v14 (same size/timing; the water silhouette, holes, starburst
// and sparkle dots are the exact comp's own procedural sub-comps). Real water: the cel blob gets CC Glass refraction +
// specular, water_02/water_01 photo material and a water_02 droplet burst on the shatter; the white starburst becomes
// crackling electricity with Advanced Lightning arcs and blue bloom.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
function BUILD(V) {
  var SRC = "aq_aqua_impact_v14", S = 3, W = 480, H = 414, cx = 71 * S, cy = 66 * S, D = 1.0;
  RE.purge("re_aqua_impact_v");
  var tag = "re_aqua_impact_v" + V;
  var f = FX.gt("aqua_impact");
  var rnd = FX.rng(61);
  var CORE = FX.rgb("F2F7FF"), PALE = FX.rgb("B8D0FF"), BLU = FX.rgb("5F86D8"), DEEP = FX.rgb("21407C");
  // drivers from the exact build
  var water = RE.only(SRC + "_body", tag + "_water", function (n) { return !(n === "white" || n.indexOf("violet") === 0 || n.indexOf("cyan") === 0); });
  var Hd = RE.findComp(SRC + "_H"), gsrc = RE.findComp(SRC + "_glowsrc"), spc = RE.findComp(SRC + "_sparks");
  var c = RE.comp(tag, W, H, D);
  function holes(l) { var h = FX.cel(c, Hd, l.name + "_holes", 0.6, [1, 1, 1], 0.02); FX.matte(l, h, true); return l; }

  // 1. electricity behind the water: bloom, crackled starburst, lightning arcs
  RE.light(c, gsrc, "elec_bloom_deep", DEEP, 10 * S, 100);
  RE.light(c, gsrc, "elec_bloom", BLU, 3.5 * S, 100);
  var ec = RE.light(c, gsrc, "elec_crackle", PALE, 0, 100);
  var td = FX.fx(ec, "ADBE Turbulent Displace"); FX.set(td, "Amount", 9); FX.set(td, "Size", 2 * S); FX.set(td, "Complexity", 3);
  FX.find(td, "Evolution").expression = "Math.floor(time * 25) * 47";
  var ecore = RE.light(c, gsrc, "elec_core", CORE, 0, 90);
  FX.fx(ecore, "ADBE Simple Choker"); FX.set(ecore.property("ADBE Effect Parade").property("ADBE Simple Choker"), "Choke Matte", 2);
  for (var b = 0; b < 10; b++) {
    var a = (b * 36 + (rnd() - 0.5) * 18) * Math.PI / 180, r0 = (36 + rnd() * 6) * S, r1 = (50 + rnd() * 9) * S;
    var l = FX.solid(c, "arc" + b, [0, 0, 0]);
    var lg = FX.fx(l, "ADBE Lightning 2");
    FX.set(lg, "Lightning Type", 2);
    FX.set(lg, "Origin", [cx + Math.cos(a) * r0, cy + Math.sin(a) * r0]);
    FX.set(lg, "Contextual Control", [cx + Math.cos(a) * r1, cy + Math.sin(a) * r1]);
    FX.find(lg, "Conductivity State").expression = "Math.floor(time * 25) * 7.7 + " + b * 3;
    FX.set(lg, "Core Radius", 0.9); FX.set(lg, "Core Opacity", 100); FX.set(lg, "Core Color", CORE);
    FX.set(lg, "Glow Radius", 6); FX.set(lg, "Glow Opacity", 50); FX.set(lg, "Glow Color", BLU);
    FX.set(lg, "Turbulence", 1.3); FX.set(lg, "Forking", 0.3); FX.set(lg, "Decay", 0.5); FX.set(lg, "Complexity", 6); FX.set(lg, "Min. Forkdistance", 25);
    var tb = f(10.1 + rnd() * 0.6), te = f(13.6 + rnd() * 0.6);
    FX.keys(l.opacity, [[tb - 0.01, 0], [tb, 100], [te, 80], [te + 0.04, 0]], false);
    l.blendingMode = BlendingMode.ADD;
  }

  // 2. the water: exact cel shading softened, refracting + specular (CC Glass on its own alpha), cut by the holes
  var wb = c.layers.add(water); wb.name = "water_body";
  FX.blur(wb, 0.8 * S);
  var ex = FX.fx(wb, "ADBE Exposure2"); FX.set(ex, "Exposure", -0.3);   // keep the teal deep under the glass light
  var gl = FX.fx(wb, "CC Glass");
  FX.set(gl, "Bump Map", wb.index); FX.set(gl, "Softness", 14); FX.set(gl, "Height", 35); FX.set(gl, "Displacement", 60);
  FX.set(gl, "Light Intensity", 85); FX.set(gl, "Light Direction", -45); FX.set(gl, "Light Height", 50);
  FX.set(gl, "Ambient", 55); FX.set(gl, "Diffuse", 45); FX.set(gl, "Specular", 100); FX.set(gl, "Roughness", 0.04); FX.set(gl, "Metal", 30);
  holes(wb);
  // photo water material inside the body
  var w2 = RE.tex(c, RE.R + "water_02.png", "water_photo", { pos: [cx, cy], blend: BlendingMode.SCREEN });
  RE.tint(w2, FX.rgb("DFFBFF"), FX.rgb("0A3C44"));
  FX.keys(w2.scale, [[f(10), [26, 26]], [f(14), [32, 32]], [D, [38, 38]]], "out");
  FX.keys(w2.rotation, [[0, -8], [D, 14]], false);
  w2.opacity.setValue(26);
  var w2m = c.layers.add(water); w2m.name = "water_photo_matte"; holes(w2m);
  FX.matte(w2, w2m, false);
  var w1 = RE.tex(c, RE.R + "water_01.png", "water_foam", { pos: [cx, cy + 6 * S], blend: BlendingMode.OVERLAY });
  RE.tint(w1, FX.rgb("E8FFFF"), FX.rgb("0E5A60"));
  FX.keys(w1.scale, [[f(10), [30, 30]], [D, [40, 40]]], false);
  w1.opacity.setValue(40);
  var w1m = c.layers.add(water); w1m.name = "water_foam_matte"; holes(w1m);
  FX.matte(w1, w1m, false);

  // 3. shatter (f14): a real droplet burst flying out
  var sp = RE.tex(c, RE.R + "water_02.png", "droplet_burst", { pos: [cx, cy], blend: BlendingMode.SCREEN });
  RE.circMask(sp, 520, 320, 330, 160);
  sp.anchorPoint.setValue([520, 320]);
  RE.tint(sp, FX.rgb("9FE6EE"), FX.rgb("000000"));
  FX.keys(sp.scale, [[f(13.6), [22, 22]], [f(15), [36, 36]], [f(19), [46, 46]]], "out");
  FX.keys(sp.opacity, [[f(13.5), 0], [f(14.2), 30], [f(16), 12], [f(18.5), 0]], false);
  var sp2 = RE.tex(c, RE.R + "water_02.png", "droplet_burst2", { pos: [cx, cy], blend: BlendingMode.SCREEN, rot: 160 });
  RE.circMask(sp2, 520, 320, 330, 160);
  sp2.anchorPoint.setValue([520, 320]);
  RE.tint(sp2, FX.rgb("7FD0DC"), FX.rgb("000000"));
  FX.keys(sp2.scale, [[f(13.8), [18, 18]], [f(15.5), [32, 32]], [f(20), [42, 42]]], "out");
  FX.keys(sp2.opacity, [[f(13.7), 0], [f(14.5), 22], [f(16.5), 8], [f(19), 0]], false);

  // 4. sparkle droplets (exact dots) as blue-white glints
  RE.light(c, spc, "glints_bloom", BLU, 2 * S, 60);
  RE.light(c, spc, "glints", CORE, 0, 100);

  // 5. the first spark (f9-f10): cold flare + short arcs along the spark arms
  var fl = RE.tex(c, RE.K + "flare_01.png", "spark_flare", { pos: [cx, cy - 1 * S] });
  RE.fill(fl, PALE);
  FX.keys(fl.scale, [[f(8.7), [15, 15]], [f(9.2), [70, 70]], [f(10.3), [60, 60]], [f(11), [30, 30]]], false);
  FX.keys(fl.opacity, [[f(8.7), 0], [f(8.9), 100], [f(10.2), 80], [f(10.9), 0]], false);
  var st = RE.tex(c, RE.K + "star_04.png", "spark_star", { pos: [cx, cy - 1 * S] });
  RE.fill(st, CORE);
  FX.keys(st.scale, [[f(8.8), [12, 12]], [f(9.5), [40, 40]], [f(10.5), [55, 55]]], "out");
  FX.keys(st.opacity, [[f(8.8), 0], [f(9), 100], [f(10.4), 90], [f(11), 0]], false);
  for (var k = 0; k < 4; k++) {
    var ka = (k * 90 + 25 + rnd() * 40) * Math.PI / 180;
    var sl = FX.solid(c, "spark_arc" + k, [0, 0, 0]);
    var sg = FX.fx(sl, "ADBE Lightning 2"); FX.set(sg, "Lightning Type", 2); FX.set(sg, "Origin", [cx, cy - 1 * S]);
    FX.keys(FX.find(sg, "Contextual Control"), [[f(9), [cx + Math.cos(ka) * 10 * S, cy + Math.sin(ka) * 10 * S]], [f(10.5), [cx + Math.cos(ka) * 30 * S, cy + Math.sin(ka) * 30 * S]]], "out");
    FX.find(sg, "Conductivity State").expression = "Math.floor(time * 25) * 5.3 + " + k * 2;
    FX.set(sg, "Core Radius", 0.8); FX.set(sg, "Core Color", CORE); FX.set(sg, "Glow Radius", 5); FX.set(sg, "Glow Color", BLU);
    FX.set(sg, "Turbulence", 1.2); FX.set(sg, "Forking", 0.2); FX.set(sg, "Complexity", 6);
    FX.keys(sl.opacity, [[f(8.9), 0], [f(9.1), 100], [f(10.4), 80], [f(10.9), 0]], false);
    sl.blendingMode = BlendingMode.ADD;
  }
  // 6. cool bloom over all, mostly on the electric parts
  var gb = FX.adj(c, "bloom"); var g = FX.glow(gb, 6 * S, 0.3, 80, PALE, BLU);
  return FX.done(c);
}
