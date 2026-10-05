/*TEMPLATE {"name":"heat_shimmer","doc":"Heat shimmer above a fire, with exaggerated real optics: hot air has a lower refractive index, and the turbulent plume carries eddies of it UPWARD at `rise` px/s (fractal noise, flattened eddies, streaming up, rendered twice the duration and crossfaded with AEFX.loopify so it loops while really rising). The eddies are strongest just above the fire and mix away toward the top (a vertical falloff) and the sides (edge). `output` picks what you render: \"map\" = the looping displacement map (opaque, 50% grey = no offset) for an engine distortion shader placed over the fire; \"shimmer\" = its schlieren image, brightness ~ the horizontal gradient of the index (the map minus itself shifted 2 px, Difference), tinted warm on black, for an additive Spine layer (mode=\"additive\"); \"preview\" = the map driving a Displacement Map over `image` (or a generated checkerboard) to judge the refraction in AE. Place the strip's BOTTOM edge on the top of the fire. Pair with fx_recipe recipe=heat_shimmer (anchor bone + ae_hint).","params":{"width":256,"height":384,"duration":2.0,"fps":24,"output":"shimmer","rise":160,"scale":26,"flatten":0.45,"complexity":3,"contrast":110,"base":0.92,"top":0.08,"edge":0.2,"strength":10,"shift":2,"gain":7,"color":"FFE8C8","glow":0.6,"image":"","seed":5}} */
var W = P.width, H = P.height, D = P.duration, name = P.comp || "heat_shimmer";
if (P.output !== "map" && P.output !== "shimmer" && P.output !== "preview") throw new Error("output must be map | shimmer | preview");
// 1. the refractive-index field: flattened eddies streaming up (run 2D, crossfaded into a D loop)
var src = AEFX.comp(name + "_src", W, H, P.fps, 2 * D);
src.layers.addSolid([0.5, 0.5, 0.5], "neutral", W, H, 1);
var n = src.layers.addSolid([0, 0, 0], "eddies", W, H, 1);
var fn = AEFX.fx(n, "ADBE Fractal Noise");
AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3);
AEFX.set(fn, "Contrast", P.contrast); AEFX.set(fn, "Brightness", 0);
AEFX.set(fn, "Uniform Scaling", 0);
AEFX.set(fn, "Scale Width", P.scale); AEFX.set(fn, "Scale Height", P.scale * P.flatten);    // eddies are wide and flat
AEFX.set(fn, "Complexity", P.complexity); AEFX.set(fn, "Random Seed", P.seed);
var ev = AEFX.find(fn, "Evolution"); ev.setValueAtTime(0, 0); ev.setValueAtTime(2 * D, 720);
AEFX.find(fn, "Offset Turbulence").expression = "[value[0], value[1] - time * " + P.rise + "]";   // the plume rises (AE y down)
var map = AEFX.loopify(src, name + "_map", D);
// envelope AFTER the crossfade: neutral grey (no offset) toward the top and the sides, full strength just above the fire
var fadeTop = map.layers.addSolid([0.5, 0.5, 0.5], "mixed_away", W, H, 1);
var fm = map.layers.addSolid([1, 1, 1], "mixed_away_matte", W, H, 1);
var rp = AEFX.fx(fm, "ADBE Ramp");
AEFX.set(rp, "ADBE Ramp-0001", [W / 2, H * P.top]); AEFX.set(rp, "ADBE Ramp-0002", [1, 1, 1, 1]);
AEFX.set(rp, "ADBE Ramp-0003", [W / 2, H * P.base]); AEFX.set(rp, "ADBE Ramp-0004", [0, 0, 0, 1]); AEFX.set(rp, "ADBE Ramp-0005", 1);
fadeTop.moveAfter(fm);
fadeTop.setTrackMatte(fm, TrackMatteType.LUMA);
fm.enabled = false;
var sides = map.layers.addSolid([0.5, 0.5, 0.5], "sides", W, H, 1);
var sm = sides.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
var ssh = new Shape(), ex = W * P.edge;
ssh.vertices = [[ex, -H], [W - ex, -H], [W - ex, H * 2], [ex, H * 2]]; ssh.closed = true;
sm.property("ADBE Mask Shape").setValue(ssh);
sm.property("ADBE Mask Feather").setValue([ex * 1.6, 0]);
sm.inverted = true;
var comp = AEFX.comp(name, W, H, P.fps, D);
var mode = "map";
if (P.output === "map") {
  comp.layers.add(map).name = "displacement_map";
} else if (P.output === "shimmer") {
  // schlieren: brightness ~ |dn/dx|, the map minus itself shifted a couple of px (Difference), boosted, tinted warm on black
  var a = comp.layers.add(map); a.name = "index";
  var b = comp.layers.add(map); b.name = "index_shifted";
  b.position.setValue([W / 2 + P.shift, H / 2]);
  b.blendingMode = BlendingMode.DIFFERENCE;
  var adj = comp.layers.addSolid([1, 1, 1], "schlieren", W, H, 1); adj.adjustmentLayer = true;
  var lv = AEFX.fx(adj, "ADBE Easy Levels2"); AEFX.set(lv, "Input White", Math.max(0.02, 1 / P.gain));
  var tt = AEFX.fx(adj, "ADBE Tritone");
  AEFX.set(tt, "Highlights", [1, 1, 1]); AEFX.set(tt, "Midtones", AEFX.rgb(P.color)); AEFX.set(tt, "Shadows", [0, 0, 0]);
  if (P.glow > 0) {
    var gf = AEFX.fx(adj, "ADBE Glo2");
    gf.property("Glow Threshold").setValue(40); gf.property("Glow Radius").setValue(W * 0.02); gf.property("Glow Intensity").setValue(P.glow);
  }
  var trim = comp.layers.addSolid([0, 0, 0], "trim", W, H, 1);   // the column the shifted copy leaves uncovered is not a gradient
  var tm = trim.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  var tsh = new Shape(), tx = Math.abs(P.shift) + 1;
  tsh.vertices = P.shift >= 0 ? [[0, 0], [tx, 0], [tx, H], [0, H]] : [[W - tx, 0], [W, 0], [W, H], [W - tx, H]]; tsh.closed = true;
  tm.property("ADBE Mask Shape").setValue(tsh);
  mode = "additive";
} else {
  var target;
  if (P.image) {
    target = comp.layers.add(app.project.importFile(new ImportOptions(new File(P.image))));
    target.scale.setValue([100 * W / target.width, 100 * H / target.height]);
  } else {
    target = comp.layers.addSolid([1, 1, 1], "checker", W, H, 1);
    var cb = AEFX.fx(target, "ADBE Checkerboard"); AEFX.set(cb, "Width", 16);
  }
  var ml = comp.layers.add(map); ml.name = "displacement_map"; ml.enabled = false;
  var dm = AEFX.fx(target, "ADBE Displacement Map");
  AEFX.set(dm, "Displacement Map Layer", ml.index);
  AEFX.set(dm, "Use For Horizontal Displacement", 5);            // 5 = Luminance
  AEFX.set(dm, "Max Horizontal Displacement", P.strength);
  AEFX.set(dm, "Use For Vertical Displacement", 5);
  AEFX.set(dm, "Max Vertical Displacement", P.strength * 0.35);
  AEFX.set(dm, "Displacement Map Behavior", 2);                  // 2 = Stretch Map to Fit
  mode = "alpha";
}
return AEFX.done(comp, '"mode":"' + mode + '","output":"' + P.output + '"');
