## UI flare family (spin button, win banner, total-win light)

Lifted from a reference clip of a desert-themed slot's bottom UI: a round spin button, a win banner over the balance
bar, a door with a rune coin above a "total win" arch. Module `claude_spine/fx_ui_flare.py`. Every picture is drawn
in code (white, tinted by the slot colour). The game's own art (button, arrows, coins, text) is NOT part of these recipes:
play them over your art. Times below are clip frames at 30 fps. At scale 1 the button is ~184 units across (rim radius
~92) and the banner is ~760 wide.

| recipe | what | kind |
|---|---|---|
| rim_glow_pulse | press on a round button: white-hot rim (2 rings), orange wash on the inner band (NORMAL blend), halo spreading 9%, 2 faint shock rings to 1.65x / 1.5x; + AE fire ripple (ae_hint / `ripple_frames`) | one-shot 0.97 s |
| anamorphic_burst | spin-start flare: rim bloom, wide bloom, 26 rays, 2 anamorphic streaks tilted 12 deg (white-cyan over warm), blue light on the top rim, 16 drifting sparks; + AE flame wisps (ae_hint / `wisps_frames`) | one-shot 1.6 s |
| ray_fan_beam | looping win light from an arch top: 10 soft wedges swaying and breathing on whole cycles, haze, light column up to a target with a ring, hot spot + flat flare, gold arch glow, back light | loop 2.8 s |
| glyph_strike | glyph flies into a target in 6 frames (comet trail, light band, prism shards, twinkles), impact flash + rays + ring, glyph cools on the target, light line draws out through it, secondary target lights up | one-shot 1.03 s |
| banner_energy | win banner lands: green burst spikes, green slashes racing outward, green haze, gold bloom, top-bar flare, coins from 2 sources, glints, resting gold light that stays | one-shot 1.8 s |
| ember_drift | embers drifting up over an area, each fading in and out once per loop | loop 4 s |

Anchors (`x, y`): the button centre (rim_glow_pulse, anamorphic_burst), the light source on the arch top (ray_fan_beam;
`target` is relative to it), the target the glyph lands on (glyph_strike; `source`, `secondary` and `twinkles` are
relative to it), the banner text centre (banner_energy; `bar` and `sources` relative), the area centre (ember_drift).

**Colour, one argument per part.** `color` is the main family colour, and every other part has its own option:
- rim_glow_pulse: `hot` (rim), `wash` (inner band), `deep` (dark of the AE ripple tint).
- anamorphic_burst: `bloom`, `hot`, `ray`, `core`, `blue`, `spark`, plus the wisp tints `dark`, `violet`, `violet_dark`, `pink`.
- ray_fan_beam: `magenta`, `red`, `beam`, `gold`, `hot`.
- glyph_strike: `trail`, `hot`, `shard`, `impact`, `ring`, `secondary_glow`, `line`.
- banner_energy: `hot`, `rest`, `green`, `green_hot`, `coin`.

To recolour the whole set, swap these hexes (a blue/cyan swap of every orange/gold one was checked on the clip).

**The After Effects halves.** Each recipe returns an `ae_hint`. Render the comp it names, then pass the frames folder
back as an option, and the recipe imports the frames into its own slot run (tintable, so the same hexes recolour them):
- rim_glow_pulse: the existing **ripple_glow** template, unchanged, with `size 384, duration 1, fps 30, look line,
  origin rim, color FF4A08, core FFB040, radius 0.48, travel 0.4, waves 3, life 0.9, echo 2, wave 0.9, wave_width 0.02,
  rim 0, halo 0.35, wobble 16, wobble_size 0.1, softness 0.5, breathe 0, seed 5`. It is imported at max_size 320 and
  15 frames, looped over the pulse, with alpha 0.3 x the pulse. Pass it as `options={"ripple_frames": dir}`.
- anamorphic_burst: the new **flame_wisps** template (below), at its defaults. Pass it as `options={"wisps_frames": dir}`.
  One grey frame set plays as 4 copies:
  - orange, from frame 4;
  - orange mirrored (rotation 184, scale 0.9, alpha 0.82 to 0.38), from frame 5;
  - violet (rotation 5, stretching from (1, 1.25) to (1.1, 1.3)), from frame 6;
  - pink (rotation -4, scale 0.8, alpha 0.7), from frame 8.

AE frames play at their own fps (`frames_fps`, default 30): retiming a one-shot with `duration` retimes the Spine keys
and the sequence start, not the flipbook speed.

**AE template `flame_wisps`.** Anamorphic flame wisps flying OUT of a centre to both sides:
- Two fractal-noise fields, stretched into thin strands (`strand` 16 px tall, `stretch` 14x wider), drift outward at
  `speed` 380 px/s.
- The left half is a mirrored copy of a second seed, so the 2 sides differ.
- A drifting turbulent displace (`curl` 16, `curl_size` 34) tears them into curls.
- They are shaped by a feathered flat ellipse (`spread` 0.6 of the width, `thick` 0.24 of the height), used as an ALPHA
  matte on its own layer.
- They flare in over 3 frames, grow fast then crawl (drag, scale 70 > 95 > 110 > 124%), and fade out over 0.9 s, with a glow.
- Output: 768x192 at 30 fps, additive on black, one-shot, 27 frames (26 after the trim).
- It is coloured once at the end (black > `color` > `core`). The defaults 808080 / FFFFFF render it GREY: import it
  tintable and tint it in Spine, or set `color`/`core` to bake a single colour.

**Measured facts from the clip.**
- The rim pulse peaks at frame 5 and is gone at frame 29. The halo grows 9%, and the 2 shock rings leave at frames 3 and 8.
- The press squash on the button: 1 > 0.77 (frame 3) > 1.09 (frame 7) > 1. Play it with `button_press`, or with your
  own keys on the button bone. Faithfulness check: with the same squash on the parent bone, anamorphic_burst matches the
  build to 0.02/255.
- The glyph flies at a constant ~38 px per frame and lands on frame 6.
- The win text pops 0.55 > 1.11 (frame 6) > 1.0 (frame 21). That is art: use `popup`, or your own keys.
- The total-win light breathes on a 2.8 s period.

**Traps.**
- The inner-band wash is NORMAL blend. Additive light cannot turn a teal band orange. Keep it in front of the button art.
- These are one slot run each. Put them `front_of` the button / banner art; the halos and rays are designed to sit over
  the art's edges (in the clip some sat behind the button: put a copy `behind` it if your rim art is opaque and wide).
- `glyph_strike`'s default glyph is a generic diamond. Pass your rune as `art={"glyph": ...}`, and the secondary target's
  LIT picture as `art={"secondary": ...}` (it is revealed bottom-up by a clipping wipe over 4 frames).
- AE caches renders by comp name: give each flame_wisps attempt a new comp name.

CHANGELOG: UI flare family (fx_ui_flare): rim_glow_pulse, anamorphic_burst, ray_fan_beam, glyph_strike, banner_energy, ember_drift (spin button / win banner / total-win light from a slot UI clip), plus AE template flame_wisps (grey anamorphic flame wisps, one frame set played as tinted copies); rim_glow_pulse documents its ripple_glow params.
SKILLROW: | Spin-start flare flame wisps (anamorphic, both sides) | `flame_wisps` defaults (768x192, 0.9 s, grey: import tintable, play as orange / mirrored orange / violet / pink copies; fx_recipe anamorphic_burst options.wisps_frames does it) |
