// fire_rose_burst (085808): a cel explosion shaped like a rose. f2 white star-flower, f4 full bloom (white lobes on
// hot red, crimson centre), f8 crimson interior with holes, f12 only rim fragments, gone ~f21. Soft red glow.
// Three grey fields: A = silhouette (radial ramp x blobby noise), H = white highlights, E = erosion (holes).
function BUILD(V) {
  var S = 3, W = 164 * S, H = 204 * S, cx = 82 * S, cy = 100 * S;
  var D = 1.12, fps = 25, tag = "fr_rose_v" + V;
  var f = FX.gt("fire_rose_burst");
  var WHITE = FX.rgb("FFF8F4"), RED = FX.rgb("FF1428"), PINK = FX.rgb("EE1440"), CRIM = FX.rgb("B5163F"), PLUM = FX.rgb("6E1030");

  // A: silhouette density = radial ramp + centred noise (ADD), so the cel threshold cuts petal lobes
  var A = FX.density(tag + "_A", W, H, fps, D, function (d) {
    var pet = FX.shape(d, "petals");
    var st = FX.group(pet, "star", { points: 7, r1: 52 * S, r2: 34 * S, fill: [1, 1, 1] });
    st.star.property("ADBE Vector Star Outer Roundess").setValue(90);
    st.star.property("ADBE Vector Star Inner Roundess").setValue(30);
    pet.position.setValue([cx, cy]); pet.rotation.setValue(8);
    FX.keys(pet.scale, [[f(1.2), [4, 4]], [f(2), [46, 46]], [f(3), [76, 76]], [f(4), [94, 94]], [f(6), [100, 100]], [f(10), [104, 104]], [f(16), [106, 106]]], "out");
    FX.keys(pet.rotation, [[f(1), -6], [f(16), 14]], false);
    FX.blur(pet, 10 * S);
    var n = FX.noise(d, "breakup", { type: 1, noise: 4, contrast: 140, brightness: -28, scale: 14 * S, complexity: 2, seed: 4, evo: [[0, 0], [D, 160]] });
    n.layer.blendingMode = BlendingMode.ADD; n.layer.opacity.setValue(45);
  });
  // H: white highlight field: small blobby noise + a bright band near the rim
  var Hh = FX.density(tag + "_H", W, H, fps, D, function (d) {
    FX.noise(d, "hl", { type: 1, noise: 4, contrast: 200, brightness: -10, scale: 18 * S, complexity: 1, seed: 9, evo: [[0, 0], [D, 200]] });
    var r = FX.ramp(d, "rim", cx, cy, 10, [0, 0, 0, 1], [0.55, 0.55, 0.55, 1], BlendingMode.ADD);
    FX.rampRadius(r, cx, cy, [[f(1), 4], [f(4), 56 * S], [f(10), 70 * S]]);
  });
  // E: erosion field: blobby noise + a growing centre ramp: holes open in the middle and spread out
  var E = FX.density(tag + "_E", W, H, fps, D, function (d) {
    var n = FX.noise(d, "holes", { type: 1, noise: 4, contrast: 120, brightness: 0, scale: 11 * S, complexity: 1, seed: 21, evo: [[0, 0], [D, 120]] });
    n.layer.opacity.setValue(80);
    var r = FX.ramp(d, "spread", cx, cy, 10, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.ADD);
    FX.rampRadius(r, cx, cy, [[f(3), 4], [f(6), 30 * S], [f(9), 50 * S], [f(13), 66 * S], [f(20), 90 * S]]);
    FX.keys(r.layer.opacity, [[f(3), 10], [f(8), 25], [f(13), 35]], false);
  });

  // body: everything that sits inside the silhouette, built in its own comp so the holes can cut it once
  var body = FX.comp(tag + "_body", W, H, fps, D, "fxlib_density");
  FX.cel(body, A, "outline", 0.5, RED, 0.015);
  FX.celIn(body, A, "fill", 0.58, PINK, 0.015, A, 0.58);
  FX.celIn(body, Hh, "white", [[f(1.5), 0.35], [f(3), 0.62], [f(5), 0.72], [f(7), 0.8], [f(10), 0.95]], WHITE, 0.02, A, 0.54);
  FX.celIn(body, E, "crimson", [[f(3), 0.74], [f(6), 0.54], [f(8), 0.42], [f(10), 0.43], [f(12), 0.36], [f(16), 0.28], [f(21), 0.18]], CRIM, 0.02, A, 0.52);
  FX.celIn(body, E, "plum", [[f(3), 0.93], [f(6), 0.73], [f(8), 0.61], [f(10), 0.52], [f(12), 0.45], [f(16), 0.37], [f(21), 0.27]], PLUM, 0.02, A, 0.52);

  var c = FX.comp(tag, W, H, fps, D);
  // halo behind
  var halo = FX.cel(c, A, "halo", 0.3, FX.rgb("E0102A"), 0.3);
  FX.blur(halo, 10 * S);
  FX.keys(halo.opacity, [[f(1.5), 0], [f(2), 80], [f(6), 55], [f(10), 20], [f(14), 0]], false);
  var bl = c.layers.add(body); bl.name = "body";
  FX.keys(bl.opacity, [[f(14), 100], [f(21), 0]], false);
  var holes = FX.cel(c, E, "holes", [[f(3), 0.98], [f(6), 0.78], [f(8), 0.66], [f(10), 0.57], [f(12), 0.5], [f(16), 0.42], [f(21), 0.32]], [1, 1, 1], 0.015);
  FX.matte(bl, holes, true);
  return FX.done(c);
}
