# CLAUDE-SPINE

An MCP server that rigs and animates **Spine 4.2** skeletons the way a slots
studio ships them. It builds clean silhouette meshes, heat-diffused weights,
IK, physics, a 2.5D turn rig, a juice preset library built on a fixed symbol
animation contract, FX, and a mobile performance budget guard. Every output is
loaded and played in the official `spine-core` runtime before it counts as
done.

Built from [egorfedorov/spine-mcp](https://github.com/egorfedorov/spine-mcp)
(MIT) and restructured around one typed model of the Spine format, with small
tools that do one job each.

| | | |
|---|---|---|
| ![wave](docs/wave.gif) IK arm + physics hair | ![turn](docs/turn_test.gif) 2.5D turn from one control | ![mesh](docs/mesh.png) contour meshes |
| ![land](docs/land.gif) `land`: drop, squash, settle | ![epic](docs/win_epic.gif) `win_epic`: coins, flash, shockwave | ![ripple](docs/ripple.gif) seamless water ripple |

*The previews are rendered from the procedural sample character
(`examples/build_demo.py`) through the spine-core runtime.*

## Install

You need Python 3.10+ and [uv](https://docs.astral.sh/uv/). Node 18+ is
needed for validation and previews. The Spine editor is optional; with it you
also get editable `.spine` projects.

```bash
claude mcp add -s user claude-spine -- uvx --from git+https://github.com/kumikilongyeyo/CLAUDE-SPINE claude-spine
```

Pin to a commit you have reviewed by adding `@<sha>` after the URL. Set
`SPINE_BIN` if Spine is not in the default place
(`/Applications/Spine.app/Contents/MacOS/Spine` on macOS,
`C:\Program Files\Spine\Spine.com` on Windows). The spine-core runtime
installs itself with `npm` the first time it is used. Run the `doctor` tool to
check everything.

## The tools

| Stage | Tool | What it does |
|---|---|---|
| Setup | `doctor`, `make_sample`, `inspect_psd`, `import_psd`, `project_info` | Check the toolchain; turn PSDs into a project (`<name>.json` + `images/`) |
| Bones | `add_bones`, `add_chain`, `reparent_slot` | Add bones in world coordinates. Art never moves |
| Mesh | `rig_mesh` | Region → contour mesh with bone-heat weights |
| Constraints | `rig_ik`, `rig_physics`, `rig_transform`, `rig_strand`, `rig_turn` | IK, Spine 4.2 physics, drivers, one-call hair/cape/tail rigs, 2.5D head turn |
| Motion | `juice_apply`, `fx_generate`, `ae_template`, `ae_fx_to_spine`, `add_keys`, `add_event` | Symbol contract clips, FX presets, After Effects comps played as frame sequences with matched timing, custom keys with named easing, game events |
| QA | `validate`, `qa_budget`, `qa_character`, `preview` | Structural and runtime validation, mobile budget, character QA (joint cracks, foot slide, per-rig bone budgets), GIF previews |
| Characters | `rig_face`, `face_clip`, `look_at`, `lipsync`, `rig_biped`, `clip_set`, `secondary`, `squash_stretch` | Whole-face rig and 2.5D turn from layer names (clamped eyes, blinks, brows, visemes, jaw); biped rig with floor-pinned IK feet and the 11-clip character contract; physics on every strand; volume-preserving squash |
| Animals | `gait`, `rig_quadruped`, `rig_serpent`, `rig_flier`, `attach_rig`, `rig_creature` | Footfall-table locomotion with planted feet; one-call quadrupeds; swimming and flying chains; snap-on ears, tails, wings, horns, digitigrade legs, mermaid tails, snake hair, fur and glow whose clips merge into any host; slime, golem, ghost, tentacle beast, dragon, insect, plant monster and mimic |
| Samples | `make_face_sample`, `make_biped_sample`, `make_quadruped_sample`, `make_serpent_sample`, `make_flier_sample`, `make_host_sample`, `make_creature_sample` | Procedural PSD-named sample rigs to try every recipe on |
| Export | `pack_atlas`, `make_editable`, `export_runtime` | Atlas + runtime folder; editable `.spine` through the Spine CLI |

A typical session, as Claude would run it:

```
import_psd   psd=wild.psd  out_dir=./wild  origin=center
rig_mesh     slot=cape  bones=[cape1, cape2, cape3]
rig_strand   slot=hair_lock_l  n_bones=4  physics=hair
rig_ik       bones=[arm_r1, arm_r2]
rig_turn     head_bone=head  face_slot=face  features={nose: 1.25, eye_l: 0.9, eye_r: 0.9, ear_l: -0.35}
juice_apply  fx=true  shine_slot=gem               → idle, land, win, win_loop, anticipation, dim
fx_generate  preset=coin_burst  into=win
validate     → qa_budget profile=mobile_symbol → preview → make_editable / pack_atlas
```

FX recipes (rune ring, flare, wisps, aura, floor glow, fireflies, twinkles, or all seven as `magic_reveal`) are one tool:
`fx_recipe` lists them, `fx_recipe recipe=guide` explains how to use, fork and mix them (also in [docs/FX_RECIPES.md](docs/FX_RECIPES.md)).

![magic_reveal](docs/magic_reveal.gif)

The two FX on every spin are recipes too: `reel_stop` (the strip overshoots, squashes and springs back on an exact
spring, dust, shock rings, screen shake) and `anticipation_reel` (an accelerating heartbeat glow with edge flames while
the other reels dim). They move your reel and screen bones through inserted carrier bones, never your own keys.

![reel_stop](docs/reel_stop.gif)

The rest of a slot game is recipes too, one family per moment (`fx_recipe` with no recipe lists them all; the guide
is [docs/FX_RECIPES.md](docs/FX_RECIPES.md)). Every one takes `tier=` small | medium | big | mega | epic, and
`sequence` turns a whole win choreography into a JSON list. Recipes that move your reel, symbol, screen or button bones
do it through inserted carrier bones, never your own keys.

| | | |
|---|---|---|
| ![spin](docs/spin.gif) spin: near_miss, spin_blur, turbo_spin, screen_shake | ![wins](docs/wins.gif) wins: payline, win_highlight, multiplier_stack, win_rollup | ![banner](docs/win_banner.gif) win_banner: big, mega, epic from one recipe |
| ![payouts](docs/payouts.gif) payouts: coin_fountain, cascade_pop | ![features](docs/features.gif) features: wild_land, expanding_wild, scatter_trigger, free_spins_transition | ![bonus](docs/bonus.gif) bonus: pick_reveal, hold_respin, jackpot_wheel, meter_fill |
| ![ambient](docs/ambient.gif) ambient: weather, god_rays, water_surface, heat_shimmer, fog_roll, lightning_storm | ![ui](docs/ui.gif) UI: button_press, idle_shimmer, focus_glow, padlock, popup | ![saber](docs/saber.gif) saber: a port of Video Copilot's Saber (Spine + AE template) |
| ![pinata](docs/pinata.gif) piñata: wild_glow, wild_transform, mult_cell_glow, cell_pop, confetti_burst, mult_streak, wild_merge, coins_to_bar, bar_sweep, pinata_hit, jar_burst, banner_backdrop (one picture kit; swap in a texture pack by name, `gain` / `thick` retune it) | | |
| speed_lines: anime focus lines that flicker like hand-drawn ones and rush in on the hit | AE template fire_aura: a flame ring shooting out of a hole (fire or electric), built on the fire template | ae_fx_to_spine sequences follow a rotated / scaled parent bone (aim a flame along a reel edge or away from a punch) |

Characters and animals are rig recipes that read your PSD by layer name and return a finished rig plus a standard clip
set, so swapping the theme means swapping the PSD ([docs/RIGS.md](docs/RIGS.md)):

| | | |
|---|---|---|
| ![face](docs/face.gif) rig_face: look, blink, brows, expressions | ![talk](docs/face_talk.gif) lipsync + look_at | ![body](docs/body.gif) rig_biped + clip_set |
| ![gait](docs/gait.gif) gait + rig_quadruped | ![addons](docs/addons.gif) rig_serpent, rig_flier, attach_rig | ![creature](docs/creature.gif) rig_creature: eight kinds |

## How it works

### One typed model: `ir.py`

All Spine 4.2 JSON goes through Pydantic models. Two rules keep round-trips
safe:

- **Spine's defaults.** Saving drops every field that is still at its runtime
  default.
- **Unknown fields survive.** New-version and editor-only fields are written
  back untouched.

Five real production exports round-trip with zero meaningful diffs.

The model also owns one trap. Weighted vertices refer to bones by **index**,
so inserting a single bone silently moves every weighted mesh onto the wrong
bones. Every change to the bone list goes through `remap_bone_indices`.

### Meshes: `geometry.py`

The pipeline runs in this order:

1. Pad the alpha mask.
2. Trace the outline (Moore neighbour).
3. Simplify with Douglas-Peucker, keeping the tolerance below the pad. This
   provably never clips art, and the result is checked.
4. Refine hull edges finer near joints. A hull edge that spans an elbow
   cannot bend.
5. Add interior points with Poisson-disk sampling, denser at joints.
6. Triangulate with a conforming Delaunay that is *verified*. Any hull edge
   still missing is split, and an exact constrained Delaunay (ear clipping
   plus Lawson flips) is the fallback.

Every mesh satisfies `triangles = 2n − hull − 2`, stays inside the image (the
editor clamps UVs outside 0–1 and the texture shifts), and imports into Spine
with zero repairs. Fuzzing 1,000 random silhouettes found four separate
degeneracies. All four are fixed and covered by tests.

### Weights: `weights.py`

Weights use bone-heat diffusion (Baran & Popović 2007, in 2D). The system is
`(L + A·H) w = A·H·p`, where L is the cotangent Laplacian and H is 1/d² to
the nearest bone segment visible inside the outline. As a result:

- A vertex halfway along a long bone belongs to that bone. Inverse distance
  to joints pulls it toward the next joint.
- Weights blend smoothly across joints.
- Heat cannot jump across a gap in the art, such as between two fingers.

After the solve, weights under 0.05 are pruned, each vertex keeps at most 4
influences, and every vertex is renormalised to sum to exactly 1. Tested
properties: 0 folded triangles at a 45° elbow, and finger weights do not leak
across the gap.

### Constraints: `rig.py`

- **IK:** the bend direction is taken from the setup pose. The target sits
  under the juice bones, so slams carry it.
- **Physics presets:** hair, cloth, tail, ribbon, jiggle, antenna and tassel,
  with values documented against what the runtime actually does. `damping`
  is the velocity *kept* per 1/60 s, and `limit` caps how far a reel slam can
  fling a lock of hair.
- **`rig_strand`:** builds a chain along the part's own centre line, then a
  mesh and physics, in one call.
- **`rig_turn`:**
  - The face mesh's middle travels with one control while its outline stays
    pinned. Each row gets a parabola weight profile, which cannot fold inside
    the turn range.
  - Features move by depth through local/relative transform constraints.
  - Everything happens in a screen-aligned frame. In the head bone's own
    frame, "turn" would nod.

### Juice and the symbol contract: `juice.py`

Every symbol gets `idle`, `land`, `win`, `win_loop`, `anticipation` and `dim`.
The optional clips are `scatter_trigger`, `wild_expand`, `flip`, `flip_depth`,
`multiplier_fly` and `win_big`/`win_mega`/`win_epic`.

The presets animate only two inserted bones: `juice_ground` (pivot at the
base) and `juice_core` (pivot at the centre). The artist's own keys are never
touched.

The clips follow these guarantees, all of them tested:

- One-shots end exactly on the setup pose.
- Loops match at both ends.
- `intensity` scales every amplitude.
- Events fire for the game: `sfx_land`, `sfx_win`, `rollup_start`/`rollup_end`
  and `fx_*`.

### FX: `fx.py`

The presets are explosion (flash, shockwave, radial sparks and smoke),
shockwave, coin burst and shower, ripple, glow pulse, sparkle and shine sweep.

- **Coins** spin through a flipbook sequence on true parabolas: x is linear,
  y is eased up and then down.
- **The ripple** is a seamless loop of staggered rings.
- **The shine** is clipped to the part's own outline and simplified to 32 or
  fewer clip vertices.

All textures are procedural and white, tinted per slot, so one tiny texture
serves every colour. Each FX slot is hidden in the setup pose. Each preset
fires `fx_<preset>`, so the engine's particle emitter can take over heavy
counts.

### QA: `qa.py`, `runtime.py`, `render.py`

`validate` checks:

- References
- Weights
- Triangulations
- UV range
- Curve array lengths
- Key order
- Events
- Draw order

It then loads the skeleton in **spine-core** and applies every animation frame
by frame, with physics stepping.

`qa_budget` uses per-profile limits (`mobile_symbol`, `mobile_banner`,
`mobile_character`, `desktop`). It estimates draw calls the way spine-webgl and
spine-pixi batch: a new call at every change of blend mode or atlas page along
the draw order, plus clipping. It then says what to fix.

`preview` rasterises the runtime's posed triangles to GIFs. It was
cross-checked frame for frame against the Spine editor's own PNG export.

## Tests

```bash
uv venv && uv pip install -e ".[dev]" && (cd validator && npm ci) && pytest
```

There are 1,028 tests:

- IR round-trip and bone remapping
- Meshing, plus 300 random silhouettes in CI (1,000 run locally)
- Weight properties
- Rigs
- Every juice clip, FX preset and FX recipe, with each recipe's physics read back from its keys (springs, drag,
  restitution, lags, Poisson schedules, loop closure)
- Every rig recipe: faces, bipeds, quadrupeds, gaits, serpents, fliers, add-ons and creatures, with planted feet
  and clip contracts measured in the runtime
- QA catching broken input
- The MCP tool chain
- The runtime

The Spine round-trip test skips unless the editor is installed. It imports a fully
rigged character into the real editor, exports it again, and requires every
mesh, weight and physics value to come back identical, with no importer
repairs.

## Limits

- **Weights are a strong first pass, not a finished hero rig.** Hands and
  faces still want an artist's pass. Linear blend skinning still collapses on
  the inside of bends past ~90°.
- **The turn rig needs separated layers.** Eyes, brows, nose, mouth, ears and
  front/back hair must each be their own layer.
- **The preview renderer is exact about geometry, not shading.** It has no
  MSAA and no two-colour tint.
- **Spine licensing still applies.** Using the Spine Runtimes requires a Spine
  license, and `make_editable` / `export_runtime` need a licensed editor.

## License

MIT. See `LICENSE`. The original work is © 2026 Egor Fedorov; this fork is
© 2026 kumikilongyeyo.
