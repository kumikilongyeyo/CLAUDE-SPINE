"""The FX recipe guide, returned by ``fx_recipe(recipe="guide")`` and mirrored in docs/FX_RECIPES.md
(a test keeps the two identical)."""

GUIDE = """# FX recipes: use, fork, mix

Authored FX layers lifted from real reference clips (a lotus blooming out of a magic book; light beams; a blue vortex
portal; a crackling electric frame), plus a bundle that plays the lotus set together. Spine primitives with procedural
textures: no art needed, tiny atlas, nothing to re-export when you recolour or resize. Three of them (portal,
electric_frame, and optionally any other) are HYBRIDS: the churning plasma / lightning part is After Effects, the rest is Spine.

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
| light_beam | tall beam: column glow + filaments (weaving ribbons) + dust + glints; style gold / ribbon / blue | loop 4 s |
| portal | swirling disc, spiral arms, orbiting specks, comet streaks, flashes (+ AE plasma ring) | loop 6 s, hybrid |
| electric_frame | violet underglow + sparks around a frame (+ AE lightning line) | loop 1 s, hybrid |
| crosshair | targeting reticle: drops in spinning, locks on with a flash, recoils and fades when it fires | one-shot 1.25 s |
| hit_burst | starburst + core + two shock rings + sparks (fires fx_hit) | one-shot 0.95 s |
| lock_on | crosshairs lock onto any number of targets in turn, fire, hit bursts land | bundle |
| cell_glow | glowing cell frame(s) with a twinkling starfield, pop = flash + burst + sparkles; resizable 9-slice | window 3.2 s |
| puff | cartoon puff of smoke: flash, cloud lobes burst out and thin, soft ring (clears a symbol) | one-shot 1.15 s |
| smoke_glow | rising smoke haze filling a box + flame-colour glow at its base | loop 4 s |
| meteor_trace | bright head + comet tail racing around a rounded-rect frame, shedding sparks | loop 2 s |
| projectile | glowing shot on an arc to (tx, ty) with a comet tail, then impact flash/ring/star | one-shot ~1.35 s |
| frost | frost ferns grow across a box (edges, or centre like a snowflake) as a generated flipbook; cold glow, glints | window 2.4 s |
| icicles | icicles grow down from the top edge under a frost crust; glints run down, drops swell and fall | window 3 s |
| ice_shatter | an ice block forms, cracks (Voronoi lines), shatters into shards that fly and fall; mist, ring | one-shot 1.6 s |
| bubbles | bubbles rise, wobble, squish and pop; clear centres, fresnel rims | loop 4 s |
| water_splash | droplets on parabolas (stretched along their speed), two ripple rings, mist | one-shot 1.3 s |
| magic_reveal | the seven lotus recipes, timed like the reference | bundle 13.2 s |

## Your own art (`art=`)

Every recipe can use your pictures instead of the generated ones and keep ALL the motion (timing, easing, flashes, events).
`art={role: spec}`; the roles of each recipe are in the listing (`fx_recipe` with no recipe, field `art_roles`), e.g.
crosshair: reticle (the picture) plus glow / ring / flash; hit_burst: starburst, glow, ring, core, mote; cell_glow: frame, fill, ...
A spec is a PNG path, a PSD layer `"file.psd#Layer name"` (or `"file.psd#Group/Layer"`; the layer is cut at its own
bounding box, so its centre is the target point), or a dict `{path, blend, scale, slice, px, anchor}`:

    fx_recipe recipe=crosshair project=p.json art={"reticle": "ui.psd#reticle"}
    fx_recipe recipe=lock_on  project=p.json art={"crosshair": {"reticle": "ui.psd#reticle"}, "hit_burst": {"starburst": "ui.psd#hit star"}}
    fx_recipe recipe=cell_glow project=p.json art={"frame": {"path": "cell.png", "slice": 40, "px": 0.5}}

- The recipe keeps its own WIDTH for the slot and your art keeps its aspect; `scale` multiplies that width.
- Blend defaults to the recipe's (additive for light). Give `"blend": "normal"` for art with solid colours.
- Slots whose colour is white show your colours as drawn; glows keep the recipe `color` as a tint, so give art for them too (or
  leave the generated glow) when the colours must match.
- Art conventions: centred and roughly square for reticles / stars / rings; wisps have their BASE on the left edge; the light
  column has its base at the bottom; the reflection hangs down from its top edge; a column is stretched to the beam height.
- 9-slice frames (`cell_glow` frame / fill): `slice` = corner size in art pixels, `px` = units per art pixel. The corners stay as drawn,
  the middle stretches, so draw the edge cross-section constant along its length.
- Bundles take art per member: `lock_on` -> `{"crosshair": {...}, "hit_burst": {...}}`, `magic_reveal` -> `{"<recipe>": {...}}`.
- Art is copied into the project as `images/fx/art_<recipe>_<role>.png`; edit that file (or the source) and rebuild to update.

## Mixing recipes into one clip (example: a gold cell that fills with haze, then a puff clears it)

    fx_recipe recipe=smoke_glow into=gold_cell options={width: 130, height: 350, alpha: 0.45}
    fx_recipe recipe=cell_glow  into=gold_cell color=FFC93C options={width: 130, height: 350, color2: FFE9A0, pop: 2.9, fill_color: C98A7A, fill_alpha: 0.35}
    fx_recipe recipe=puff       into=gold_cell start=2.85 options={radius: 130, size: 170, color2: FFE9A0}

All three land in the same animation; draw order follows call order (later = in front; use front_of / behind to change it). Flames
licking a frame are an After Effects `fire` flipbook placed with ae_fx_to_spine (not a recipe yet).

## Realistic smoke, flames and haze (After Effects templates)

- `smoke_puff`: a billowing cloud that bursts, rolls and erodes from its thin parts (alpha). Pair with
  `fx_recipe recipe=puff options={lobes: false}` (flash + ring, and an `ae_hint`), then `ae_fx_to_spine` the comp with that hint.
- `smoke_haze`: a soft churning haze that fills a box and loops (alpha); put it in front of a cell's fill.
- `fire` with `edge_fade` (0.15-0.2) for narrow flame tongues that never show the comp border. ONE tongue flipbook is enough for a
  whole frame: add it once with ae_fx_to_spine, then clone the slot along the edges with different bone scale/rotation and a
  different sequence `index` per clone (loop phase), so the flames never move in step and the atlas holds one flipbook.
- `electric_frame` re-rendered at any aspect (e.g. width 1024, height 160, green) gives a long energy bar.

## Ice and water

Spine alone: `frost`, `icicles`, `ice_shatter`, `bubbles`, `water_splash` (module `fx_elements.py`). Mix them: a frozen cell is
`cell_glow` (dark fill) + `frost` + `icicles` (y = cell top) + `ice_shatter` at the end. Underwater is `bubbles` over the AE
`caustics` template (shimmering light webs, additive, loops) added behind the first bubble slot with ae_fx_to_spine.

- `frost` grows by a GENERATED FLIPBOOK: the ferns are grown once in Python (branches at the 60 degrees of ice crystals,
  each point stamped with its freeze time), and frame k shows what has frozen by k/frames. Exact growth, a sequence at
  runtime, nothing to key. `grow` = seconds to freeze, `mode` = edges | center, `fade` = seconds to melt away at the end.
- `ice_shatter` cuts a procedural ice block into Voronoi shards (one image per shard, bright cut edges); each shard is a
  slot on its own bone, thrown out from the centre and pulled down by gravity.
- Droplets are turned and stretched along their velocity (unwrapped angles) so they read as water, not confetti.

## Hybrids: Spine recipe + After Effects part

`portal` and `electric_frame` return a `ring_hint` (parent bone, the slot to draw in front of, additive, loop, until).
The recipe builds everything Spine does well; the part that needs per-pixel noise comes from After Effects:

    fx_recipe recipe=portal project=p.json into=portal           -> ring_hint
    ae_template name=portal_ring params={comp: portal_ring_v1, save_as: x.aep}   -> run its script in AE (ae_run_script)
    ae_fx_to_spine project=p.json name=portal_ring aep=x.aep comp=portal_ring_v1 mode=additive
                   parent=<ring_hint.parent> front_of=<ring_hint.front_of> animation=portal seq_mode=loop until=6 scale=1.8

Same for electric_frame (template electric_frame, scale ~0.95 for the default 512 comp and a 400 frame). Both AE
comps cycle their turbulence (Cycle Evolution), so the flipbook loops with no seam. The AE part is fixed-size: to make
a frame resize at runtime, bend an AE strip along a path with `ae_fx_along_path` (when that tool is available).
Stay honest about cost: the portal ring is 48 frames at 384 px, the frame line 24 frames at 512 px. Use `max_size` /
`max_frames` in ae_fx_to_spine to shrink them.

## Resizing and recolouring a glowing frame

- Spine-built frames (`cell_glow`): any `width`/`height` at build time, `color`/`color2` for the line and the pop. The frame and
  its fill are ONE 9-slice mesh pair weighted to four shared corner bones (the result lists them): corners keep their
  art, edges stretch (the edge cross-section is constant, so stretching never shows). In the game, move the corner bones
  to resize at runtime; slot colours can be changed live to recolour.
- AE-rendered frames (`electric_frame`): the underglow and sparks resize (`width`/`height`) and recolour (`color`/`color2`)
  freely. The jagged line is a baked 512 px flipbook: uniform scale works up to ~1.5x; recolour by re-rendering with
  another `glow_color`/`color` (about 10 s) or by rendering it neutral (white) and tinting the slot. For different
  width/height at runtime, run the flipbook through the same 9-slice mesh (corners crisp, edges stretch the crackle),
  or bend an AE strip along a path with `ae_fx_along_path`.

## What needs After Effects, what does not (from the references seen so far)

| Looks like | Spine alone | Needs AE |
|---|---|---|
| beams, glows, rings, flares, sparkle/dust, orbiting specks, spiral swirls, flashes | yes (recipes above) | no |
| crosshair reticles locking on, hit starbursts, coin pops, symbol pop-out | yes: ring + cross texture with scale/rotate, `burst_flare`, `fx_generate coin_burst`, scale/alpha the symbol | no |
| glowing cell frames with a starfield inside | yes: `electric_frame`-style glow + `fireflies`/`light_beam` dust clipped to the cell | no |
| churning plasma edge, lightning, smoke, fire, painterly turbulence | no (needs noise every frame) | yes: `ae_template` fire / lightning / portal_ring / electric_frame, then `ae_fx_to_spine` |
| a smoke glow sitting on a UI bar | the glow is Spine (additive soft ellipse) | the smoke body is AE (fractal noise, looped) |

## Fork: change a recipe

- Recolour: `color=` (ring and flare bake a texture per colour: `fx/rune_ring_<HEX>`; the rest are white textures tinted
  by the slot). Aura has `options={color2, beam_color}`; fireflies and twinkles take `options={palette: [...]}`.
- Resize: `scale=`. Everything is in design units under one group bone, so it resizes as one piece.
- Retime: window recipes take `duration=` (seconds); one-shots scale their whole timeline by duration/default.
- Beams: `light_beam options={style: gold|ribbon|blue}` sets all defaults; any of `strands, wave, dust, dust_width, core_width,
  column_*, strand_width, dust_size, dust_tint, sparks, cap` overrides one. `color=` retints it (core, strands, dust).
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
- A ribbon/strand that bends: do NOT use deform keys (they count against the mobile budget, 4 allowed). Build a 2-column
  weighted mesh whose rows are each pinned to one bone and animate those bones' translateX (see `Ctx.strand`).
- Rounded-rectangle SDF glow: inside the outline the "outside" term is 1, so max(out, inside) fills the whole interior.
  Use the outside term only where d > 0 and a separate decaying term where d < 0.
- AE Fractal Noise clips to white with contrast >~150; start at contrast ~100, brightness -30 and tune by measuring mean
  luminance of a saved frame (comp.saveFrameToPng). A thin stroke displaced at a small Size just wobbles; use Size
  ~9% of the comp with Complexity 6 for lace.
- AE caches rendered frames by comp name: give each attempt a new comp name. `save_as` in a template switches the OPEN
  project to the new file (the old .aep stays intact on disk).
- A tail that follows a curve: rows of a strand mesh on bones that each sit on the path at a lag, ROTATED to the tangent + 90
  so the strip's width stays across the curve. Unwrap the angles (np.unwrap) or a row spins 360 the moment the tangent crosses
  +-180 (any shot fired leftward). Perimeter walkers must return a continuous, ever-decreasing angle lap after lap.
- `a or b and c` is `a or (b and c)`: a segment test written like that matched every corner arc and parked the meteor in the first corner.
- A square glow stretched to a long bar floods its ends; frame glows are 9-slices (`_frame_glow`) so the edge keeps its thickness.
- AE 2026: Easy Levels' Input Black/White cannot be keyframed (canVaryOverTime false); animate the noise Brightness instead.
  A mask on a MULTIPLY layer leaves the noise outside the mask; mask the noise itself and keep a black solid at the bottom of
  a luma precomp, or a transparent area turns into a hard white rectangle. Fire's faint noise reaches the comp sides: use edge_fade.
  ae_run_script needs an explicit `return`.
- AE 2026 Cell Pattern shows its Contrast as "Contextual Slider"; set it by match name ("ADBE Cell Pattern-0003").
  Caustics = inverted Cell Pattern (bubbles type) + Easy Levels input black ~0.38 to keep only the bright webs, then Tritone.
- Frost that reads as frost is DENSE: many short ferns with frequent 60-degree branches plus a blurred frosted film; sparse
  long branches look like twigs.
- Flare streaks wider than the view clip hard; keep them ~1.2x the subject, and give streaks real thickness
  (a 1-px hairline reads as a scratch).
- GIF previews of soft gradients dither to 10+ MB. Judge on the contact sheet; share a quantised/resized GIF.
- No book, lotus or vines here by design: they need art (layered PSD) and are rigged with `import_psd` + `rig_mesh` +
  `rig_strand`. Put these recipes `front_of=` / `behind=` those slots.
"""
