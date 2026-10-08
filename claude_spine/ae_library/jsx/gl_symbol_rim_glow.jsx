// gl_symbol_rim_glow: two light heads chasing around a rounded-square cell border. Seamless 1.2 s loop (30 frames).
// Each head: white-hot tapered core, gold body, orange-red fading tail (stacked Trim Paths strokes, colour
// temperature white -> gold -> orange -> red along the tail), soft bloom stroke, a star/flare glint riding the head
// (pointOnPath of the same path) and sparks shed from the head drifting outward. Faint resting frame glow.
// Centre is empty (transparent) so it sits over a symbol. Heads move half the perimeter per loop (2 heads => seamless).
$.evalFile(FXLIB_DIR + "gl_kit.jsx");
function BUILD(V) {
  var W = 512, H = 512, cx = 256, cy = 256, D = 1.2, E = 212, R = 58;
  RE.purge("gl_symbol_rim_glow_v");
  var tag = "gl_symbol_rim_glow_v" + V;
  var WHITE = FX.rgb("FFFDF2"), CREAM = FX.rgb("FFEFB8"), GOLD = FX.rgb("FFC93C"), AMBER = FX.rgb("FF9518"),
      ORANGE = FX.rgb("FF5E0A"), RED = FX.rgb("D8200A");
  var rnd = FX.rng(1200);

  // rounded-square path (clockwise from top centre), layer-space around (0,0)
  function framePath() {
    var k = 0.5523 * R, a = E - R, s = new Shape();
    s.vertices = [[0, -E], [a, -E], [E, -a], [E, a], [a, E], [-a, E], [-E, a], [-E, -a], [-a, -E]];
    s.inTangents = [[0, 0], [0, 0], [0, -k], [0, 0], [k, 0], [0, 0], [0, k], [0, 0], [-k, 0]];
    s.outTangents = [[0, 0], [k, 0], [0, 0], [0, k], [0, 0], [-k, 0], [0, 0], [0, -k], [0, 0]];
    s.closed = true; return s;
  }
  var b = GL.pre(tag + "_body", W, H, D);
  function strokeLayer(name, color, width, o) {
    var l = FX.shape(b, name); l.anchorPoint.setValue([0, 0]); l.position.setValue([cx, cy]);
    var g = FX.group(l, "path", { stroke: color, width: width, trim: !!o.len, taper: o.taper });
    g.path.setValue(framePath());
    if (o.len) {
      g.tStart.setValue(0); g.tEnd.setValue(o.len * 100);
      GL.ex(g.tOff, "360*(" + o.s0 + "+0.5*time/" + D + "-" + o.len + ")");
    }
    if (o.blur) FX.blur(l, o.blur);
    l.blendingMode = BlendingMode.ADD;
    if (o.op !== undefined) l.opacity.setValue(o.op);
    return l;
  }
  // path reference for glints / sparks (disabled, read by expressions)
  var ref = strokeLayer("path_ref", [1, 1, 1], 1, {}); ref.enabled = false;

  // resting frame glow (faint, breathing with the heads)
  var base = strokeLayer("frame_glow", AMBER, 10, { blur: 9, op: 22 });
  GL.breathOp(base, D, 20, 5, 2, 0);
  strokeLayer("frame_line", GOLD, 1.5, { blur: 0.6, op: 28 });

  for (var h = 0; h < 2; h++) {
    var s0 = h * 0.5 + 0.125, nm = "head" + h + "_";
    strokeLayer(nm + "tail_red", RED, 9, { len: 0.28, s0: s0, taper: [100, 0], blur: 7, op: 65 });
    strokeLayer(nm + "tail_orange", ORANGE, 6, { len: 0.19, s0: s0, taper: [100, 0], blur: 3, op: 85 });
    strokeLayer(nm + "body_gold", GOLD, 5, { len: 0.12, s0: s0, taper: [100, 0], blur: 1.2 });
    strokeLayer(nm + "bloom", AMBER, 28, { len: 0.09, s0: s0, taper: [100, 30], blur: 16, op: 55 });
    strokeLayer(nm + "core_white", WHITE, 3.5, { len: 0.05, s0: s0, taper: [100, 0], blur: 0.4 });
    var P = "var L=thisComp.layer(\"path_ref\");var pp=L.content(1).content(1).path;";
    var HEAD = "var s=" + s0 + "+0.5*time/" + D + ";s=s-Math.floor(s);";
    // glints riding the head
    var fl = GL.sprite(b, GL.K + "flare_01.png", nm + "flare", { color: GOLD, scale: 34 });
    GL.ex(fl.position, P + HEAD + "L.toComp(pp.pointOnPath(s))");
    GL.ex(fl.rotation, P + HEAD + "var t=pp.tangentOnPath(s);Math.atan2(t[1],t[0])*180/Math.PI");
    var st = GL.sprite(b, GL.K + "star_07.png", nm + "star", { color: WHITE });
    GL.ex(st.position, P + HEAD + "L.toComp(pp.pointOnPath(s))");
    GL.ex(st.scale, "var x=" + GL.breath(D, 13, 3, 6, h * 0.3) + ";[x,x]");
    GL.ex(st.rotation, "15+20*Math.sin(2*Math.PI*2*time/" + D + ")");
    var hb = GL.orb(b, nm + "hot", [0, 0], 9, WHITE, 100);
    GL.ex(hb.position, P + HEAD + "L.toComp(pp.pointOnPath(s))");
    // sparks shed from the head, drifting outward (normal to the frame) with slight gravity
    for (var k = 0; k < 14; k++) {
      var ph = (k + rnd() * 0.8) / 14, life = 0.22 + rnd() * 0.25, v = 40 + rnd() * 70, jx = (rnd() - 0.5) * 50, jy = (rnd() - 0.5) * 50;
      var sp = GL.sprite(b, GL.K + (k % 3 ? "circle_05.png" : "star_06.png"), nm + "spark" + k, { color: k % 2 ? GOLD : CREAM });
      var AGE = "var D=" + D + ",ph=" + ph + ",life=" + life + ";var a=time/D-ph;a=(a-Math.floor(a))*D;";
      GL.ex(sp.position, P + AGE + "var s=" + s0 + "+0.5*ph+" + (-0.004 * rnd()) + ";s=s-Math.floor(s);var p=L.toComp(pp.pointOnPath(s));" +
        "var d=normalize(sub(p,[" + cx + "," + cy + "]));add(add(p,mul(d," + v + "*a)),[" + jx + "*a," + jy + "*a+60*a*a])");
      GL.ex(sp.opacity, AGE + "a<life?100*Math.pow(1-a/life,1.4):0");
      var sz = k % 3 ? 2.2 + rnd() * 1.6 : 5 + rnd() * 3;
      GL.ex(sp.scale, AGE + "var x=" + sz + "*(1-0.5*a/life);[x,x]");
      sp.motionBlur = true;
    }
  }
  var gb = FX.adj(b, "bloom");
  FX.glow(gb, 10, 0.4, 60, GOLD, ORANGE);

  var c = GL.comp(tag, W, H, D);
  var bl = c.layers.add(b); bl.name = "body"; bl.blendingMode = BlendingMode.ADD;
  return FX.done(c);
}
