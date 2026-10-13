## Win screens (`claude_spine/fx_win_screens.py`)

Fourteen recipes rebuilt from a casual-slot reference clip (portrait 800 x 1396, 30 fps, 23 s): a cascade win
(winning cells glow, pop, the board drops, a multiplier steps up with a burst of fire, the win number pops), then a
Big Win screen, a tier upgrade to Mega Win, and a Total Win screen. Units are the clip's pixels (a cell is ~150 units);
anchor = the subject's centre. Every recipe is procedural, additive unless noted, one group bone, colours from params.

### Cell and board moments

| Recipe | What | Defaults / options |
|---|---|---|
| `ornate_cell_glow` | Yellow light PAINTED behind a winning symbol (normal-blend lozenge + round skirt: additive yellow vanishes on a pale board), an ornate lozenge outline of light, `count` rising motes. Grows in 0.17 s (scale 0.8 -> 1, cubic out), breathes (0.5 s), dims over the last 0.3 s. | 1.0 s, color FFE63C, line_color FFF4A8, size 150, off True. Start it 1.0 s before the pop; `result.loop` = [0.17, 0.7] to loop while waiting. Draw it behind the symbol (`behind=`). Roles `paint`, `frame`. |
| `starburst_pop` | A winner vanishes: translucent square flash, a 22-ray + 12-ray starburst out in 0.12 s and gone by 0.2 s, star core + streak, `count` glints drifting out to 0.45 s. | 0.45 s, color FFB43A, hot_color FFF6D8, glint_color FFF4A8, size 150, count 9. Role `rays`. |
| `blowout_flash` | A symbol that STAYS (a wild) blows out white 0.06-0.19 s while it re-forms. | color FFF6D8, size [150, 118]. Anchor = the bright part (a wild's heart: +33 units). |
| `label_glint` | A label that just changed: warm flare + streak, a tilted band sweeping across (0.3 s). | 0.42 s, color FFE7A0, size [192, 120]. Role `band`. |
| `echo_stamp` | A label joins a total: 3 echo copies stamp down under it (0-0.24 s), one copy drops `drop` units into the target, growing 12%. | size [192, 122], drop 138. Role `label` (stretched to the box; default = a pill of light). |
| `ghost_pop` | A number lands: label pops 1.42 -> 0.97 -> 1.0 in 0.2 s, a ghost copy swells to 1.55 and fades by 0.33 s. | size [425, 94], pop 1.42, ghost 1.55. Role `label`. |
| `fire_boost_flare` | Spine half of a multiplier "fire boost": the warm flare on the bar. The fire and smoke are After Effects: `result.ae_hint` carries both template param sets and the import (see below). | 0.85 s window, color FF9426. |

### Win screens (anchor = the win number)

| Recipe | What | Defaults / options |
|---|---|---|
| `win_screen_intro` | Board dims (0-0.1 s, 35%), a full-screen wash floods at 0.13 s (82%) and clears by 0.45 s while the screen fades in; glow burst (normal body + additive + hot core) + ray flare + `count` flung sparks bloom 0.2-1.0 s. | 1.0 s, color 2ED2FF, core_color E6FFFF, wash_color 2840FF, dim_color 0A0A30, count 16, screen [840, 1440], screen_offset [-27, -134]. |
| `win_screen_glow` | Hold behind a count-up: the glow settles from the intro over `settle` s, then breathes (1 s); a fan of streaks turns slowly; `count` stars twinkle. | 4.2 s window, settle 2.2 (`result.loop` = [2.2, 4.2]), dust_color 70ECFF, count 22. |
| `win_upgrade_flash` | Tier upgrade: flash + star rays + streak at the number (0.02-0.3 s), screen wash wash_color -> wash_mid -> wash_color (0.12-0.44 s) while the game swaps the art. | color 7FEBFF, wash_color FF54D6, wash_mid FF7A3C. |
| `beam_sweep` | 7 broad soft beams turning behind the title, exactly one beam step per loop (seamless), glow (normal body + additive), white core, stars. | 3.0 s window, color FF54D6, size 1500, count 20. Role `beams`. |
| `sunburst_intro` | A glow gathers on the counter (0-0.18 s), a bloom fills the screen (0.12-0.45 s) with a light wash. | color FFB52E, core_color FFF3B8, screen_offset [0, -228]. |
| `sunburst_glow` | Total Win sunburst: NORMAL-blend warm light (outer + sun) behind everything, white-hot core, two fans of thin rays (120 + 90) turning against each other and flickering (periods T/8, T/5), sparkles. | 4.0 s window, color FFB52E, core_color FFF3B8, outer_color = color mixed 45% to FF5A20, turn 12. Role `rays`. |
| `face_flash` | A light that fills one object's face on a period: `shape` disc (coin) or plate (cut gem), short soft edge, halo, star glint. Peak at `delay` + rise. | 1.25 s window, color FFE45A, shape disc, size 152, delay 0.2, timing [0.1, 0.1, 0.1], peak 0.85. Role `face` (the object's silhouette = an exact fill). The clip's gem: shape plate, size 140, tilt -35, color FFC8B4, delay 0.06, timing [0.07, 0.08, 0.08], peak 0.75, hold_level 0.8, halo 0.4, star False; then the coin at delay 0.2. |

### The After Effects parts (existing templates, unchanged)

- Fire column: `fire` width 320 height 448 duration 1 fps 30 hot FFF6C8 mid FFA23C cool E8582A scale 60 rise 380
  lick 0.35 flicker 0.25 body 0.55 taper 1.3 flame_height 1.1 threshold 0.12 softness 0.85 alpha_cut 0.12 core 0.45
  turbulence 24 glow 0.8 loop seed 3 edge_fade 0.2 contrast 55. Import alpha mode, ADDITIVE blend, loop, scale 0.95,
  on a bone that stretches (1.1, 0.2) -> (1.4, 0.9) -> (1.5, 1.05) over 0.85 s, alpha 0.3. Recolour = a re-render
  (three colours do not survive a two-colour tint).
- Orange smoke round it: `magic_smoke` 448 x 640, 1.5 s, luminous, color FF7A1E, light FFE8A0, rise 260, scale 130,
  threads 0.35, curl 60, fine_curl 24, swirl 14, spread 0.42, height_fade 0.9, motes 10, seed 5. Import additive,
  `tintable=True`, `tint=` the family colour (grade good: one frame set, any colour), loop, scale 1.15, alpha 0.8.
  Both go BEHIND the bar's labels.
- Background fireworks: `metal_sparks` size 384 duration 1.2 fps 30 rate 1 velocity 1.5 gravity 0.3 drag 1.6 extra 0.2
  life 1.1 hot FFFFFF cool B8B8B8 droplets 0 echoes 40 glow 1 flash 0.4 seed 21 (white sparks with long Echo streaks,
  drag-slowed: a firework burst). Import additive, `tintable=True`, ONE import and `copies=[{x, y, start, scale,
  tint}, ...]` for every burst of every screen (36 frames at 256 px shared by ~17 bursts), loop the animation on a
  fixed period (4.4 s board, 3 s Big, 2.8 s Mega). Draw them behind the balloon / background art.

### Measured facts and traps

- Timing (30 fps clip): highlight starts 1.0 s before the pop; pop flash 0.82-0.93 s; fire rises 0.12 s after the
  pop, the multiplier slides 0.1 s later; win label lands 0.13 s before the pop. Big Win: dim at +0, wash peak +0.13 s,
  number from +0.2 s; Mega flash at +0.03 s, wash peak +0.23 s; Total bloom +0.17 s. The gem / coin glint period is
  1.25 s with the coin peaking 0.17 s after the gem.
- Additive colour disappears on same-coloured or pale art: the cell glow and the Total sunburst are normal-blend, and
  the Big / Mega glows carry a normal-blend body under the additive light or a recolour reads as white.
- Spine 4 rotate / translate keys are RELATIVE to the setup pose: a bone with setup rotation 9 keyed 0 -> -5 turns
  9 -> 4. Porting absolute values doubled the offsets in the first try.
- A looping twinkle whose life crosses the loop end must be wrapped (evaluate it at 0 and T): keys built with
  `t % T` and sorted put a peak on the loop end and a 0 on the start (a pop every loop).
- Faithfulness: each recipe at defaults vs the clip build, FX only through the runtime: mean difference 0.00-0.35/255.

CHANGELOG: - Recipes `ornate_cell_glow`, `starburst_pop`, `blowout_flash`, `label_glint`, `echo_stamp`, `ghost_pop`, `fire_boost_flare`, `win_screen_intro`, `win_screen_glow`, `win_upgrade_flash`, `beam_sweep`, `sunburst_intro`, `sunburst_glow`, `face_flash` (`claude_spine/fx_win_screens.py`): the cascade-win moments and the Big / Mega / Total Win screens of a casual slot, rebuilt from a reference clip (winning-cell paint glow + ornate frame, starburst pop, wild blow-out, label glint, echo stamp, ghost number pop, the bar flare of a fire boost whose fire / smoke are the `fire` + `magic_smoke` templates via `ae_hint`, intro wash + burst, settling count-up glow, tier-upgrade flash + wash, turning beams, sunburst bloom + normal-blend sunburst with counter-turning ray fans, and a face flash for gems / coins). Procedural pictures only; label / face / ray art roles. Each recipe at defaults matches the hand-built clip version through the runtime within 0.35/255 mean. Fireworks are documented as one tintable `metal_sparks` import shared by copies. 37 tests.
