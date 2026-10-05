/*TEMPLATE {"name":"relief_shimmer","doc":"A light wave that sweeps across a picture and catches only its relief (edges, engraving, depth). `image` is the art (transparent PNG); `depth` is an optional height map (white = high) that drives the highlights instead of the art itself. Needs the art's own size, so the comp matches it. Renders additive: use mode=additive.","params":{"image":"","depth":"","duration":1.0,"fps":30,"color":"FFD27A","relief":8,"contrast":100,"threshold_low":0.52,"threshold_high":0.80,"origin_x":0.5,"origin_y":0.5,"wave":0.22,"glow":1.0,"sheen":0.05}} */
if (!P.image) throw new Error("relief_shimmer needs image=<path to the art PNG>");
function imp(path) {
  var f = new File(path); if (!f.exists) throw new Error("file not found: " + path);
  for (var i = 1; i <= app.project.numItems; i++) {         // the same file is imported once, not per run
    var q = app.project.item(i);
    if (q instanceof FootageItem && q.mainSource instanceof FileSource && q.mainSource.file && q.mainSource.file.fsName === f.fsName) return q;
  }
  var io = new ImportOptions(f); var it = app.project.importFile(io); it.parentFolder = AEFX.folder(); return it;
}
var art = imp(P.image), src = P.depth ? imp(P.depth) : art;
var W = art.width, H = art.height, D = P.duration, name = P.comp || "relief_shimmer";
var col = AEFX.rgb(P.color), big = Math.max(W, H);

// 1. emboss stack: two light directions, so edges facing either way catch the wave
var stack = AEFX.comp(name + "_emboss", W, H, P.fps, D);
for (var k = 0; k < 2; k++) {
  var l = stack.layers.add(src);
  var em = AEFX.fx(l, "ADBE Emboss");
  em.property("ADBE Emboss-0001").setValue(k ? 315 : 135);
  em.property("ADBE Emboss-0002").setValue(P.relief);
  em.property("ADBE Emboss-0003").setValue(P.contrast);
  if (k) l.blendingMode = BlendingMode.ADD;
}
var adj = stack.layers.addSolid([1, 1, 1], "relief_levels", W, H, 1); adj.adjustmentLayer = true;
var lv = AEFX.fx(adj, "ADBE Easy Levels2");
lv.property("Input Black").setValue(P.threshold_low); lv.property("Input White").setValue(P.threshold_high);
var tn = AEFX.fx(adj, "ADBE Tint");
tn.property("Map Black To").setValue([0, 0, 0]); tn.property("Map White To").setValue(col);

// 2. clip the relief to the art's own outline
var pre = AEFX.comp(name + "_relief", W, H, P.fps, D);
var matteArt = pre.layers.add(art);
var rel = pre.layers.add(stack); rel.moveAfter(matteArt);
rel.setTrackMatte(matteArt, TrackMatteType.ALPHA);

// 3. the comp: a ring wave from (origin) reveals the relief; a wider, softer one reveals a faint sheen
var comp = AEFX.comp(name, W, H, P.fps, D);
var cx = W * P.origin_x, cy = H * P.origin_y;
var far = Math.sqrt(Math.max(cx, W - cx) * Math.max(cx, W - cx) + Math.max(cy, H - cy) * Math.max(cy, H - cy)) * 2.1;
function ring(label, widthF, blurF) {
  var r = AEFX.shape(comp, label);
  var e = AEFX.ellipse(r, far, null, [1, 1, 1], big * widthF);
  r.position.setValue([cx, cy]);
  AEFX.keys(e.size, [[0, [big * 0.02, big * 0.02]], [D, [far, far]]], false);
  AEFX.keys(r.opacity, [[0, 100], [D * 0.8, 100], [D, 0]], false);
  AEFX.fx(r, "ADBE Gaussian Blur 2").property("Blurriness").setValue(big * blurF);
  return r;
}
var gl = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); gl.adjustmentLayer = true;
var g = AEFX.fx(gl, "ADBE Glo2");
g.property("Glow Threshold").setValue(40); g.property("Glow Radius").setValue(big * 0.033 * P.glow); g.property("Glow Intensity").setValue(0.9 * P.glow);
var m1 = ring("wave_matte", P.wave, 0.05);
var relief = comp.layers.add(pre); relief.name = "relief"; relief.blendingMode = BlendingMode.ADD;
relief.moveAfter(m1); relief.setTrackMatte(m1, TrackMatteType.LUMA);
var m2 = ring("sheen_matte", P.wave * 1.8, 0.1);
m2.moveAfter(relief);
var sheen = comp.layers.add(art); sheen.name = "sheen"; sheen.blendingMode = BlendingMode.ADD; sheen.opacity.setValue(P.sheen * 100);
AEFX.fx(sheen, "ADBE Fill").property("Color").setValue(col);
sheen.moveAfter(m2); sheen.setTrackMatte(m2, TrackMatteType.LUMA);
return AEFX.done(comp, '"mode":"additive"');
