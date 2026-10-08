// fs_transition (clip B 4.12-5.42): the white-pink full-screen flash into the free-spins scene, then the sunburst
// switching on behind the "5". ADDITIVE, full frame 1556x1740, comp t = clip t - 4.12. Measured (frame mean RGB):
// 4.155 (58,38,37) dark dip | 4.229 bloom starts at (810,790) | 4.267 white bloom r~490 (28% of px > 230) |
// 4.306-4.344 peak, white -> lavender full screen (212,192,217)->(225,183,228) | 4.383-4.5 the added light is VIOLET
// (delta vs the new scene ~ (56,39,101) -> (17,1,28)); the pink look is the scene under it |
// 4.55 clear | 4.586 -> 4.621 sunburst ON in one frame, extra bright 4.7-4.8, settles by 5.0.
// The sunburst is cb_sunburst_loop_v<SBV> nested so that its loop time is 0 at this comp's end (hand-off to the loop).
// The dark dip (black 45 %, clip 4.14-4.27) cannot be additive: it is a NORMAL layer here, disabled by default
// (`dip` - enable it or key a black slot in Spine).
var SBV = 6;
function BUILD(V) {
  var W = 1556, H = 1740, D = 1.3, FPS = 30, BX = 810, BY = 780, CX = 780, CY = 540;
  var name = "cb_fs_transition_v" + V;
  var c = FX.comp(name, W, H, FPS, D);
  var WHITE = [1, 1, 1], LAV = FX.rgb("E0D8FF"), LILAC = [0.75, 0.62, 1], VIOLET = [0.55, 0.35, 1];
  function T(clip) { return clip - 4.12; }

  // sunburst (bottom)
  var sbc = null;
  for (var i = 1; i <= app.project.numItems; i++) { var it = app.project.item(i); if (it instanceof CompItem && it.name === "cb_sunburst_loop_v" + SBV) sbc = it; }
  if (!sbc) throw new Error("build cb_sunburst_loop_v" + SBV + " first");
  var sb = c.layers.add(sbc); sb.name = "sunburst";
  sb.startTime = D - sbc.duration;                       // loop time 0 at the end of this comp
  sb.anchorPoint.setValue([CX, CY]); sb.position.setValue([CX, CY]);
  sb.blendingMode = BlendingMode.ADD;
  FX.keys(sb.opacity, [[T(4.595), 0], [T(4.615), 100]], false);
  FX.keys(sb.scale, [[T(4.595), [70, 70]], [T(4.65), [100, 100]]], "out");
  // the burst over-brightens right after it switches on (4.7-4.8), then settles
  var boost = FX.ramp(c, "on_boost", CX, CY, 900, [1, 0.86, 0.45, 1], [0, 0, 0, 1], BlendingMode.ADD);
  FX.keys(boost.layer.opacity, [[T(4.6), 0], [T(4.62), 35], [T(4.72), 45], [T(4.85), 25], [T(5.05), 0]], false);

  // flash: a bloom from the centre that swells to the whole frame
  var core = FX.ramp(c, "bloom_core", BX, BY, 200, [1, 1, 1, 1], [0, 0, 0, 1], BlendingMode.ADD);
  FX.rampRadius(core, BX, BY, [[T(4.20), 150], [T(4.229), 450], [T(4.267), 800], [T(4.306), 1000], [T(4.344), 1100], [T(4.42), 1150]]);
  FX.keys(core.layer.opacity, [[T(4.195), 0], [T(4.229), 85], [T(4.267), 100], [T(4.306), 90], [T(4.344), 60], [T(4.383), 30], [T(4.44), 0]], false);
  var cf = FX.fx(core.layer, "ADBE Fill");          // colour: white -> lavender -> pink
  FX.keys(FX.find(cf, "Color"), [[T(4.267), WHITE], [T(4.306), LAV], [T(4.344), LILAC], [T(4.383), VIOLET]], false);
  // ADBE Fill would flatten the ramp: keep the luminance by taking the ramp as alpha first
  var csc = FX.fx(core.layer, "ADBE Shift Channels"); FX.set(csc, "Take Alpha From", 5);
  csc.moveTo(2);                                    // after the Ramp, before the Fill
  // full-screen haze
  var haze = FX.solid(c, "haze", WHITE);
  haze.blendingMode = BlendingMode.ADD;
  var hf = FX.fx(haze, "ADBE Fill");
  FX.keys(FX.find(hf, "Color"), [[T(4.267), WHITE], [T(4.306), LAV], [T(4.344), LILAC], [T(4.383), VIOLET]], false);
  FX.keys(haze.opacity, [[T(4.21), 0], [T(4.229), 8], [T(4.267), 30], [T(4.306), 35], [T(4.344), 40], [T(4.383), 38], [T(4.42), 28], [T(4.46), 18], [T(4.5), 10], [T(4.56), 0]], false);
  // glitter in the bloom
  var rnd = FX.rng(5);
  for (var k = 0; k < 26; k++) {
    var s = FX.shape(c, "flash_glint" + k), L = 10 + rnd() * 22;
    FX.group(s, "path", { points: [[-L, 0], [L, 0]], stroke: WHITE, width: 2.5, taper: [100, 100] });
    FX.group(s, "path", { points: [[0, -L], [0, L]], stroke: WHITE, width: 2.5, taper: [100, 100] });
    s.anchorPoint.setValue([0, 0]);
    var a = rnd() * 6.283, r = 80 + rnd() * 620;
    s.position.setValue([BX + Math.cos(a) * r, BY + Math.sin(a) * r * 1.1]);
    var t0 = T(4.24 + rnd() * 0.16);
    FX.keys(s.opacity, [[t0, 0], [t0 + 0.03, 100], [t0 + 0.12, 0]], false);
    FX.keys(s.scale, [[t0, [30, 30]], [t0 + 0.03, [110, 110]], [t0 + 0.12, [40, 40]]], false);
    s.blendingMode = BlendingMode.ADD;
  }
  // the dark dip (normal blend; disabled - see header)
  var dip = FX.solid(c, "dip", [0, 0, 0]);
  FX.keys(dip.opacity, [[T(4.12), 0], [T(4.155), 45], [T(4.20), 45], [T(4.267), 0]], false);
  dip.enabled = false;
  return FX.done(c, '"mode":"additive"');
}
