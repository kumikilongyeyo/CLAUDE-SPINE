/*TEMPLATE {"name":"surface_sweep","doc":"A shine that sits ON the surface instead of a flat white bar: the art's own colours brightened inside a soft band that sweeps across, the band bent around a sphere (Spherize) so it follows the volume, plus an emboss highlight of a depth map (or the art) inside the band. `image` = the art (transparent PNG, the comp takes its size); `depth` = optional height map (white = high); `sphere` = [x, y] centre in image px and `radius` px (0 = no bend). Renders additive (mode=additive); in Spine pass deform_like=<the art's slots> to ae_fx_to_spine so the light deforms with the art. Run it at reduced opacity (0.5-0.6) for a gentle idle shine.","params":{"image":"","depth":"","duration":1.2,"fps":30,"band":0.3,"soft":0.12,"angle":22,"travel":0.3,"surface":0.75,"highlight":0.55,"color":"FFF3DC","light_angle":135,"relief":6,"contrast":120,"threshold_low":0.55,"threshold_high":0.85,"glow":0.5,"sphere":[],"radius":0}} */
if (!P.image) throw new Error("surface_sweep needs image=<path to the art PNG>");
var art = AEFX.imp(P.image), dep = P.depth ? AEFX.imp(P.depth) : art;
var W = art.width, H = art.height, D = P.duration, fps = P.fps, name = P.comp || "surface_sweep";
var band = AEFX.comp(name + "_band", W, H, fps, D);
band.layers.addSolid([0, 0, 0], "black", W, H, 1);
var bar = AEFX.rect(band, "bar", W * P.band, H * 2.4);
bar.rotation.setValue(P.angle);
AEFX.keys(bar.position, [[0, [-W * P.travel, H * 0.5]], [D, [W * (1 + P.travel), H * 0.5]]], true);
AEFX.fx(bar, "ADBE Gaussian Blur 2").property("Blurriness").setValue(W * P.soft);
var comp = AEFX.comp(name, W, H, fps, D);
function matteFor(target) {
  var m = comp.layers.add(band); m.name = "band_matte";
  if (P.radius > 0) {
    var sp = AEFX.fx(m, "ADBE Spherize");
    AEFX.set(sp, "Radius", P.radius * 1.02);
    AEFX.set(sp, "Center of Sphere", P.sphere.length ? P.sphere : [W / 2, H / 2]);
  }
  m.moveBefore(target); target.setTrackMatte(m, TrackMatteType.LUMA);
  return m;
}
var lit = comp.layers.add(art); lit.name = "surface_light"; lit.opacity.setValue(P.surface * 100);
matteFor(lit);
var rel = AEFX.comp(name + "_relief", W, H, fps, D);
var e1 = rel.layers.add(dep);
var em = AEFX.fx(e1, "ADBE Emboss");
em.property("ADBE Emboss-0001").setValue(P.light_angle); em.property("ADBE Emboss-0002").setValue(P.relief);
em.property("ADBE Emboss-0003").setValue(P.contrast);
var lvA = rel.layers.addSolid([1, 1, 1], "levels", W, H, 1); lvA.adjustmentLayer = true;
var lv = AEFX.fx(lvA, "ADBE Easy Levels2");
lv.property("Input Black").setValue(P.threshold_low); lv.property("Input White").setValue(P.threshold_high);
var tn = AEFX.fx(lvA, "ADBE Tint");
tn.property("Map Black To").setValue([0, 0, 0]); tn.property("Map White To").setValue(AEFX.rgb(P.color));
var relOut = AEFX.comp(name + "_relief_clip", W, H, fps, D);
var rl = relOut.layers.add(rel);
var am = relOut.layers.add(art);
rl.setTrackMatte(am, TrackMatteType.ALPHA);
var hi = comp.layers.add(relOut); hi.name = "relief_light"; hi.blendingMode = BlendingMode.ADD; hi.opacity.setValue(P.highlight * 100);
matteFor(hi);
var gl = comp.layers.addSolid([1, 1, 1], "glow", W, H, 1); gl.adjustmentLayer = true;
var g = AEFX.fx(gl, "ADBE Glo2");
g.property("Glow Threshold").setValue(55); g.property("Glow Radius").setValue(W * 0.03); g.property("Glow Intensity").setValue(P.glow);
return AEFX.done(comp, '"mode":"additive"');
