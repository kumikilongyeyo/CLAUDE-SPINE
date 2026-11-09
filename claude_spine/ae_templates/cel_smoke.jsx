/*TEMPLATE {"name":"cel_smoke","doc":"Cartoon CEL smoke in two flat tones (a base and a lighter highlight, never a gradient), the workflow read out of a commercial cel smoke pack's .aep (fx_recipe recipe=guide, section 'Cel smoke', has the full study). A SOFT source (generated here, or footage you pass as source=) goes through ONE stack: Transform squash -> CC Radial ScaleWipe (a hole opens from the inside) -> Minimax erode + early Minimax grow -> a Fast Box Blur that GROWS -> Levels on alpha (hard cel edge) -> two Turbulent Displace (big lumps, complexity 1) -> Extract on alpha. The blur grows while the threshold stays, so thin parts go first: it swells, hollows into a ring, breaks into crescents and slivers, and is gone by 90% of the duration. Base = a Fill copy; highlight = a copy shifted toward the light, eroded, displaced, re-thresholded and alpha-matted inside the base. A Bulge adjustment on top swells it (Twirl curls a plume, Optics Compensation wobbles a puff); fractal noise stencilled into the source (jag) cuts angular notches. style: explosion (cluster that bursts and hollows into crescents), puff (round ball that swells, wobbles and shrinks away, no hole), plume (a column pushed up from the floor that curls into a hook and thins to an arc). source: a .mov / sequence / still to RE-TREAT, the pack's own trick (every new smoke is an older render pushed through the stack again); source_key alpha or luma, source_speed 0 = stretched onto the duration. Pixel knobs are in the pack's 1080 px units, scaled to size. Built-in effects only. Transparent background (mode=\"alpha\"), one-shot.","params":{"style":"explosion","size":512,"duration":1.7,"fps":24,"base":"A29072","light":"C1AE90","seed":3,"lobes":7,"squash":46,"hollow":0.33,"erode":18,"round":59,"wobble":[96,110],"lump":254,"threshold":163,"softness":10,"swell":1.4,"light_angle":-125,"highlight":0.08,"highlight_erode":10,"twirl":-110,"pace":0.9,"grow":0.1,"jag":0.4,"rise":0.18,"source":"","source_key":"alpha","source_speed":0}} */
var W = P.size, D = P.duration, name = P.comp || ("cel_smoke_" + P.style);
var k = W / 1080;                       // the pack's comps are ~1080 px: every pixel number is scaled by k
// the pack's key times sit on a 1.71 s render whose source is already time-remapped: pace < 1 plays the stack faster
var T = function (t) { return Math.min(D, t * D / 1.71 * P.pace * (P.style === "plume" ? 0.72 : 1)); };   // plumes thin out faster
var thr = P.threshold / 255, soft = Math.max(1, P.softness) / 255;
// Extract only REMOVES pixels below the threshold; the kept ones keep their blurred alpha (soft edge). The pack hardens
// them with Curves (unreadable from script); Levels on alpha around the same threshold does the same job.
var harden = function (layer) {
  var lv = AEFX.fx(layer, "ADBE Pro Levels2");
  AEFX.set(lv, "Alpha Input Black", Math.max(0, thr - soft)); AEFX.set(lv, "Alpha Input White", Math.min(1, thr + soft));
  return lv;
};
var style = P.style;
if (style !== "explosion" && style !== "puff" && style !== "plume") throw new Error("style must be explosion, puff or plume, not " + style);
var rnd = AEFX.rng(P.seed + 41);
var cx = W / 2, cy = W / 2;

// 1. SOURCE: a soft alpha mass. The pack starts from a soft pre-rendered fireball ("CEL explosion mushroom"); here a
//    cluster of blurred ellipses does the same job. Any footage passed as source= replaces it (re-treatment).
var src = AEFX.comp(name + "_source", W, W, P.fps, D);
if (P.source) {
  var it = AEFX.imp(P.source);
  var fl = src.layers.add(it);
  var fit = 100 * Math.min(W / it.width, W / it.height);
  fl.scale.setValue([fit, fit]);
  if (it.duration > 0) {   // source_speed 0: the whole footage stretched onto the duration; else play at that speed
    fl.timeRemapEnabled = true;
    var tr = fl.property("ADBE Time Remapping"), last = Math.max(0, it.duration - 1 / P.fps);
    AEFX.keys(tr, [[0, 0], [D, P.source_speed > 0 ? Math.min(last, D * P.source_speed) : last]], false);
  }
  if (P.source_key === "luma") {                // a render on black: alpha from luminance
    var sh = AEFX.fx(fl, "ADBE Shift Channels");
    AEFX.set(sh, "Take Alpha From", 5);
  }
} else {
  var blob = AEFX.shape(src, "mass");
  var lobes = style === "puff" ? 1 : P.lobes;
  for (var lb = 0; lb < lobes; lb++) {
    var big = style === "plume" ? 0.3 + 0.06 * rnd() : (lb === 0 ? 0.5 : 0.22 + 0.12 * rnd());
    var e = AEFX.ellipse(blob, W * big * (style === "puff" ? 1.1 : 1), [1, 1, 1], null, 0);
    var vg = blob.property("ADBE Root Vectors Group");
    var g = vg.property(vg.numProperties).property("ADBE Vector Transform Group");
    if (style === "plume") {                                // a column leaning up-right from the floor point
      var u = lobes > 1 ? lb / (lobes - 1) : 0;
      g.property("ADBE Vector Position").setValue([W * (0.34 * u + (rnd() - 0.5) * 0.06), -W * (0.08 + 0.5 * u)]);
      g.property("ADBE Vector Scale").setValue([100 - 45 * u, 100 - 45 * u]);
    } else if (lb > 0) {
      var a = lb / lobes * Math.PI * 2 + (rnd() - 0.5) * 0.8, dd = W * (0.13 + 0.08 * rnd());
      g.property("ADBE Vector Position").setValue([Math.cos(a) * dd, Math.sin(a) * dd]);
    }
  }
  if (style === "plume") {                                  // the floor skid the pack's plumes leave behind
    AEFX.ellipse(blob, W * 0.2, [1, 1, 1], null, 0);
    var fg = blob.property("ADBE Root Vectors Group"); fg = fg.property(fg.numProperties).property("ADBE Vector Transform Group");
    fg.property("ADBE Vector Scale").setValue([260, 34]); fg.property("ADBE Vector Position").setValue([-W * 0.08, -W * 0.02]);
  }
  var gb = AEFX.fx(blob, "ADBE Gaussian Blur 2");
  AEFX.set(gb, "Blurriness", W * 0.05);
  AEFX.set(gb, "Repeat Edge Pixels", 0);
  // burst: fast swell that drag brings to a crawl (puff then shrinks away: the pack keys its scale down to ~1 %)
  var sk = [], pk = [], N = 12;
  for (var q = 0; q <= N; q++) {
    var f = q / N, sw = 1 - Math.pow(1 - Math.min(1, f / (style === "puff" ? 1.6 * P.grow : P.grow)), 3), s;
    if (style === "puff") s = 18 + 92 * sw - (f > 0.45 ? 104 * Math.pow((f - 0.45) / 0.55, 1.6) : 0);
    else s = 12 + 90 * sw;
    s = Math.max(1, s);
    sk.push([D * f, style === "plume" ? [s * 1.15, s] : [s, s]]);
    var px = cx, py = cy - W * P.rise * (1 - Math.pow(1 - f, 2));
    if (style === "plume") { px = W * (0.3 + 0.05 * sw); py = W * (0.8 - 0.04 * sw); }
    pk.push([D * f, [px, py]]);
  }
  AEFX.keys(blob.scale, sk, false);
  AEFX.keys(blob.position, pk, false);
}
if (P.jag > 0) {
  // texture inside the soft mass (the pack's Lrg explosion: blur -> Turbulent Noise -> Extract): noise stencils the
  // alpha so the later threshold cuts angular notches and holes instead of smooth round edges
  var nz = src.layers.addSolid([1, 1, 1], "jag_noise", W, W, 1);
  var fn = AEFX.fx(nz, "ADBE Fractal Noise");
  AEFX.set(fn, "Fractal Type", 1); AEFX.set(fn, "Noise Type", 3); AEFX.set(fn, "Complexity", 1);
  AEFX.set(fn, "Contrast", 168); AEFX.set(fn, "Brightness", 100 - 100 * P.jag);
  AEFX.set(fn, "Scale", 1.6 * P.lump * k); AEFX.set(fn, "Random Seed", P.seed);
  var nev = AEFX.find(fn, "Evolution"); nev.setValueAtTime(0, 0); nev.setValueAtTime(D, 140);
  nz.blendingMode = BlendingMode.STENCIL_LUMA;
}

// 2. CEL: the pack's master stack ("Base 1.1" of Explosion simple), every number from the .aep, scaled by k
var cel = AEFX.comp(name + "_cel", W, W, P.fps, D);
var L = cel.layers.add(src); L.name = "soft_source";
var tf = AEFX.fx(L, "ADBE Geometry2");                       // squash: born flat, springs to full height
AEFX.set(tf, "Uniform Scale", 0);
var shp = AEFX.find(tf, "Scale Height");
AEFX.keys(shp, [[0, style === "explosion" ? P.squash : 100], [T(0.833), 100]], true);
AEFX.set(tf, "Anchor Point", [cx, cy]); AEFX.set(tf, "Position", [cx, cy]);
if (P.hollow > 0 && style === "explosion") {    // a hole opens from the inside and eats outward (puff shrinks, plume thins)
  var rw = AEFX.fx(L, "CC Radial ScaleWipe");
  var hj = W * 0.11;                                         // the hole is never dead centre: the ring breaks unevenly
  AEFX.set(rw, "Center", [cx + (rnd() - 0.5) * 2 * hj, cy - W * P.rise * 0.5 + (rnd() - 0.5) * 2 * hj]);
  AEFX.keys(AEFX.find(rw, "Completion"), [[T(0.04), 0], [T(0.45), P.hollow * 0.6], [T(1.5), P.hollow]], false);   // opens at once, then creeps
}
var m1 = AEFX.fx(L, "ADBE Minimax");                         // erode: thins everything, thin parts vanish first
AEFX.set(m1, "Operation", 1); AEFX.set(m1, "Channel", 2);
AEFX.keys(AEFX.find(m1, "Radius"), [[T(0.167), 0], [T(1.42), Math.max(1, Math.round(P.erode * k * (style === "puff" ? 0.5 : style === "plume" ? 1.4 : 1)))],
  [Math.max(T(1.42) + 0.05, D * 0.9), Math.round(P.erode * k * (style === "puff" ? 3 : 7))]], true);   // and eats every last sliver by the end
var m2 = AEFX.fx(L, "ADBE Minimax");                         // grow early (fat start), released later
AEFX.set(m2, "Operation", 2); AEFX.set(m2, "Channel", 2);
AEFX.keys(AEFX.find(m2, "Radius"), [[T(0.657), Math.round(6 * k)], [T(2.34), 0]], true);
var bb = AEFX.fx(L, "ADBE Box Blur2");                       // rounding that grows: blobs merge, slivers drop out
AEFX.set(bb, "Iterations", 1);
AEFX.keys(AEFX.find(bb, "Blur Radius"), [[T(0.208), 0], [T(1.83), P.round * k]], true);
harden(L);
var td1 = AEFX.fx(L, "ADBE Turbulent Displace");             // big lumps, complexity 1, growing
AEFX.set(td1, "Size", P.lump * k); AEFX.set(td1, "Complexity", 1); AEFX.set(td1, "Pinning", 3);
AEFX.set(td1, "Evolution", P.seed * 37);
AEFX.keys(AEFX.find(td1, "Amount"), [[0, 0], [T(1.75), P.wobble[0] * k]], false);
var td2 = AEFX.fx(L, "ADBE Turbulent Displace");             // second pass, other evolution, half strength
AEFX.set(td2, "Size", P.lump * k); AEFX.set(td2, "Complexity", 1); AEFX.set(td2, "Pinning", 3);
AEFX.set(td2, "Evolution", 293 + P.seed * 37);
AEFX.keys(AEFX.find(td2, "Amount"), [[0, 0], [T(1.71), P.wobble[1] * k]], true);
AEFX.find(td2, "Effect Opacity").setValue(50);
var ex = AEFX.fx(L, "ADBE Extract");                         // the cel edge: threshold the alpha every frame
AEFX.set(ex, "Channel", 5); AEFX.set(ex, "Black Point", P.threshold); AEFX.set(ex, "Black Softness", P.softness);

// 3. TWO TONES (Floor plume / Mini puff comps): base = a Fill copy; highlight = a copy shifted toward the light,
//    eroded, blurred and re-Extracted so it stays round, alpha-matted to the base so a base rim shows on the shadow side
var comp = AEFX.comp(name, W, W, P.fps, D);
var hm = comp.layers.add(cel); hm.name = "highlight_matte";
var hl = comp.layers.add(cel); hl.name = "highlight"; hl.moveAfter(hm);
var la = P.light_angle * Math.PI / 180, off = W * P.highlight;
hl.position.setValue([cx + Math.cos(la) * off, cy + Math.sin(la) * off]);
var hmm = AEFX.fx(hl, "ADBE Minimax");
AEFX.set(hmm, "Operation", 1); AEFX.set(hmm, "Channel", 2); AEFX.set(hmm, "Radius", Math.max(1, Math.round(P.highlight_erode * k)));
var htd = AEFX.fx(hl, "ADBE Turbulent Displace");            // the pack's highlight copies wander: own displacement
AEFX.set(htd, "Size", 150 * k); AEFX.set(htd, "Complexity", 1); AEFX.set(htd, "Amount", 40);
AEFX.keys(AEFX.find(htd, "Evolution"), [[0, 60 + P.seed * 11], [D, 160 + P.seed * 11]], false);
var hbb = AEFX.fx(hl, "ADBE Box Blur2"); AEFX.set(hbb, "Blur Radius", 16 * k); AEFX.set(hbb, "Iterations", 3);
var hex_ = AEFX.fx(hl, "ADBE Extract");
AEFX.set(hex_, "Channel", 5); AEFX.set(hex_, "Black Point", 140); AEFX.set(hex_, "Black Softness", 9);
harden(hl);
AEFX.set(AEFX.fx(hl, "ADBE Fill"), "Color", AEFX.rgb(P.light));
hl.setTrackMatte(hm, TrackMatteType.ALPHA);
hm.enabled = false;
var bs = comp.layers.add(cel); bs.name = "base"; bs.moveAfter(hl);
AEFX.set(AEFX.fx(bs, "ADBE Fill"), "Color", AEFX.rgb(P.base));

// 4. SHAPE PASS on top (every final comp in the pack): Bulge swells the mass outward, so the hole grows into a ring;
//    plume curls over with Twirl; puff wobbles with Optics Compensation
var adj = comp.layers.addSolid([1, 1, 1], "bulge", W, W, 1); adj.adjustmentLayer = true; adj.moveToBeginning();
var bc = style === "plume" ? [W * 0.33, W * 0.72] : [cx, cy];
if (style === "plume") {
  var tw = AEFX.fx(adj, "ADBE Twirl");
  AEFX.set(tw, "Twirl Center", [W * 0.64, W * 0.36]); AEFX.set(tw, "Twirl Radius", 38);
  AEFX.keys(AEFX.find(tw, "Angle"), [[T(0.04), 0], [T(0.9), P.twirl]], true);
}
var bu = AEFX.fx(adj, "ADBE Bulge");
AEFX.set(bu, "Horizontal Radius", W * (style === "plume" ? 0.9 : 0.44)); AEFX.set(bu, "Vertical Radius", W * (style === "plume" ? 0.8 : 0.43));
AEFX.set(bu, "Bulge Center", bc); AEFX.set(bu, "Antialiasing (Best Qual Only)", 2);
AEFX.keys(AEFX.find(bu, "Bulge Height"), [[T(0.083), 0], [T(1.33), P.swell]], true);
if (style === "puff") {
  var oc = AEFX.fx(adj, "ADBE Optics Compensation");
  AEFX.set(oc, "View Center", [cx, cy]);
  AEFX.keys(AEFX.find(oc, "Field Of View (FOV)"), [[T(0.35), 0], [T(1.0), 70], [T(1.6), 0]], true);
}
return AEFX.done(comp, '"mode":"alpha","style":"' + style + '"');
