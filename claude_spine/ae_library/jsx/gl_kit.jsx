// gl_kit: shared helpers for the gl_ (realistic glow) set. Loaded by gl_*.jsx after fxlib.jsx (run.jsx loads it).
// Every loop uses time-periodic expressions (period D) so frame N == frame 0; one-shots use plain keys.
// TRAP: the shared ExtendScript engine has an Array "+" operator overload (from another script): "" + [1,2] throws
// "invalid numeric result". Always .join(",") arrays before concatenating them into expression strings.
$.evalFile(FXLIB_DIR + "re_kit.jsx");
var GL = {};
GL.K = RE.K; GL.R = RE.R; GL.KS = RE.KS;

GL.comp = function (name, w, h, dur) { return RE.comp(name, w, h, dur); };
GL.pre = function (name, w, h, dur) {          // precomp (same folder, motion blur on)
  var c = RE.comp(name, w, h, dur); return c;
};
GL.ex = function (prop, code) { prop.expression = code; return prop; };
// u = loop phase 0..1 of a cycle that repeats k times per D, shifted by ph
GL.U = function (D, k, ph) { return "var D=" + D + ",k=" + k + ",ph=" + ph + ";var u=time/D*k+ph;u=u-Math.floor(u);"; };
// smoothstep in expressions
GL.SS = "function ss(a,b,x){x=Math.max(0,Math.min(1,(x-a)/(b-a)));return x*x*(3-2*x);}";

// white-on-alpha sprite (Kenney) coloured with Fill, additive by default
GL.sprite = function (comp, path, name, o) {
  o = o || {};
  var l;
  if (typeof path === "string") l = RE.tex(comp, path, name, o);
  else {                                        // a precomp / footage item instead of a file path
    l = comp.layers.add(path); l.name = name;
    if (o.pos) l.position.setValue(o.pos);
    if (o.scale !== undefined) l.scale.setValue(o.scale instanceof Array ? o.scale : [o.scale, o.scale]);
    l.blendingMode = o.blend === undefined ? BlendingMode.ADD : o.blend;
    if (o.op !== undefined) l.opacity.setValue(o.op);
  }
  if (o.color) RE.fill(l, o.color);
  if (o.blur) FX.blur(l, o.blur);
  return l;
};
// photo with luma -> colour ramp (Tritone)
GL.tritone = function (l, hi, mid, lo) {
  var t = FX.fx(l, "ADBE Tritone");
  function c4(c) { return [c[0], c[1], c[2], 1]; }
  FX.set(t, "Highlights", c4(hi)); FX.set(t, "Midtones", c4(mid)); FX.set(t, "Shadows", c4(lo || [0, 0, 0]));
  return t;
};
// a periodic "mote": lives k times per loop, moves p0 -> p1 (+sway), scales s0 -> s1, fades in/out.
// o = {D, k, ph, p0, p1, sway:[ampX, cycles], s0, s1, op, fin, fout, rot:[r0, r1], flick}
GL.mote = function (comp, path, name, o) {
  var l = GL.sprite(comp, path, name, { color: o.color, blend: o.blend, blur: o.blur });
  var u = GL.U(o.D, o.k || 1, o.ph || 0);
  var sw = o.sway || [0, 1];
  GL.ex(l.position, u + "var a=[" + o.p0.join(",") + "],b=[" + o.p1.join(",") + "];var s=" + sw[0] + "*Math.sin(2*Math.PI*(u*" + sw[1] + "+" + (o.swph || 0) + "));" +
    "[a[0]+(b[0]-a[0])*u+s, a[1]+(b[1]-a[1])*u]");
  var s0 = o.s0 === undefined ? 10 : o.s0, s1 = o.s1 === undefined ? s0 : o.s1;
  var sx = o.sx || 1, sy = o.sy || 1;
  GL.ex(l.scale, u + "var s=" + s0 + "+(" + (s1 - s0) + ")*u;[s*" + sx + ",s*" + sy + "]");
  GL.ex(l.opacity, u + GL.SS + "var e=ss(0," + (o.fin || 0.15) + ",u)*(1-ss(" + (1 - (o.fout || 0.4)) + ",1,u));" +
    (o.flick ? "e*=1-" + o.flick + "*(0.5+0.5*Math.sin(2*Math.PI*(u*" + (o.flickN || 5) + ")));" : "") +
    (o.op === undefined ? 100 : o.op) + "*e");
  if (o.rot) GL.ex(l.rotation, u + o.rot[0] + "+(" + (o.rot[1] - o.rot[0]) + ")*u");
  return l;
};
// periodic flash (twinkle): a short burst at phase ph of the loop. o = {D, ph, len (fraction of loop), pos, s, op, rot}
GL.twinkle = function (comp, path, name, o) {
  var l = GL.sprite(comp, path, name, { color: o.color, pos: o.pos });
  var u = GL.U(o.D, o.k || 1, o.ph || 0);
  var len = o.len || 0.18;
  GL.ex(l.opacity, u + "var x=u/" + len + ";var e=x<1?Math.pow(Math.sin(Math.PI*x),2):0;" + (o.op || 100) + "*e");
  GL.ex(l.scale, u + "var x=Math.min(1,u/" + len + ");var s=" + (o.s || 20) + "*(0.35+0.65*Math.sin(Math.PI*x));[s,s]");
  GL.ex(l.rotation, u + (o.rot || 0) + "+40*Math.min(1,u/" + len + ")");
  return l;
};
// seamless slow rotation of a layer source: two copies, copy B one loop behind, linear crossfade
// (O(t) = (1-t/D) X(t) + (t/D) X(t-D)  ->  O(D) = X(0)). deg = rotation per loop. Returns [a, b].
GL.loopRot = function (comp, src, name, D, deg, o) {
  o = o || {};
  var res = [];
  for (var i = 0; i < 2; i++) {
    var l = comp.layers.add(src); l.name = name + (i ? "_b" : "_a");
    l.blendingMode = o.blend === undefined ? BlendingMode.ADD : o.blend;
    if (o.pos) l.position.setValue(o.pos);
    if (o.anchor) l.anchorPoint.setValue(o.anchor);
    if (o.scale) l.scale.setValue([o.scale, o.scale]);
    var base = o.rot0 || 0;
    GL.ex(l.rotation, "var D=" + D + ";var t=time-Math.floor(time/D)*D;" + base + "+" + deg + "*(t" + (i ? "-D" : "") + ")/D");
    var op = o.op === undefined ? 100 : o.op;
    GL.ex(l.opacity, "var D=" + D + ";var t=time-Math.floor(time/D)*D;" + op + "*" + (i ? "t/D" : "(1-t/D)"));
    res.push(l);
  }
  return res;
};
// breathing value expression: base + amp * sin(2pi (n t / D + ph))
GL.breath = function (D, base, amp, n, ph) {
  return "(" + base + ")+(" + amp + ")*Math.sin(2*Math.PI*(" + (n || 1) + "*time/" + D + "+" + (ph || 0) + "))";
};
GL.breathScale = function (l, D, base, amp, n, ph) { GL.ex(l.scale, "var s=" + GL.breath(D, base, amp, n, ph) + ";[s,s]"); };
GL.breathOp = function (l, D, base, amp, n, ph) { GL.ex(l.opacity, GL.breath(D, base, amp, n, ph)); };
// elliptical feathered mask in LAYER coordinates
GL.ellipse = function (l, cx, cy, rx, ry, feather, mode) {
  var k = 0.5523, s = new Shape();
  s.vertices = [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]];
  s.inTangents = [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]];
  s.outTangents = [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]];
  s.closed = true;
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([feather, feather]);
  if (mode) m.maskMode = mode;
  return m;
};
GL.rectMask = function (l, x0, y0, x1, y1, feather, mode) {
  var s = new Shape(); s.vertices = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]; s.closed = true;
  var m = l.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
  m.property("ADBE Mask Shape").setValue(s);
  m.property("ADBE Mask Feather").setValue([feather, feather]);
  if (mode) m.maskMode = mode;
  return m;
};
// soft radial light (Kenney circle_05 = smooth gaussian-ish dot), coloured, additive
GL.orb = function (comp, name, pos, scale, color, op) {
  return GL.sprite(comp, GL.K + "circle_05.png", name, { pos: pos, scale: scale, color: color, op: op === undefined ? 100 : op });
};
// 1/t style impact falloff keys: I(t) = 1/(1 + t/tau), forced to 0 at tEnd. Returns [[t, v*peak]...]
GL.falloff = function (t0, tau, tEnd, peak, steps) {
  var k = [], n = steps || 12;
  if (t0 > 0.002) k.push([t0 - 0.001, 0]);
  for (var i = 0; i <= n; i++) {
    var t = t0 + (tEnd - t0) * i / n, x = (t - t0) / (tEnd - t0);
    var v = 1 / (1 + (t - t0) / tau) * (1 - x * x * x);
    k.push([t, Math.max(0, Math.min(100, peak * v))]);
  }
  return k;
};
// volumetric rays precomp: a noisy disc (fractal noise through a blurred ellipse matte) streaked outward by
// CC Light Rays on an adjustment layer. Loops when o.cycle (noise evolution cycles o.revs times over D).
// o = {r, blurM, scale, contrast, bright, revs, cycle, intensity, radius, soft, sw, sh, intensityKeys, rKeys}
GL.rays = function (name, W, H, D, o) {
  var src = GL.pre(name + "src", W, H, D), cx = W / 2, cy = H / 2;
  var n = FX.noise(src, "ray_noise", { type: o.type || 1, noise: o.noiseType || 4, contrast: o.contrast || 200, brightness: o.bright || -20,
    scale: o.scale || 30, sw: o.sw, sh: o.sh, complexity: o.complexity || 3, seed: o.seed || 11,
    evo: [[0, 0], [D, 360 * (o.revs || 1)]] });
  if (o.cycle) { FX.set(n.fx, "Cycle Evolution", 1); FX.set(n.fx, "Cycle (in Revolutions)", o.revs || 1); }
  var m = FX.shape(src, "disc_matte");
  var g = o.ring ? FX.group(m, "ellipse", { size: [o.r * 2, o.r * 2], stroke: [1, 1, 1], width: o.ring })
                 : FX.group(m, "ellipse", { size: [o.r * 2, o.r * 2], fill: [1, 1, 1] });
  m.position.setValue([cx, cy]);
  if (o.rKeys) { var kk = []; for (var i = 0; i < o.rKeys.length; i++) kk.push([o.rKeys[i][0], [o.rKeys[i][1] * 2, o.rKeys[i][1] * 2]]); FX.keys(g.size, kk, o.rEase || false); }
  FX.blur(m, o.blurM || o.r * 0.35);
  m.moveBefore(n.layer);
  FX.matte(n.layer, m, false);
  var c = GL.pre(name, W, H, D);
  GL.opaque(c);
  var a = c.layers.add(src); a.name = "ray_source";
  var lr = FX.fx(a, "CC Light Rays");
  FX.set(lr, "Center", [cx, cy]);
  FX.set(lr, "Radius", o.radius || 60);
  FX.set(lr, "Warp Softness", o.soft === undefined ? 50 : o.soft);
  var ip = FX.set(lr, "Intensity", o.intensity || 200);
  if (o.intensityKeys) FX.keys(ip, o.intensityKeys, o.iEase || false);
  if (o.radiusKeys) FX.keys(FX.find(lr, "Radius"), o.radiusKeys, false);
  return c;
};

// bokeh disc precomp (filled disc + brighter rim, slightly soft), white, size px
GL.bokehDisc = function (name, size, D) {
  var c = GL.pre(name, size + 8, size + 8, D);
  var l = FX.shape(c, "disc");
  FX.group(l, "ellipse", { size: [size, size], fill: [1, 1, 1] }).fillO.setValue(55);
  FX.group(l, "ellipse", { size: [size - 2, size - 2], stroke: [1, 1, 1], width: Math.max(1.5, size * 0.06) }).strokeO.setValue(90);
  l.position.setValue([(size + 8) / 2, (size + 8) / 2]);
  FX.blur(l, Math.max(0.8, size * 0.03));
  return c;
};
// wrap a body comp into the final comp with a feathered round vignette so the frame edge is pure black
GL.vignette = function (comp, body, cx, cy, rx, ry, feather) {
  var l = comp.layers.add(body); l.name = "body"; l.blendingMode = BlendingMode.ADD;
  GL.ellipse(l, cx, cy, rx, ry, feather);
  return l;
};
// procedural god-ray fan precomp: n wedges from the centre, each a radial white->black gradient (black adds no
// light), random length / angular width, per-ray periodic shimmer (integer cycles per D => loops).
// o = {n, seed, len:[min,max], wdeg:[min,max], flick (0..1), blur, cycles}
GL.shapeRays = function (name, W, H, D, o) {
  var c = GL.pre(name, W, H, D), rnd = FX.rng(o.seed || 1);
  var l = FX.shape(c, "rays"); l.position.setValue([W / 2, H / 2]);
  var root = l.property("ADBE Root Vectors Group");
  for (var i = 0; i < o.n; i++) {
    var ang = (i + rnd() * 0.8) * 360 / o.n, L = o.len[0] + rnd() * (o.len[1] - o.len[0]);
    var wd = (o.wdeg[0] + rnd() * (o.wdeg[1] - o.wdeg[0])) * Math.PI / 180, hw = Math.tan(wd / 2) * L;
    var g = root.addProperty("ADBE Vector Group"); var gi = root.numProperties;
    var cc = g.property("ADBE Vectors Group");
    cc.addProperty("ADBE Vector Shape - Group");
    cc.addProperty("ADBE Vector Graphic - G-Fill");
    g = l.property("ADBE Root Vectors Group").property(gi); cc = g.property("ADBE Vectors Group");
    var s = new Shape(); s.vertices = [[0, 0], [L, -hw], [L * 1.02, 0], [L, hw]]; s.closed = true;
    cc.property("ADBE Vector Shape - Group").property("ADBE Vector Shape").setValue(s);
    var gf = cc.property("ADBE Vector Graphic - G-Fill");
    gf.property("ADBE Vector Grad Type").setValue(2);
    gf.property("ADBE Vector Grad Start Pt").setValue([0, 0]);
    gf.property("ADBE Vector Grad End Pt").setValue([L, 0]);
    var tr = g.property("ADBE Vector Transform Group");
    tr.property("ADBE Vector Rotation").setValue(ang);
    var base = 45 + rnd() * 55, fl = (o.flick || 0.4) * base, ncy = 1 + Math.floor(rnd() * (o.cycles || 2)), ph = rnd();
    tr.property("ADBE Vector Group Opacity").expression = base + "-" + fl + "*(0.5+0.5*Math.sin(2*Math.PI*(" + ncy + "*time/" + D + "+" + ph + ")))";
  }
  if (o.blur) FX.blur(l, o.blur);
  GL.lumaAlpha(l);      // the gradient's black end is opaque: make alpha follow the light so nothing dark composites
  return c;
};
// alpha := luminance (keeps colour): dim / black parts of photos and gradients stop carrying alpha
// opaque black solid at the bottom of a comp: needed before GL.lumaAlpha on its output (transparent pixels keep
// hidden colour, e.g. noise outside a track matte, which lumaAlpha would bring back)
GL.opaque = function (comp) { var s = FX.solid(comp, "black_base", [0, 0, 0]); s.moveToEnd(); return s; };
GL.lumaAlpha = function (l) { var sc = FX.fx(l, "ADBE Shift Channels"); FX.set(sc, "Take Alpha From", 5); return sc; };
// A ready/ photo as clean light. The photos are straight RGBA (black unmultiplied), so recolouring them directly
// turns saturated-but-faint pixels into dark opaque smudges. Instead: photo (masked) over an opaque black solid in
// its own precomp = the real light; the caller recolours that (Tritone on true luminance) and GL.lumaAlpha() makes
// alpha follow the light. masks: [[cx, cy, rx, ry, feather, mode], ...] in photo pixels (mode "sub" = subtract).
GL.photoSrc = function (name, path, D, masks) {
  var it = FX.imp(path);
  var pc = GL.pre(name, it.width, it.height, D);
  FX.solid(pc, "black", [0, 0, 0]);
  var l = pc.layers.add(it); l.name = "photo";
  for (var i = 0; i < (masks || []).length; i++) {
    var m = masks[i];
    if (m[0] === "rect") GL.rectMask(l, m[1], m[2], m[3], m[4], m[5], m[6] === "sub" ? MaskMode.SUBTRACT : MaskMode.ADD);
    else GL.ellipse(l, m[0], m[1], m[2], m[3], m[4], m[5] === "sub" ? MaskMode.SUBTRACT : MaskMode.ADD);
  }
  return pc;
};
GL.photoLight = function (l, hi, mid, lo) {
  if (hi) GL.tritone(l, hi, mid, lo || [0, 0, 0]);
  GL.lumaAlpha(l);
  l.blendingMode = BlendingMode.ADD;
  return l;
};
