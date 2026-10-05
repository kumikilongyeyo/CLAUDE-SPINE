# FX recipes: use, fork, mix

Seven authored FX layers lifted from a real reference clip (a lotus blooming out of a magic book), plus a bundle that
plays them together. They are Spine primitives with procedural textures: no art needed, one draw call, nothing to
re-export when you recolour or resize.

## Use

    fx_recipe                                   -> lists every recipe with its options and defaults
    fx_recipe recipe=rune_ring  project=p.json  -> adds the ring as animation fx_rune_ring
    fx_recipe recipe=magic_reveal project=p.json x=0 y=0 scale=1.2   -> all seven in one 13.2 s animation

Shared arguments (every recipe): `x`,`y` = the SUBJECT CENTRE in the parent bone's space; `scale` (1 = a ~720-unit canvas
with a subject ~420 wide); `start` (seconds into the animation); `duration` (life window for window recipes, a time scale
for the two one-shots); `color`; `intensity` (alpha gain, 0..1+); `seed`; `count`; `into` (merge into an existing
animation, e.g. "win"); `parent`, `front_of`, `behind` (draw order); `name`; `options` ({recipe-specific: value}).
Every recipe fires an event `fx_<recipe>` at its start: hook it to a sound or an engine emitter.

| recipe | what | kind |
|---|---|---|
| rune_ring | gold rune circle flat on a surface; builds, flashes white, fades | one-shot 2.7 s |
| burst_flare | anamorphic flare + shock ring + flung sparks | one-shot 1.8 s |
| rim_wisps | soft feathery fringe around a footprint | window 5.6 s |
| bloom_aura | coloured halo + core + hot spot + rising light column | window 5.9 s |
| floor_glow | warm glow + streaky reflection under the subject | window 9.8 s |
| fireflies | drifting motes, each with its own life and twinkle | window 8.2 s |
| twinkles | four-point stars that pop and spin | window 5.8 s |
| magic_reveal | all seven, timed like the reference | bundle 13.2 s |

## Fork: change a recipe

- Recolour: `color=` (ring and flare bake a texture per colour: `fx/rune_ring_<HEX>`; the rest are white textures tinted
  by the slot). Aura has `options={color2, beam_color}`; fireflies and twinkles take `options={palette: [...]}`.
- Resize: `scale=`. Everything is in design units under one group bone, so it resizes as one piece.
- Retime: window recipes take `duration=` (seconds); one-shots scale their whole timeline by duration/default.
- Reshape the footprint: `rim_wisps options={rx, ry, length}`, `rune_ring options={squash}` (1 = top-down).
- Different look entirely: copy the recipe function in `fx_recipes.py`. Each is ~30 lines: make slots on bones, then write
  closed-form functions of time with `c.bone_keys` / `c.color_keys`. The texture factories (`tex_*`) are reusable.

## Mix

- Any subset: `magic_reveal options={skip: ["fireflies"], overrides: {"rune_ring": {"color": "5AE0FF"}}}`.
- Any recipe into a game clip: `fx_recipe recipe=burst_flare into=win start=0.4 x=<symbol x> y=<symbol y> scale=0.6`.
- Several of the same recipe: call again with a different `name=` (bones and slots are uniquified either way).
- With the generic presets: `fx_generate preset=coin_burst into=win` and `fx_recipe recipe=rune_ring into=win` share the
  same animation; both fire events the engine can hook.
- With After Effects: bake what Spine cannot do (volumetric smoke, fire) with `ae_template` + `ae_fx_to_spine`, keep
  the glow/ring/particle layer here, and merge both into one clip with `into=`.

## How these were made (do the same for a new clip)

1. Pull a contact sheet of ~16 evenly spaced frames from the reference (AVFoundation or ffmpeg). Look at WHEN each element
   appears, not just what it looks like: write the timeline (ring 2.0 s, flare 3.55 s, aura 3.7 s ...).
2. Split into layers by behaviour, not by object: one-shot flash, breathing glow, drifting particles, flicker fringe.
3. One recipe per layer. A texture that is white (tint by slot) or colourised once (hot core -> colour -> deeper rim).
   Additive blend only, so everything batches.
4. Write each animated value as a closed-form function of time and sample it densely and linearly (24 keys/s for fast
   FX, 8-14/s for slow ones). Exact curves, trivial to retime, nothing to tune by hand in an editor.
5. Render with the runtime (`preview`, or `runtime.run` + `render.render_frame` with a FIXED camera and the reference's
   dark background: additive FX on the default grey look washed out). Compare to the reference sheet, adjust, repeat.
6. Validate and `qa_budget`; the recipes add no weights, no clipping, no physics and a single blend mode.

## Traps (each one cost an iteration)

- Spine translate keys are OFFSETS from the setup pose, scale keys MULTIPLY it; bone x/y are in the PARENT's space.
  `add_bones` takes world coordinates; recipes append `Bone` objects with local ones. Don't mix them up.
- A squashed (iso) ring: put the squash on a parent bone's scaleY and rotate the child. Rotating inside the squashed space
  is the correct projection; squashing the sprite itself shears it.
- Feather/wisp textures: thresholding noise to zero leaves speckle pits that read as gas-burner flames. Keep a floor under
  the streaks and fade the base.
- Reflection textures: a hard top edge reads as a curtain and strong banding looks artificial. Soft top, low-contrast streaks.
- Looping particles: give each its own period and phase, make alpha 0 at the wrap, and add explicit keys at every wrap
  (`wrap-0.002`, `wrap`) so linear interpolation cannot streak a mote across the frame while it is still visible.
- Flare streaks wider than the view clip hard; keep them ~1.2x the subject, and give streaks real thickness
  (a 1-px hairline reads as a scratch).
- GIF previews of soft gradients dither to 10+ MB. Judge on the contact sheet; share a quantised/resized GIF.
- No book, lotus or vines here by design: they need art (layered PSD) and are rigged with `import_psd` + `rig_mesh` +
  `rig_strand`. Put these recipes `front_of=` / `behind=` those slots.
