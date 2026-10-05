# Changelog

## Unreleased

- Three more `fx_recipe` recipes, from new reference clips: `light_beam` (gold, ribbon and blue beams: column glow, filaments, weaving ribbon strands built as weighted meshes with one bone per row so they cost no deform keys, dust and glints; loops exactly), `portal` (swirling disc, counter-rotating spiral arms, orbiting specks, comet streaks, flashes) and `electric_frame` (underglow + sparks). The last two are hybrids: their plasma ring / lightning line is After Effects, via two new templates `portal_ring` and `electric_frame` (turbulent displacement + fractal-noise plasma, seamless loops) and `ae_fx_to_spine`; each recipe returns a `ring_hint` with the exact arguments. Guide extended with the hybrid workflow, a Spine-vs-AE table (crosshairs, hit bursts, coin pops, smoke) and the traps (SDF glow fill, AE noise clipping, deform keys vs the mobile budget).

- `fx_recipe` (new tool) + `claude_spine/fx_recipes.py`: seven authored FX layers lifted from a real reference clip (a lotus blooming out of a magic book) as reusable, parameterised recipes: `rune_ring`, `burst_flare`, `rim_wisps`, `bloom_aura`, `floor_glow`, `fireflies`, `twinkles`, plus `magic_reveal` (all seven timed like the clip, 13.2 s). Procedural textures, additive only (one draw call), one group bone per recipe so it moves, recolours (`color=`), resizes (`scale=`) and retimes as one piece, and merges into any animation with `into=`. `fx_recipe` with no recipe lists them with options and defaults; `recipe="guide"` returns the guide (use / fork / mix / how they were made / traps), mirrored in `docs/FX_RECIPES.md`. Each recipe fires an `fx_<recipe>` event. 28 new tests (every recipe builds, validates and plays in the spine-core runtime; shared arguments; respawn-at-alpha-0 for looping motes; bundle budget = 1 draw call).

- `ae_template` (26th tool) + `claude_spine/ae_templates/`: eight parameterised After Effects FX templates as ExtendScript (glow_pulse, shockwave, sparkle, relief_shimmer, fire, lightning, burst, splash). `ae_template` returns a script; running it in AE builds one ready-to-render comp, which goes straight to `ae_fx_to_spine`. Built-in AE effects only, so scripts render anywhere with `aerender`. Verified end to end (template → AE → save → aerender → Spine → spine-core runtime).

- `ae_fx_to_spine` (25th tool): After Effects → Spine bridge. Renders a saved `.aep` comp headless with `aerender` (never touches the project open in AE), reads AE's premultiplied TIFF alpha, trims empty frames, writes straight-alpha sprites to `images/ae/` and plays them as a Spine sequence at the comp's own speed. `hit_ae` + `hit_at` land an AE moment on a Spine one; `fit_duration` stretches a sequence to a loop length; `max_frames`/`max_size` shrink it. Frames already on disk work too (`frames_dir` + `fps`). Reproduces the coin project's hand-made fire flipbook byte for byte. 11 new tests.

## 0.1.0 — 2026-10-05

First release of the restructured fork of egorfedorov/spine-mcp.

- Typed Spine 4.2 IR (Pydantic) with exact runtime defaults and pass-through of unknown fields; bone-index remapping for weighted vertices.
- Contour meshes: padded trace → DP simplify (never clips art) → joint-aware refinement → verified conforming Delaunay with an exact CDT fallback.
- Bone-heat weights (cotangent Laplacian, visibility-aware heat), ≤4 influences, exact normalisation.
- IK, Spine 4.2 physics presets, transform constraints, one-call strand rigs, 2.5D turn rig.
- Symbol animation contract + juice presets on inserted juice bones; FX presets with procedural textures; Spine events for SFX/particles/rollups.
- QA: structural validation, spine-core runtime load + playback check, mobile budget with draw-call estimate, runtime-driven GIF previews.
- MaxRects atlas packer (whitespace strip, PMA, sequence-safe region names).
- 24 MCP tools; 369 tests including mesh fuzzing and a Spine editor round-trip.
