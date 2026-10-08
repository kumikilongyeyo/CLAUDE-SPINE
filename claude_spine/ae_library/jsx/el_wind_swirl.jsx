// el_wind_swirl: seamless wind-gust vortex (a small whirlwind), 512x512, loop of 38 frames (1.52 s at 25 fps).
// Physics: air spins faster at the narrow base (conservation of angular momentum: the low rings turn 2 rev per
// loop, the wide top 1), the column leans and sways, dust is dragged in along the ground and lifted, leaves are
// caught in it and spiral UP while tumbling (3D flutter = scale-x flip), translucent air streaks show the flow,
// and a cycled turbulent distortion bends everything slightly. Every motion is periodic in P.
$.evalFile(FXLIB_DIR + "el_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, P = 1.52, F = 0.04, CX = 256, BY = 446, TY = 96;
  EL.purge("el_wind_swirl_v");
  var tag = "el_wind_swirl_v" + V, rnd = FX.rng(2024 + V);
  var TP = "6.283185307179586", AIR = FX.rgb("E4F2FA"), AIR2 = FX.rgb("B9D6E6"), DUST = FX.rgb("B49C7C");
  function per(n, ph) { return "(" + TP + " * " + n + " * time / " + P + " + " + (ph || 0).toFixed(3) + ")"; }

  // ---------- one ring of moving air (2P long so a time-offset layer still loops): twirls + streaks, spinning
  function ring(name, revs, seed) {
    var r = FX.rng(seed);
    var rc = EL.comp(name, 512, 512, 2 * P);
    var tw = seed % 2 ? ["twirl_01", "twirl_03"] : ["twirl_02", "twirl_03"];    // broken arcs, not closed rings
    for (var i = 0; i < tw.length; i++) {
      var t = EL.tex(rc, EL.K + tw[i] + ".png", "twirl" + i, { pos: [256, 256], blend: BlendingMode.SCREEN });
      RE.fill(t, i % 2 ? AIR : AIR2);
      var s = 88 + r() * 16; t.scale.setValue([s, s]);
      t.rotation.expression = (i * 160 + r() * 40).toFixed(1) + " + 360 * " + revs + " * time / " + P;
      t.opacity.expression = (38 + r() * 25).toFixed(0) + " + 20 * Math.sin" + per(1, r() * 6);
    }
    for (var k = 0; k < 8; k++) {                    // thin streaks riding the ring, tangent to it
      var st = EL.tex(rc, EL.K + (k % 2 ? "trace_04" : "trace_06") + ".png", "streak" + k, { blend: BlendingMode.SCREEN });
      RE.fill(st, AIR);
      var a0 = r() * 360, rad = 170 + r() * 50;
      st.position.expression = "var a = (" + a0.toFixed(1) + " + 360 * " + revs + " * time / " + P + ") * Math.PI / 180; [256 + " + rad + " * Math.cos(a), 256 + " + rad + " * Math.sin(a)]";
      st.rotation.expression = a0.toFixed(1) + " + 360 * " + revs + " * time / " + P;
      st.scale.setValue([40, 70 + r() * 40]);
      st.opacity.expression = "Math.max(0, 70 * Math.sin" + per(revs, r() * 6) + ")";
    }
    return rc;
  }
  var ringFast = ring(tag + "_ring_fast", 2, 11), ringSlow = ring(tag + "_ring_slow", 1, 24), ringMid = ring(tag + "_ring_mid", 1, 37);

  var c = EL.comp(tag, W, H, P);
  // the column axis: leans and sways (periodic)
  function axisX(yExpr) { return CX + " + (" + BY + " - " + yExpr + ") * 0.10 + 22 * Math.sin(" + TP + " * time / " + P + " - (" + BY + " - " + yExpr + ") * 0.006)"; }

  // 1. dust at the base: dragged in and lifted (Kenney smoke tinted dust, spinning with the base)
  var dn = ["smoke_07", "smoke_08", "smoke_05"];
  for (var d = 0; d < dn.length; d++) {
    var dl = EL.tex(c, EL.K + dn[d] + ".png", "base_dust" + d);
    RE.tint(dl, DUST, FX.rgb("4A3C2C"));
    dl.position.expression = "[" + axisX(BY - 10 - d * 18) + ", " + (BY - 10 - d * 18) + "]";
    dl.scale.expression = "var s = " + (52 - d * 8) + " + 5 * Math.sin" + per(1, d * 2) + "; [s, s * 0.42]";
    dl.rotation.expression = (d * 120) + " + 360 * " + (d % 2 ? -1 : 1) + " * time / " + P;
    dl.opacity.setValue(55 - d * 10);
  }
  // 2. the funnel: rings stacked from the narrow fast base to the wide slow top, each time-offset
  var NR = 11;
  for (var i = 0; i < NR; i++) {
    var f = i / (NR - 1), y = BY - 20 - (BY - 20 - TY) * f, w = 70 + 360 * Math.pow(f, 1.3);
    var rl = EL.layerOf(c, f < 0.35 ? ringFast : (i % 2 ? ringSlow : ringMid), "ring" + i, BlendingMode.SCREEN);
    rl.startTime = -(i * 0.37 % P);
    rl.position.expression = "[" + axisX(y.toFixed(1)) + ", " + y.toFixed(1) + "]";
    rl.scale.setValue([w / 480 * 100 * (0.9 + 0.2 * rnd()), w / 480 * 100 * (0.26 + 0.1 * rnd())]);
    rl.rotation.setValue((rnd() - 0.5) * 14);
    rl.opacity.setValue(55 - 20 * Math.abs(f - 0.4));
  }
  // 2b. body of the funnel: dust-laden air (photo smoke tinted), spinning with the column, fading toward the top
  for (var v = 0; v < 4; v++) {
    var fv = v / 3, yv = BY - 50 - (BY - TY - 80) * fv;
    var bv = EL.tex(c, EL.R + "smoke_04.png", "funnel_dust" + v, { anchor: [380, 360], mask: 180, inset: 120 });
    RE.tint(bv, FX.rgb("C8BCA8"), FX.rgb("2A241C"));
    bv.position.expression = "[" + axisX(yv.toFixed(1)) + ", " + yv.toFixed(1) + "]";
    var wv = 12 + 30 * fv;
    bv.scale.setValue([wv, wv * 0.5]);
    bv.rotation.expression = (v * 90) + " + 360 * time / " + P;
    bv.opacity.setValue(40 - 18 * fv);
    bv.blendingMode = BlendingMode.SCREEN;
  }
  // 3. dust specks orbiting low and rising a little
  for (var k = 0; k < 26; k++) {
    var dt = EL.dot(c, "speck" + k, 2 + rnd() * 2.5, 2 + rnd() * 2, rnd() < 0.5 ? DUST : FX.rgb("8A7458"));
    var ph = rnd(), turns = 2 + Math.floor(rnd() * 2), hmax = 60 + rnd() * 160;
    var u = "var f = ((time / " + P + " + " + ph.toFixed(3) + ") % 1 + 1) % 1, y = " + (BY - 10) + " - " + hmax.toFixed(0) + " * f, " +
            "r = 30 + (" + BY + " - y) * 0.55, a = " + TP + " * (" + turns + " * f + " + rnd().toFixed(3) + ");";
    dt.layer.position.expression = u + " [" + axisX("y") + " + r * Math.cos(a), y + r * 0.3 * Math.sin(a)]";
    dt.layer.opacity.expression = u + " 85 * Math.min(1, f / 0.1) * Math.min(1, (1 - f) / 0.15)";
    dt.layer.motionBlur = true;
  }
  // 4. leaves caught in the vortex: spiral up, tumbling
  var LEAF = [[0, -9], [5, -5], [6, 1], [3, 7], [0, 10], [-3, 7], [-6, 1], [-5, -5]];
  var lc = [FX.rgb("6E8A2A"), FX.rgb("A4802A"), FX.rgb("8A5A22"), FX.rgb("5E7A26"), FX.rgb("B8902E")];
  for (var l = 0; l < 9; l++) {
    var lf = EL.poly(c, "leaf" + l, LEAF, lc[l % lc.length]);
    var vein = FX.group(lf, "path", { points: [[0, -8], [0, 9]], stroke: FX.rgb("2E2A12"), width: 0.8 });
    EL.bevel(lf, 1.2, -50, 0.5);
    var ph2 = l / 9 + rnd() * 0.05, turns2 = 1 + (l % 2), sc = 2.0 + rnd() * 1.0, spin = 1 + Math.floor(rnd() * 3);
    var u2 = "var f = ((time / " + P + " + " + ph2.toFixed(3) + ") % 1 + 1) % 1, y = " + (BY - 20) + " - " + (BY - TY - 40) + " * f, " +
             "r = 40 + (" + BY + " - y) * 0.52, a = " + TP + " * (" + turns2 + " * f + " + rnd().toFixed(3) + ");";
    lf.position.expression = u2 + " [" + axisX("y") + " + r * Math.cos(a), y + r * 0.3 * Math.sin(a)]";
    lf.scale.expression = u2 + " var d = 0.8 + 0.25 * Math.sin(a); [" + (sc * 100).toFixed(0) + " * d * Math.cos(" + TP + " * " + spin + " * f * 2), " + (sc * 100).toFixed(0) + " * d]";
    lf.rotation.expression = u2 + " a * 57.3 + 360 * " + spin + " * f";
    lf.opacity.expression = u2 + " 100 * Math.min(1, f / 0.08) * Math.min(1, (1 - f) / 0.12) * (0.75 + 0.25 * Math.sin(a))";
    lf.motionBlur = true;
  }
  // 5. a few big translucent gust sheets sweeping across the whole vortex (Kenney twirl, slow)
  for (var g = 0; g < 2; g++) {
    var gs = EL.tex(c, EL.K + "twirl_01.png", "gust_sheet" + g, { blend: BlendingMode.SCREEN });
    RE.fill(gs, AIR);
    gs.position.expression = "[" + axisX(260 - g * 60) + ", " + (260 - g * 60) + "]";
    gs.scale.setValue([95 - g * 10, 40]);
    gs.rotation.expression = (g * 180) + " + 360 * time / " + P;
    gs.opacity.expression = "35 + 15 * Math.sin" + per(1, g * 3);
  }
  // 6. distortion of the moving air (cycled, loops)
  var ds = FX.adj(c, "air_distortion"); EL.turb(ds, 10, 50, P, 1, true, 2);
  return EL.done(c, "normal", [CX, BY], true);
}
