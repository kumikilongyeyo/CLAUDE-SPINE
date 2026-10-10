---
name: clip-to-spine
description: Rebuild the effects of a reference video (slot game, game UI, trailer) as Spine 4.2 animations, using After Effects for what needs real noise (lightning, fire, auras, smoke, explosions) and native Spine for everything that is moving light (glows, flashes, hit bursts, streaks, rings, rays, speed lines, coins, confetti). Produces an editable .aep, an editable .spine, a game export and previews over the clip, plus a caveats report. Use when the user sends a clip and asks to "do it in AE then Spine", "make these effects in Spine", "AE to Spine", "rebuild this", or asks whether a clip's effects are possible and wants them built. Needs the claude-spine MCP (fx_recipe, ae_template, ae_fx_to_spine) and, for the AE parts, the after-effects MCP; start from the clip-breakdown skill's tools for looking at the clip.
---

# Clip to Spine

The proven workflow (it shipped a slot free-spins sequence: reel fire, scatter lightning, fire / electric auras, clash
fireballs, flame trails, speed lines). Follow the order: each step exists because skipping it cost a rebuild.

## 0. Setup checks (once per session)

- claude-spine MCP tools available (`fx_recipe`, `ae_template`, `ae_fx_to_spine`). Scripts run against the SAME
  version the MCP is pinned to: read the pinned sha with `claude mcp get claude-spine` (the CLI lives inside the
  desktop app: `~/Library/Application Support/Claude/claude-code/<ver>/<hash>/claude.app/Contents/MacOS/claude`)
  and run Python as `~/.local/bin/uvx --from git+https://github.com/kumikilongyeyo/CLAUDE-SPINE@<sha> python ...`.
  Export `PATH=$HOME/.local/node/bin:$PATH NODE_BIN=$HOME/.local/node/bin/node SPINE_BIN=/Applications/Spine.app/Contents/MacOS/Spine`.
- After Effects: call `ae_get_project_info` FIRST. The user keeps a project open: if it has items or unsaved work,
  do not build in it without asking; if it is empty and Unsaved, build there and `app.project.save(File(...))` into
  the job folder (AE then has that file open: say so). Never close or overwrite the user's project.
- Output folder: `~/Downloads/vfx recipe/<project>/` unless the user names another.

## 1. Look (use the clip-breakdown skill's `cliptools.py`)

`motion` for the beats, `sheet` for the whole clip, `strip` / `sheet --crop` around every beat, `grid --units 720`
on a CLEAN frame to measure the layout (reel centres, rows, anchors) in skeleton units. Count rows and columns on the
grid: a guessed layout cost a full rebuild. Save 1-3 clean frames to `reference_frames/` as preview backgrounds.

## 2. Split every effect

| Needs real noise: After Effects -> frame sequence | Moving light: native Spine (`fx_recipe`) |
|---|---|
| lightning, fire, auras, smoke, explosions / fireballs, liquid, energy swirls | glows, flashes, hit bursts, rings, rays, streaks, sweeps, flares, speed lines, coins, confetti, dims, shake, number pops |

Art (characters, symbols, titles, painted backgrounds) is neither: list it as "art, not covered" unless the user
supplies it. Respect "focus only on the effects".

## 3. After Effects: build all comps, judge, then import

For hero / premium / realistic effects, call `ae_vfx_plan` before building the AE comps. Use its layer hierarchy,
timing beats and look rules as the shot brief. After rendering the representative frames/contact sheet, score the
pass with `ae_vfx_review` before importing. If clarity is weak, subtract decorative particles/lens layers first.
For production handoff use `ae_vfx_to_spine` instead of the raw bridge unless you intentionally need manual frame
or texture budgets; repeated instances still use `copies=` so they share one frame set.

1. One script for ALL comps: `ae_template` for each (returns `run_with`), concatenate the `$.evalFile` calls into one
   `ae_run_script` (each in try/catch, push results), end with a save. Names: `<prefix>_<what>_v<N>`; AE caches renders
   by comp NAME, so every tuning attempt gets a new `_vN`. Delete failed / test comps and their unused solids.
2. Render each with aerender headless (`ae_bridge.render_comp(aep, comp, out_dir)`, ~5-7 s per comp, reads the SAVED
   .aep) into `ae/frames/<comp>/`.
3. Judge on a contact sheet (`templates/ae_sheet.py`) BEFORE Spine. Fix the look in AE, not in Spine.

Before building from scratch, check `ae_library` (50 finished cel and realistic effects: bursts, rings, electric,
water, smoke, fire columns, sunbursts, glows, elements): build the closest one and adapt it, or copy its builder.

Known-good starting points:

| Effect | Template + params |
|---|---|
| Lightning strike (top to bottom) | `lightning` width 320 height 640 start [0.45,0] end [0.55,1] branching 0.45 restrikes 2 (additive) |
| Small crackle on a symbol | `lightning` 256x256 start [0.38,0.12] end [0.6,0.88] amplitude 0.28 branching 0.22 bolt_width 0.028 |
| Fire aura / power-up ring | `fire_aura` size 512 (alpha, loop; import at max_size 256, show at 0.5-0.9) |
| Electric blue aura | `fire_aura` hot F0FFFF mid 3AA8FF cool 1030B0 |
| Flame trail behind a punch | `fire` 320x640 taper 2.9 body 0.2 core 0.32 edge_fade 0.16 rise 700; NORMAL blend, aimed by a bone |
| Flames along a reel edge | `fire` 1024x320 core 0.18 body 0.06 scale 24 alpha_cut 0.34; bone rotated 90, scaleX = reel height / 1024 |
| Fireball / clash | `smoke_puff` light FFF3A0 mid FF7A1C shadow 3A2018 (blue: E8FFFF / 3A9CFF / 0A1A40) |
| Neon / laser / energy line | `saber` presets (or the Spine `saber` recipe, no AE needed) |
| Energy rim sending waves outward (charged orb, powered cell) | `ripple_glow` (additive, loop, import tintable; `waves` 1 per second like the clip, `shape rect` for cells) |

## 4. Spine: one build script, one function per animation

Copy `templates/build.py` and `templates/render.py` (this skill's folder) into the job folder, set NAME, SHA, SCREEN,
the measured layout and COMPS. One function per GAME EVENT (`reel_fire`, `scatter_land`, `scatter_trigger`, ...):
AE comps via `seq(...)` (aim / stretch with a `bone(...)`, sequences follow rotated parents), Spine parts via
`R.apply(p, recipe, into=<animation>, ...)` (list recipes: `fx_recipe` with recipe=""; guide: recipe="guide").
`hit_ae` / `hit_at` lands an AE moment (the strike) on a Spine time. Then `build.py` validates, packs `export/`,
imports into real Spine (`spine_project/*.spine`, repairs must be `[]`).

## 5. Preview over the clip, tune, repeat

`render.py` plays the animations in the real spine-core runtime over the dimmed reference frames. Read the sheets;
crop / zoom single GIF frames for detail. Compare against the clip's own frames at the same beat. If something is
invisible, print its draw bounds and blend from `runtime.run(..., geometry=True)` before retuning (it is usually
there: additive colour on a same-coloured background, or its hot base parked on the subject).

## 6. Report (and offer to make it reusable)

Tell the user: what was built (per animation, AE vs Spine), the files (`ae/*.aep`, `spine_project/`, `export/`,
`previews/`, README.md in the job folder), and the caveats:
1. a flipbook repeats exactly (each variant costs memory);
2. GPU memory: ~16 MB per 2048 atlas page uncompressed (state the pages);
3. a bolt / flame has a fixed shape: stretching changes its thickness, a new shape is a re-render;
4. sequences follow bones but don't bend with a mesh;
5. additive light vanishes on bright or same-coloured backgrounds (normal blend for flames there).
Send 2-3 preview GIFs. If a new effect is generally useful, offer to add it to CLAUDE-SPINE as a recipe / template
(worktree off origin/main, tests, guide, push, re-pin the MCP).

## Traps (each cost an iteration)

- zsh does not word-split a command stored in a variable (`$U build.py` fails): use a function or write it out.
- `read_tiff` / `read_premultiplied` return float 0..1: dividing by 255 gives black sheets.
- Polar Coordinates: interpolation is 0..1 (not %); it wraps in the layer's pixels with the short side as radius
  (squeeze into a square first). The `fire` body ramp is sized to the comp WIDTH (tiny `body` on wide strips);
  `taper` sets how tall the flame reaches.
- A transition / flash frame as preview background makes every effect look wrong: use clean frames.
- Shape-layer Gaussian blur clips at its bounds; Fractal Noise whites out above contrast ~150.
- A `//` comment inserted before a closing `}` on the same line comments the brace out (check generated JSX with
  `node --check` on a .js copy).
- `claude mcp add`: the server NAME goes before the `-e KEY=V` flags (`-e` is variadic and eats it).
- Re-importing into an existing `.spine` ADDS a skeleton (`name2`, `name3`, ...) instead of replacing it, so the
  export grows `name2.json`, `name3.json` on every rebuild: delete the `.spine` (and clear `export/`) before each build
  (the starter does). Check `export/` holds exactly one json per skeleton.
- Spine has no motion blur: a fast zoom-in reads right with 2-3 ghost copies at larger scales and lower alpha.
- Preview each effect over the board state the game shows at that moment (e.g. a win flare over the already-dimmed
  board): additive pink over a bright pink board washes out in the preview and not in the game.
