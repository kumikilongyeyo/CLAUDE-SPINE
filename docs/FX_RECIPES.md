# FX recipes: use, fork, mix

Authored FX layers lifted from real reference clips (a lotus blooming out of a magic book; light beams; a blue vortex
portal; a crackling electric frame), plus a bundle that plays the lotus set together. Spine primitives with procedural
textures: no art needed, tiny atlas, nothing to re-export when you recolour or resize. The slot families drive every
moment of a game: the spin, the win, the payout, features, bonus rounds, the screen's atmosphere and the UI. Three of them (portal,
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
| explosion | 1/t flash, Sedov-Taylor shockwave (r ~ t^0.4), fireball cooling white -> orange -> smoke and rising, debris with drag, embers, dust | one-shot 1.9 s |
| shine | instant bloom with a 1/t tail, two counter-turning ray stars, anamorphic streak, chromatic halo rings, twinkles; `pulse` loops it | one-shot 1.4 s |
| reel_stop | reel thud: the strip overshoots, squashes onto its floor and springs back (exact underdamped spring); dust with drag, tiny shock rings, flash, damped screen shake | one-shot 0.9 s |
| anticipation_reel | accelerating heartbeat on the last reel: frame glow, light column, edge flames or sparks; the neighbours dim, darker on every beat | window 2.4 s |
| magic_reveal | the seven lotus recipes, timed like the reference | bundle 13.2 s |
| sequence | any list of recipes with offsets into one animation (a win choreography as JSON) | bundle |
| win_banner | Big / Mega / Epic banner from one recipe: `tier=` picks the layers; the banner art slams in on a spring | bundle |
| payline | comet traces each winning line at constant arc-length speed; tail = its past, flash + ring + sparks per symbol, fading glow line; hit events with symbol index | window (length follows the line) |
| win_highlight | per-symbol 9-slice frame + glow, 1/t shine burst at the hit, exact-overshoot pop, masked sheen sweeps; pops your symbol bones | window 2.4 s |
| multiplier_stack | badges fly ballistic arcs with comet tails into the total; superposed spring pops, Sedov rings, final shine | window ~2.2 s |
| win_rollup | counter roll-up: coins fall in accelerating, tick pops, glow + floor glow by count and tier, landing pop + shine; tick events | window 3.2 s |
| coin_fountain | coins on drag parabolas with apex hang time, tumble, restitution bounces, friction slide, Euler's-disk rattle; fountain or shower; tiers | window 3.8 s |
| cascade_pop | winning symbols shatter into Voronoi shards (+ puff + hit burst); the symbols above drop through carrier bones with exact hops and squash | one-shot 1.3 s |
| near_miss | scatter halo brightens with the approach (inverse square), then implodes: ring sucked in and spinning up, colour drains to grey, sparks fall | one-shot 2.02 s |
| spin_blur | blur streaks over a spinning reel: lag behind it, stretch with speed (speed x shutter), catch up and fade on the stop; loop mode | window (stop + tail) |
| turbo_spin | speed lines framing the reels, stretched with speed; a travelling wave ripples through the symbol grid (carriers or own bones) | window 1.6 s |
| screen_shake | damped two-axis spring shake (incommensurate frequencies), 1/t white flash, red/cyan split converging; adds onto reel_stop's shake; tiers | one-shot 0.75 s+ |
| button_press | button squash (volume preserving) + exact-overshoot spring back through a carrier; ripple ring (sqrt t, 1/perimeter), shine micro-burst | one-shot 0.75 s |
| idle_shimmer | sheen band sweeping across a symbol clipped to its outline (R sin phi), shine glint on the hotspot, rest gap | loop 2.4 s |
| focus_glow | 9-slice line + glow + wash breathing on the LED curve; phase enter (1/t flash, no pop) / loop / exit (fade to 0) | loop 2 s |
| padlock | procedural padlock: unlock (shackle springs open, jiggle, pops off with a shine) / break (cracks, shards on parabolas) / lock (swings shut, bounces, clicks) | one-shot 1.75 s |
| popup | toast/panel springs in (exact overshoot + jelly) with puff flash + ring and a shine; phase out = anticipation + collapse | one-shot 0.9 s |
| saber | port of Video Copilot's Saber: hot core along a line / polyline / circle / rect, glow bands at doubling widths falling as (r0/r)^bias, travelling-wave writhe and flicker on integer cycles, draw on / off; 12 presets; the same beam in AE via the saber template (text cores too) | loop 2 s, hybrid |
| weather | rain / snow / embers / petals at terminal velocity, drag-lagged gusts, parallax depth layers, streaks along velocity, tumbling petals, rising flickering embers | loop 4 s |
| god_rays | fan of light shafts from a source, slow sweep, occluder dimming in sequence, dust in the beams (+ AE volumetric rays) | loop 8 s, hybrid |
| water_surface | capillary rings r ~ sqrt(t) at every symbol landing, glints; fx_water_land (+ AE caustics behind the reels) | window 2.6 s, hybrid |
| heat_shimmer | anchor + faint rising-wave stand-in above a fire; the refraction is AE (displacement map / schlieren) | loop 2 s, hybrid |
| fog_roll | fog bank or sandstorm rolling sideways: shear, rolling puffs, parallax, sand in saltation (+ AE volumetric bank) | loop 6 s, hybrid |
| lightning_storm | Poisson strikes across the top, 1/t flashes, sky glow, fallback bolts, fx_thunder delayed by distance (+ AE bolts per strike) | window 8 s, hybrid |
| wild_land | wild drops with gravity, restitution bounces, area-preserving squash; impact flash/rings/sparks; sticky frame + `<anim>_hold` loop | one-shot 2.58 s |
| expanding_wild | liquid fills the reel: 9-slice front, Poiseuille bulge, damped standing waves on a strand surface, rising column | window 2.4 s |
| scatter_trigger | scatters ring on land, lock on in turn, constant-speed beams charge the centre, burst (fx_scatter_bonus) | one-shot ~3.1 s |
| free_spins_transition | portal behind the screen, exponential infall with conserved angular momentum, puff, spring back to rest | one-shot 2.52 s, hybrid |
| pick_reveal | pick tile flips (exact spring overshoot) behind a puff; shine for a good pick, dark smoke + "no" shake or an ice shatter for a bad one; swaps your tile's art at edge-on | one-shot 1.7 s |
| hold_respin | locked cells glow and breathe (electric frame + smoke, exact loop); a respin counter ring depletes like a clock hand on a spring, refills under a rune flash | window (length from the respins) |
| jackpot_wheel | prize wheel with Coulomb + viscous friction stopping exactly on the winner; pointer clacks on every peg, segment glow trails the pointer, winner explodes | window 5.0 s + 1.9 s |
| meter_fill | energy drops fly into a meter; level rises with sloshing standing waves and Stokes bubbles; overflow burst + light beam at full | window (length from the drops) |

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

## Exaggerated real physics (the house style)

Every FX here follows real physics, then turns it up. The rules, so new recipes match:
- Impulses: instant attack (<= 50 ms), then decay like 1/t or e^-kt with a long tail (`shine`, explosion flash, lightning).
- Blasts: shockwave radius ~ t^0.4 (Sedov-Taylor) and it fades as it thins; the fireball balloons the same way, cools
  white -> yellow -> orange -> dark smoke, and the smoke rises on its own heat (y ~ t^2).
- Thrown things: parabolas with gravity; air drag makes velocity decay e^-kt; sprites are turned and STRETCHED along their
  velocity (debris, splash drops). Landings make their own small event (splash landing rings).
- Water: capillary rings spread as sqrt(t); a splash has a crown AND a central jet that pinches off a drop.
- Vortices: inner layers spin faster (differential rotation); infalling specks speed up as r^-1.5 (Keplerian).
- Hot gas (fire, haze): RISES and accelerates; a fast small turbulence rides over a slow big one; flames flicker ~11 Hz; a
  loop with real drift is rendered twice as long and crossfaded (`AEFX.loopify`), then thresholded AFTER the crossfade.
- Smoke puffs: burst (expansion with exponent 4), drag brings it to a crawl, it rolls as it slows (turbulence grows with
  time), is lit from above, and erodes from its thin parts as it dilutes.
- Lightning: stepped leader grows across, return stroke snaps bright + branches, branches die first, channel narrows and
  dims, restrikes hit the same channel with new forks; the flash is the channel's own air-glow, never a full-frame solid.
- Dendrites (frost): tips race then slow (diffusion-limited), branch at 60 degrees, stop on contact, glow at the growth
  front, then a late wave of needles frosts everything over.
- Lags: things dragged along by something else follow a first-order lag s' = (v - s)/tau: they trail, then catch up by tau x v after it stops (spin_blur).
- Falling and rising particles: terminal velocity, launch speed decaying to it as e^(-t/tau); sideways Stokes drag toward
  the wind, so a gust reaches a particle attenuated by 1/sqrt(1 + (w tau)^2) and late by atan(w tau) / w; parallax = 1/distance.
- Lightning: Poisson strikes with dead time; flash 1/t per return stroke, channel e^(-t/50 ms); thunder delayed by distance.

## Win tiers, sequences and the banner

`tier=` (small | medium | big | mega | epic) works on EVERY recipe: one recipe covers every win size. It multiplies the
scale (0.8 .. 1.5), the default count (0.6 .. 2.6, so more sparks, coins, debris), and the time of one-shots (0.85 .. 1.4),
then applies the recipe's own `tiers` overrides (shown in the listing); options you pass win over both, and an explicit
`count` or `duration` is never scaled. Medium is the recipe as authored.

`sequence` plays any list of recipes into one animation, so a whole win choreography is data:

    fx_recipe recipe=sequence project=p.json name=win_big tier=big options={steps: [
        {recipe: payline, start: 0},
        {recipe: shine, start: 0.4, dx: -160},
        {recipe: coin_fountain, start: 0.6, dy: -200, tier: mega}]}

Each step takes any fx_recipe argument; `dx`/`dy` offset it from the bundle centre (design units), `scale` and
`intensity` multiply the bundle's, `tier` overrides it. Steps chain in draw order. The bundle fires `fx_<name>_end` at its
last key (or `length`), which also fixes the clip length for the game.

`win_banner` is the tiered banner: big = shine + flare + twinkles; mega adds an explosion; epic opens with three strikes,
then the explosion and a rune ring under the banner. `options={banner: bone}` slams the game's banner art in from the
camera through a carrier bone (scale falls in with an accelerating, gravity-like shrink, lands, squashes shorter by the
tier's punch and wider by `squash` x punch on an exact spring, settles exactly on 1). Its layers go BEHIND the banner art
unless you set front_of / behind, so the text is never washed out. `skip` drops layers, `extra` adds sequence steps.
Events: fx_win_banner, fx_win_banner_land (the impact: the moment for the big sound), every layer's own, fx_win_banner_end.
`examples/build_banner_demo.py` renders the three tiers (`docs/win_banner.gif`).

## Reel moments (every spin)

`reel_stop` and `anticipation_reel` (module `fx_reels.py`) are the two FX a slot plays on every spin. They are the first
recipes that MOVE the game's own bones, and they do it without touching any key, constraint or weight you own:

    fx_recipe recipe=reel_stop project=p.json x=-162 start=0.55 into=spin options={reel: reel0, shake: machine}
    fx_recipe recipe=anticipation_reel project=p.json x=162 start=1.05 duration=2.2 into=spin
              options={edge: flames, dim: [[-162, 0, 150, 450], [-324, 0, 150, 450]]}
    fx_recipe recipe=reel_stop project=p.json x=162 start=3.15 into=spin options={reel: reel2, shake: machine}

- `reel=` names the reel strip bone. A pure-translation carrier `fx_squash_<reel>` is inserted above it AT THE STRIP'S
  BASE (x, y - height/2), so the squash pivots on the floor; the reel keeps every key it had (the spin itself, its
  arrival). Without `reel=`, the result's `squash_bone` is a bone to parent the reel art under.
- `shake=` names the bone to shake (the machine or screen container, never root): carrier `fx_shake_<bone>`. Every stop
  in the same clip ADDS its shake to that carrier, so overlapping stops sum instead of the last one winning.
- The spring is solved exactly: the arrival speed is chosen so the deepest point is `overshoot`, with `bounce` Hz and
  `damping` (0..1). The squash follows the spring's compression and stretches on the rebound; the clip ends exactly at rest.
- Put the reel's arrival in your own keys (the column coming in from above at spin speed, ending at rest on the stop
  time) and start reel_stop on that same time: the spring takes the strip from there.
- `anticipation_reel` is a window: `duration` = how long the reel teases. Beats start `lead` in, each period is the last
  one times `accel` down to `min_period`; the result lists `beats` and `periods`, and `fx_anticipation_beat` fires on
  every lub for the heartbeat sound. `dim` panels default to one reel either side (`gap` apart); pass your own list for
  the last reel of five. `edge` = flames | sparks | none; both return `ae_hint` (AE `fire` tongues / `electric_frame` line).
- Both put their normal-blend layers (dust, dim panels) first in their run, so each recipe costs 2 batches at most.
- On light reel art, additive glow saturates fast: lower `intensity` or darken `color` rather than adding more layers.
  `examples/build_reels_demo.py` builds the three-reel demo (`docs/reel_stop.gif`).

## Spin moments (around every spin)

`near_miss`, `spin_blur`, `turbo_spin` and `screen_shake` (module `fx_spin.py`) fill the rest of a spin around `reel_stop`
and `anticipation_reel`. Like those, the ones that MOVE your bones do it only through carrier bones, and add onto any keys
an earlier recipe left on the same carrier:

    fx_recipe recipe=turbo_spin project=p.json into=spin duration=3 options={bones: [s00, s10, s20, s01, ...], kick: 0.05}
    fx_recipe recipe=spin_blur project=p.json x=-162 start=0.7 into=spin options={stop: 1.0}        -> reel_stop at 1.7
    fx_recipe recipe=screen_shake project=p.json start=2.05 into=spin tier=big options={shake: machine}
    fx_recipe recipe=near_miss project=p.json start=2.88 into=spin parent=<scatter bone> options={dy: 420, miss: 150, closest: 0.32, fizzle: 0.62, follow: false}

- `spin_blur` models the reel speed (motor ramp, cruise, constant-deceleration brake to 0 at `stop`) and the streaks follow
  it through a first-order lag: they trail during the spin and catch up after the stop (the result's `catch_up` = lag x
  speed at the stop). Length = speed x `shutter`, opacity follows speed; rows are clamped to the reel window. Start it when
  the reel launches and give `stop` = reel_stop's start - its start. `mode=loop` is an exactly closed cruise segment (speed
  is snapped; read it back from the result). Additive white streaks need dark-ish reels; on light reels tint them or lower `intensity`.
- `turbo_spin`: speed lines in two bands outside the reel area (`gap`, `band`), each stretched to its own speed x `shutter`.
  The grid ripple is a travelling wave (phase velocity `wave_speed`, `freq`, ringing down over `ring`, amplitude falling by e
  over `reach`); `wave=across` runs left to right, `down` top to bottom. `bones=` drives carriers `fx_ripple_<bone>` above
  your symbol bones; without it the recipe makes its own grid bones (result `grid_bones`) to parent symbols under.
  `arrivals` lists when the front reaches each one.
- `near_miss`: the anchor is the payline point (follow=true) or the symbol itself (follow=false, parent= the symbol bone,
  the halo then rides every key of the symbol including reel_stop's bounce). Brightness is the inverse-square law of the
  approach distance; fire your "aww" sound on `fx_near_miss_fizzle`.
- `screen_shake` shakes `shake=` through `fx_shake_<bone>`, the same carrier reel_stop uses: a big-win shake on top of three
  reel stops sums with them. `ratio` must not be a whole number (commensurate axes draw a clean repeating figure). Per win
  size, `tier=` small | big | mega | epic. `win_banner options={shake: bone}` fires it on the banner's impact.
  `examples/build_spin_demo.py` builds the demo (`docs/spin.gif`).

## Wins (after the reels stop)

`payline`, `win_highlight`, `multiplier_stack`, `win_rollup` (module `fx_wins.py`) are the win presentation. Chain them
in one clip; the payline's result hands the hit times straight to the highlight:

    fx_recipe recipe=payline project=p.json into=win options={lines: [[[-280,140],[-140,0],[0,-140],[140,0],[280,140]], [[-280,0],[280,0]]], stagger: 0.85}
    fx_recipe recipe=win_highlight project=p.json into=win duration=6 options={cells: [[x, y, 134, 134, t] for each hit], symbols: [sym00, sym11, ...]}
    fx_recipe recipe=multiplier_stack project=p.json start=2.55 into=win options={sources: [[-280,140],[0,-140],[280,140]], target: [0, 292]}
    fx_recipe recipe=win_rollup project=p.json y=-300 start=3.55 duration=3 into=win tier=big

- `payline`: the head runs at CONSTANT SPEED BY ARC LENGTH (`speed` units/s after an `ease` ramp from rest), so a long
  diagonal takes longer than a short hop. The tail is the head's past (`tail` = seconds of lag, so it is longer where it is
  fast). The glow line left behind fades from its start first (`linger`). `fx_payline_hit` fires at every symbol with the
  symbol index in its int field and `line<k>` in its string field; `fx_payline_end` (int = line) when the head lands.
  The result's `hits` = [[x, y, t], ...]; the length follows the line, not `duration`.
- `win_highlight`: one cell per winning symbol, each lit at its own time: frame + glow snap on with a 1/t shine burst, the
  cell pops (first overshoot exactly `pop`), a sheen band sweeps every `sheen_period`. The sheen is a generated flipbook
  pre-masked to the cell (no clipping attachment). `symbols=` pops YOUR symbol bones through carriers, same pop.
- `multiplier_stack`: each badge flies a true parabola with a comet tail into the total and is absorbed (its bone ends at
  scale 0 on the target). Parent your "x2" art under the result's `badge_bones`. The total pops on spring kicks that ADD
  (a fast second hit lands on the first one's ring-down); `growth` makes each later kick harder. `total=` pops your bone.
- `win_rollup`: `duration` = the whole roll-up; the count runs for `duration - settle`, ticking at `rate` Hz
  (`fx_rollup_tick`, int = tick index: step your digits there) and lands on `fx_rollup_end` with the big pop and shine. Coins
  fall in from rest, accelerating; the glow and the floor glow climb with the count. `tier=` small | big | mega | epic sets
  glow, coins, pops, tick rate and spread (`RECIPES["win_rollup"]["tiers"]`). `counter=` pops your counter bone; otherwise
  parent the text under `counter_bone`.
- Coins are the only normal-blend layer (drawn first in the run); a clip with all four costs a few batches.
  `examples/build_wins_demo.py` builds the demo (`docs/wins.gif`).

## Payouts

`coin_fountain` and `cascade_pop` (module `fx_payouts.py`) pay a win out. The coins are real projectiles; the cascade
moves the game's own symbol bones the `reel_stop` way, through carrier bones, never through your keys.

    fx_recipe recipe=coin_fountain project=p.json y=-200 into=bigwin options={floor: -50, height: 440} tier=mega
    fx_recipe recipe=coin_fountain project=p.json y=-200 into=bigwin start=0.8 options={mode: shower, height: 600, floor: -50}
    fx_recipe recipe=cascade_pop project=p.json y=70 into=cascade art={symbol: gem.png}
              options={cells: [[-136, 0, 128, 128], [0, 0, 128, 128], [136, 0, 128, 128]],
                       drop: [[sym_0_0, 136], [sym_0_1, 136], [sym_0_2, 136]]}

- Every coin flies on a closed-form drag parabola: x = vx/k (1 - e^-kt), y = (vy + g/k)/k (1 - e^-kt) - g t/k. The launch
  speed is solved so the apex is exactly the coin's height, the sideways speed so it first lands exactly on its spot.
- HANG TIME: the clock is warped around the apex (vy = 0): dt/ds = 1 + hang e^-((s - s_apex)/w)^2, so at the top the coin
  moves 1/(1 + hang) as fast and normally again long before it lands. It changes when, never where. `hang: 0` is real time.
- Landings: each hop leaves at `restitution` x the speed it came in with (heights fall by e^2), a Coulomb friction impulse
  takes mu (1+e)|vy| off the sideways speed, then the coin slaps flat (`flat` = scaleY), slides to a stop at mu g and rattles
  like Euler's disk (the angle dies as (1-t/T)^(1/3) while the rattle speeds up), exactly still at `settle`.
- In the air it tumbles: fx.py's coin flipbook plus an in-plane spin that decays to whole turns, so it rests level. A coin
  picture (`art={coin: ...}`) flips by a scaleX turn instead. `depth` spreads the landings over the counter's depth: farther
  coins sit higher, smaller and behind. Shadows tighten as a coin comes down.
- `coin_fountain` is a window: `duration` is the whole clip; launches spread over `spread` seconds (clipped so every coin
  rests before the `fade`). `fx_coin_land` fires on first landings, thinned to `landings`. `tier=` sets count/height/duration.
- Heavy counts belong to the game's particle emitter: more than 80 coins is an error; start the emitter on
  `fx_coin_fountain` with the numbers in the result's `engine_hint` and keep the Spine coins for the hero coins in front.
- `cascade_pop`: the symbol swells and cracks for `pop` seconds, then shatters into Voronoi shards cut from its own picture
  (`art={symbol: ...}`, else a procedural gem) that fly out with drag and fall; a dust `puff` and a `hit_burst` per cell
  (`puff`/`hit` False to slim it; ~24 slots per cell). Hide your own symbol on `fx_cascade_pop`; `fx_cascade_shatter` fires
  per cell on the break.
- `drop=[[bone, distance(, height)], ...]`: each bone (at the symbol centre) falls `distance` into the gap through a carrier
  `fx_drop_<bone>` pivoting on its base: free fall, then exact restitution hops (first hop e^2 of the drop) and a squash
  spring; it ends at -distance, at rest. `fx_cascade_land` fires on each first impact.
- Both put every normal-blend slot first in their run (cascade_pop reorders the puff's lobes too): 2 batches each. On light
  symbols the additive burst saturates fast: `flash` and `dust_alpha` turn the hit burst and dust down.
  `examples/build_payouts_demo.py` builds the demo (`docs/payouts.gif`).

## Feature triggers

`wild_land`, `expanding_wild`, `scatter_trigger` and `free_spins_transition` (module `fx_features.py`) announce a feature.
Like the reel moments, two of them move the GAME's bones through inserted carrier bones and never touch your keys:

    fx_recipe recipe=wild_land project=p.json x=162 into=wild options={wild: wild_symbol}
    fx_recipe recipe=expanding_wild project=p.json x=0 into=expand front_of=cabinet options={fade: 0}
    fx_recipe recipe=scatter_trigger project=p.json into=bonus options={scatters: [[-162, 150, 0], [0, -150, 0.35], [162, 0, 0.7]], centre: [0, 318]}
    fx_recipe recipe=free_spins_transition project=p.json into=fs options={screen: machine}

- `wild_land`: the wild falls from `drop` and lands at exactly `fall` s (gravity is solved from them), bounces with
  restitution `bounce` (each bounce bounce^2 as high), stretches along its speed, squashes area-preserving on every
  contact. `wild=` inserts `fx_drop_<bone>` at the cell's BASE, so the squash sits on the floor. The sticky frame then
  breathes, and `<anim>_hold` is a loop one `pulse` long that starts on the clip's last frame: play the clip, then
  loop the hold for as long as the wild is sticky. `fx_wild_impact` / `fx_wild_bounce` time the thuds.
- `expanding_wild`: the fill is a 9-slice whose FRONT corner bones are keyed (the setup pose is the full reel, so it
  ends on rest); the surface is a strand mesh whose row bones carry the wave: the front leads in the middle while it
  flows (Poiseuille), then sloshes in damped standing waves. Keep the fill opaque (`fill_alpha` 1): below 1 the
  surface band shows where it overlaps the fill. Additive light over an opaque gold fill whitens fast, so only a faint
  column and the frame line (just outside the reel) sit on it.
- `scatter_trigger`: `scatters` = [[x, y, land_time], ...]; with `need` or more they lock on in landing order and beam to
  `centre` at one speed (`beam_speed`); the centre charges 1/N per beam and bursts at `fx_scatter_bonus` (the recipe's
  own `fx_scatter_trigger` marks its start). `fx_scatter_land` carries int = how many have landed (pitch the chime up),
  `fx_scatter_lock` int = order.
- `free_spins_transition`: `screen=` is the whole screen container (not root). The portal goes behind its first slot
  and the puff in front of its last, automatically. The screen reaches scale 0 exactly at `fx_free_spins_in`: swap
  skins/attachments on that key; it springs back out at `fx_free_spins_out` and ends at scale 1, rotation 0.
  `ae_hint` is the AE portal_ring (parented to the portal bone, so it opens and collapses with it); `smoke_hint` is
  smoke_haze over the puff. `swirl` is the total turn, `core` keeps the spin finite at scale 0 (smaller = later whip).
- `examples/build_features_demo.py` builds all four on a 3x3 machine (`docs/features.gif`). Use dark reel backs:
  additive light on cream reels only turns them white.

## Bonus games

`pick_reveal`, `hold_respin`, `jackpot_wheel`, `meter_fill` (module `fx_bonus.py`) are the bonus-round moments. They are
BUILT FROM other recipes: a pick reveal is a flip plus a real `puff` plus a real `shine` (or `ice_shatter`), run inside
the same clip, run of slots and group bone, on the same clock. At the end each re-sorts its run so every normal-blend
layer comes first (one normal batch, one additive batch), whatever its members did.

    fx_recipe recipe=pick_reveal project=p.json x=-200 into=pick front_of=tile0
              options={tile: tile0, swap_slot: tile0, swap_to: tile_prize}
    fx_recipe recipe=pick_reveal project=p.json x=0 start=0.6 into=pick options={good: false, bad: ice}
    fx_recipe recipe=hold_respin project=p.json into=hold options={cells: [[-130, 130, 120, 120], [130, 0, 120, 120]],
              respins: 3, period: 1.0, resets: [2], ring_y: 290}
    fx_recipe recipe=jackpot_wheel project=p.json into=wheel duration=4.6 front_of=wheel_art
              options={segments: 12, winner: 5, spins: 3, wheel: wheel}
    fx_recipe recipe=meter_fill project=p.json into=meter front_of=glass options={levels: [0.25, 0.5, 0.75, 1.0]}

- `pick_reveal`: the tile is flicked over (theta ~ t^2); its width |cos theta| goes through 0 with a kink at edge-on
  (a rigid rotation). The face that comes up starts at width 0 at the flip's own speed and is caught by a spring whose
  damping is SOLVED so it overshoots by exactly `overshoot` (result: `zeta`, `peak_at`). The puff covers the edge-on
  moment: swap your art on `fx_pick_swap`, or let `swap_slot`/`swap_to` key it. `tile=` flips your own tile through a
  carrier (`fx_pick_<tile>`); without it a procedural back/front is drawn and the back waits from the clip start.
  good=false: `bad: smoke` (dark puff + a damped "no" shake) or `bad: ice` (ice forms, cracks, shatters; the face goes).
- `hold_respin`: the counter is ONE band mesh on a circle of bones: the sweep is where the bones are, so it depletes like
  a clock hand without clipping. Ticks are an escapement spring (overshoot exactly `recoil` of a segment); `resets` lists
  the ticks after which a symbol lands: the counter refills under a rune_ring flash timed to peak on the refill.
  The cells are electric_frame + additive smoke_glow built as ONE respin and tiled exactly, breathing `breaths` times per
  respin, so the whole window loops at the respin period. The length follows the respins (`duration` is not used);
  `fx_respin_tick` carries the respins left in its int.
- `jackpot_wheel`: w' = -a - k w (Coulomb + viscous) in closed form, a and w0 solved so it stops at exactly `duration`
  on exactly `winner` (0 = the segment at the top at rest, clockwise). `viscous` = k (0 = pure Coulomb: a constant
  deceleration). `wheel=` rotates your wheel bone through a carrier, `pointer=` ticks your pointer bone (pivot at its
  origin); otherwise a pointer is drawn and the result's `wheel_bone` is a bone to parent your wheel art under. Every
  peg passing the pointer fires `fx_wheel_tick` (int = segment now under the pointer): one click sound each.
- `meter_fill`: drops are real `projectile`s landing on the moving surface. The surface sloshes as standing waves with
  water-wave dispersion (shallow liquid sloshes slower), the level rises critically damped, bubbles rise at their Stokes
  speed (big ones faster) and pop at the surface. `levels` = the level after each drop; reaching 1 = overflow +
  `light_beam` + `fx_meter_full`. The liquid is a normal-blend mesh on surface bones, so it hides the empty meter: put
  your glass rim AFTER the run. The meter stays full after the clip.
- On bright art (a wheel), additive glow reads weaker than on dark reels: raise `boom_size` or `intensity`.
  `examples/build_bonus_demo.py` builds the four scenes (`docs/bonus.gif`).

## Ambient (screen-level atmosphere)

Module `fx_ambient.py`. These fill the SCREEN, not a symbol: `x, y` is the centre of the area (`width` x `height`, about
the 720-unit canvas), except `god_rays` (x, y = the light source) and `heat_shimmer` (x, y = the top of the fire).
Each is Spine alone and works without AE; four also return an `ae_hint` for the After Effects version of the effect.

    fx_recipe recipe=weather project=p.json options={kind: rain}                       -> fx_weather, loops 4 s
    fx_recipe recipe=weather project=p.json options={kind: petals, wind: 40, layers: 2}
    fx_recipe recipe=god_rays project=p.json x=-330 y=350 options={angle: -58}         -> ae_hint: god_rays
    fx_recipe recipe=water_surface project=p.json into=spin options={lands: [[-300, -55, 0.3], [-150, -55, 0.6]]}
    fx_recipe recipe=fog_roll project=p.json y=-220 options={kind: sand}               -> ae_hint: fog_roll
    fx_recipe recipe=lightning_storm project=p.json duration=12 options={rate: 0.4}     -> fx_lightning_strike, fx_thunder

- `weather`: every particle moves at its kind's terminal velocity and is pushed sideways by Stokes drag toward a mean
  wind plus a slow gust (a wave travelling with the wind). Solved exactly, a raindrop (tau 0.85 s) lags and smooths
  the gust (result `gust_gain`, `gust_lag`), a snowflake follows it. `layers` sit at distance 1..`depth`: speed, drift
  and size go as 1/distance, far ones are paler and more numerous; each layer is a bone (result `layers`) the game can
  parallax further with the camera. Petals are normal blend (opaque), the rest additive.
- `god_rays`: the fan sweeps `sweep` degrees once per loop; `flicker` is a cloud pattern drifting across the source, so the
  rays dim one after another, not at random. The AE template has the SAME sweep phase: put its flipbook in with
  ae_fx_to_spine using the hint's x, y, scale (the comp's source point lands on the recipe's group bone).
- `water_surface`: one landing per symbol, rings r ~ sqrt(t), dimming as 1/sqrt(r); `fx_water_land` (int = index) on
  each one for the plop sound. The caustics hint goes BEHIND your reel slots (`behind=` your first reel slot).
- `heat_shimmer`: Spine cannot refract. The AE template renders `output=map` (a looping displacement map for an engine
  distortion shader on `anchor_bone`), `output=shimmer` (its schlieren image, additive, for ae_fx_to_spine) or
  `output=preview` (the refraction over an image, to judge it in AE). The recipe's own faint filaments are a stand-in;
  turn its intensity down once the AE layer is in.
- `fog_roll`: puffs flow faster near the top (`shear`) and roll forward; sand adds grains hopping in saltation. Normal
  blend, drawn in one batch. The AE `fog_roll` template is the volumetric bank (horizontal convection, loopified).
- `lightning_storm`: strikes are a seeded Poisson process with dead time (`rate` per second, `min_gap`), each at a random
  distance: brightness ~ 1/d, thunder `fx_thunder` arrives d / `sound_speed` later (km/s, exaggerated ~6x so it follows
  in game time) with float = km, volume = 1/d, balance = pan. Its thunder always lands inside the window (late strikes
  are close ones). For AE bolts render each `ae_hint.variants` entry with ae_template lightning, then ae_fx_to_spine
  once per `ae_hint.strikes` entry (x, y, scale, hit_ae/hit_at put the return stroke on the strike), and set
  `bolt: false` to drop the Spine fallback bolts; flashes and thunder stay. `tier=` raises the rate on big wins.
- The three new AE templates (god_rays, heat_shimmer, fog_roll) are checked against a mock of the AE object model in Node;
  they have not been rendered in After Effects yet, so a few effect property names may need a fix on the first real run.
- `examples/build_ambient_demo.py` renders every one over a procedural backdrop (`docs/ambient.gif`).

## UI and symbol polish

`button_press`, `idle_shimmer`, `focus_glow`, `padlock`, `popup` (module `fx_ui.py`). Like the reel moments they move
your own bones only through inserted carrier bones, and they compose other recipes: a `shine` micro-burst rides the
button's overshoot, the shimmer's glint and the popup's peak; the popup opens with a `puff` (lobes=False).

    fx_recipe recipe=button_press project=p.json x=0 y=-300 into=ui front_of=spin_btn options={button: spin_btn, width: 200, height: 80}
    fx_recipe recipe=idle_shimmer project=p.json into=idle front_of=gem duration=2.4 options={width: 150, height: 150, corner: 26}
    fx_recipe recipe=idle_shimmer project=p.json into=idle options={slot: gem}          (clips to the part's own outline)
    fx_recipe recipe=focus_glow   project=p.json into=hover options={phase: enter}       then phase loop, then phase exit
    fx_recipe recipe=padlock      project=p.json into=unlock options={mode: break, size: 120}
    fx_recipe recipe=popup        project=p.json into=toast front_of=panel options={panel: panel, under: panel}

- Springs are exact: you give the overshoot (a fraction past rest) and the frequency, the damping is solved from it,
  so the first peak is exactly 1 + overshoot; the ringing tail is windowed after it so the clip ends exactly at rest.
- `button=` / `panel=` name your bone: a pure-translation carrier `fx_press_<bone>` / `fx_pop_<bone>` is inserted at
  the pivot (`pivot=bottom` squashes onto the base). Several presses in one clip multiply on the same carrier. Without
  it, the result's `button_bone` / `panel_bone` is a bone to parent your art under (its origin is the pivot).
- The press squash keeps volume (sx^2 * sy = 1); the popup's jelly keeps it too (sx^2 * sy = s^3). A popup that enters
  later in a clip is held at scale 0 from the clip start (Spine shows the SETUP pose before a timeline's first key).
- `idle_shimmer` is a loop: `period` (or `duration`) = sweep + glint + rest. The band moves like a highlight over a
  dome (R sin phi: fast mid, lingering and fading at the rims), and the glint fires when it crosses `hotspot`
  (fractions of the box). `slot=` clips to that slot's hull (one clipping polygon, <= 32 vertices).
- `focus_glow` breathes on the breathing-LED curve (e^sin: dim longer, bright briefly). `enter` ends exactly on the
  loop's first frame and `exit` starts on it, so enter -> loop -> exit chain with no jump. Resize live by moving the
  corner bones in the result (line + wash share one set, the glow has its own).
- `padlock` is the only recipe here with solid art (normal blend, first in its run). `mode=break` cuts its shards from
  the body picture, so `art={"body": ...}` shatters YOUR lock. Sub-recipe art is prefixed: `art={"shine_rays": ...}`.
- UI 9-slices are `tex_ui_frame` (1 texture px = 1 unit, any corner radius, exactly 0 at the border).
  `examples/build_ui_demo.py` builds the six-cell demo (`docs/ui.gif`).

## Saber (a port of Video Copilot's Saber)

Saber is Video Copilot's free After Effects plug-in for energy beams, lightsabers, lasers, neon, electric and fire
outlines and haze. It is ported twice, sharing ONE preset table (`PRESETS` inside `ae_templates/saber.jsx`):

    fx_recipe recipe=saber project=p.json options={preset: default, start: [-240, -60], end: [230, 70]}
    fx_recipe recipe=saber project=p.json into=win options={preset: neon, core: rect, rect: [440, 200, 40], draw: on}
    fx_recipe recipe=saber project=p.json options={preset: fire, core: circle, radius: 105}      -> ae_hint: saber
    ae_template name=saber params={preset: gold, core: text, text: "BIG WIN", draw: on}          (text cores: AE only)

- Presets: default (blue saber), red, green, purple, gold, neon, laser, electric, fire, energy, plasma, haze. Any style
  option (color, core_color, core_size, intensity, spread, bias, distortion, noise_size, noise_speed, flicker, haze)
  wins over the preset; in the AE template the style parameters default to null = take the preset.
- Glow falloff: a glowing tube's light falls off as 1/distance. Both halves build the glow from octaves: bands (Spine)
  or Gaussian-blurred copies (AE) at doubling radii whose peaks fall as (r0 / r)^bias. bias 1 = equal light per octave
  = 1/r (the real thing); < 1 spreads into haze; > 1 tightens into a laser.
- Distortion: Spine moves the shared row bones sideways with travelling waves (wavelengths noise_size x 1, 1/2, 1/4, each
  moving a whole number of cycles per loop; around a closed path a whole number of waves, so no seam); AE uses
  Turbulent Displace with a cycled evolution. Flicker is a product of two sines with integer cycles. Both loop exactly.
- Draw on / off (Saber's start / end offset): Spine collapses the rows past the head onto it and shrinks them, AE uses
  Trim Paths (Linear Wipe for text). Events fx_saber_on / fx_saber_off; the AE result says seq_mode once.
- Every band is a strip mesh on ONE set of row bones, so the whole beam costs one draw call and no deform keys. Wide
  bands use normals smoothed over their own width and are clamped to 0.65 x the local radius of curvature, so they
  never fold in a tight ring; polyline corners are rounded (Chaikin) like Saber's round joins; open ends fade out
  along the beam instead of stopping square.
- The ae_hint renders the same beam in AE: comp centred on the recipe's group bone, `px` comp pixels per design unit,
  additive; put it in with ae_fx_to_spine using the hint's args, then lower or drop the Spine beam.
- Why not the plug-in itself: a template that needs Saber renders nowhere Saber is missing (a render farm, a teammate's
  aerender). This port uses AE's own effects only. `examples/build_saber_demo.py` renders `docs/saber.gif`.

## Piñata family (one picture kit, swap in your texture pack)

Twelve effects lifted from a candy / piñata slot's free spins, all drawn from ONE kit of 23 neutral pictures (white
glows Spine tints, plus normal-blend confetti, coin, smoke and two label placeholders). Every picture is also an `art=`
role with the same name, so an artist's pack drops in by name and the motion stays the same:

    fx_recipe recipe=wild_transform project=p.json x=-144 y=43                              -> event wild_pop
    fx_recipe recipe=wild_glow project=p.json into=fx_wild_transform x=-144 y=43 start=0.6  (seamless hand-off)
    fx_recipe recipe=bubble_pop project=p.json options={cells: [[-288, 41], [3, 41]], stagger: 0.03}  -> bubble_burst
    fx_recipe recipe=tier_swap project=p.json options={old: card_big, new: card_mega, radius: 220}    -> tier_swap
    fx_recipe recipe=jar_burst project=p.json art={glow_soft: pack/glow_soft.png, rays: pack/rays.png}
              options={gain: {glow_soft: 0.5, rays: 0.6}, thick: {light_streak: [1, 2.4]}}

- Cell recipes, centred on the anchor, one cell = `cell` (144): wild_glow (loop: breathing glow, tilted orbit ring,
  stars bright on the near half), wild_transform (white cell flash with a pink rim peaking in 1-2
  frames, sparkles, the WILD art popped through a carrier with wild=; ends on wild_glow's first frame; style=bubble
  keeps the older swirling-bubble intro), mult_cell_glow (loop), cell_pop, confetti_burst (drag + gravity + flutter +
  3D flip, six shapes).
- Board recipes, positions relative to the anchor (defaults = the clip's 5x4 board on a 721 x 1200 screen, anchor at the
  centre): mult_streak (row flashes, streak, the number punches in then DROPS into the win bar, accelerating; to=sign arcs it
  up into the sign instead), wild_merge (comets oriented along curved paths
  converge on a target), coins_to_bar, bar_sweep (loop), jar_burst (bursts ripple out from the centre, then a big flare
  with colour-split rings; the X label comes OUT of the sign and wanders down onto the winning cell `land`, the flare
  riding behind it; x_path=flare_to_sign for the reverse), bubble_pop (the cascade removal: cyan glass bubble for 1
  frame, burst into confetti in ~9), tier_swap (BIG -> MEGA -> SUPER card swap through a white ribbon ring, ~9
  frames; old= / new= card bones via carriers; event tier_swap = switch title and backdrop), banner_backdrop (exact loop behind a win banner: turning rays,
  title shine, number bar, coin + confetti rain). pinata_hit is anchored on the thing that bursts; `land` = fireball targets.
- A real pack is never tuned like the kit. Two shared options fix it without repainting: `gain` = {picture: alpha
  multiplier} (a fuller glow_soft turns overlapping glows into a white blob: 0.5), `thick` = {picture: [w x, h x]} (a
  hairline light_streak / shine_band vanishes when stretched: [1, 2.4] / [2.6, 1]). `fx_pinata.pack_tuning()` holds the
  values measured on the first real pack.
- Blend runs: coins_to_bar adds every coin first and every flash after, so 10 coins cost 2 draw calls, not 20; jar_burst
  puts all smoke (normal) before all flashes (additive) for the same reason.
- `examples/build_pinata_demo.py` renders `docs/pinata.gif` on a procedural board.
- Corrected from a frame-by-frame breakdown of the reference clip (clip-breakdown skill): the cyan bubble is the
  CASCADE pop (bubble_pop), not the WILD transform (a white flash); the multiplier drops into the WIN BAR; the X comes
  FROM the sign. Before trusting a first read of a clip, break it down at full frame rate around every beat.

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

## After Effects -> Spine, end to end (lightning, auras, flame trails, speed lines)

The workflow that shipped a whole free-spins sequence (two-fighter slot: reel fire, scatter lightning, fire and
electric auras, clash fireballs, flame trails, focus lines), in the order that saves the most iterations:

1. Contact sheet of the clip (16-24 frames) and a GRIDDED still: measure reel centres, rows and anchor points in
   pixels before placing anything (a guessed layout cost a full rebuild: the board had 5 rows, not 4).
2. Split every effect into "needs real noise" (lightning, flames, auras, smoke, fireballs: AE) and "light that moves"
   (flashes, hit bursts, streaks, glows, flares, speed lines: Spine recipes). The second group is most of a clip.
3. Build ALL the AE comps in one script with `ae_template` (fresh comp names each attempt: AE caches by name), save,
   render each with aerender into a frames folder, and judge them on a contact sheet before going near Spine.
4. Bring each comp in with `ae_fx_to_spine` (frames_dir= the rendered folder) on its own bone; aim and stretch with
   that bone (sequences now follow a rotated / scaled parent). 256 px is plenty for a looping aura.
5. Mix Spine recipes into the same animation with `into=`, preview over a frame of the clip, tune, export.

Recipes for the parts:

    ae_template name=lightning params={width: 320, height: 640, start: [0.45, 0], end: [0.55, 1], branching: 0.45}
    ae_template name=fire_aura params={size: 512}                                    -> fire ring, loop, mode alpha
    ae_template name=fire_aura params={hot: F0FFFF, mid: 3AA8FF, cool: 1030B0}       -> electric blue aura
    ae_template name=fire params={width: 320, height: 640, taper: 2.9, body: 0.2, core: 0.32, edge_fade: 0.16}
              -> a long flame trail: aim its bone AWAY from the motion, base just behind the fist, NORMAL blend
    ae_template name=fire params={width: 1024, height: 320, core: 0.18, body: 0.06, scale: 24, alpha_cut: 0.34}
              -> a flame strip to stand along a reel edge (rotate its bone 90, stretch x to the reel height)
    ae_template name=smoke_puff params={light: FFF3A0, mid: FF7A1C, shadow: 3A2018}  -> clash fireball
    fx_recipe recipe=speed_lines options={hit: 1.35}                                 -> focus lines, rush at the hit

- `fire_aura` = a fire strip (thin body, tall tongues), mirrored (seamless), flipped, squeezed square, wrapped with
  Polar Coordinates (Rect to Polar). Templates can now build on each other: a header `"uses": ["fire"]` inlines that
  template as `AEFX.T_fire(P)` with its defaults in `AEFX.D_fire`.
- `speed_lines` redraws every line on STEPPED keys (12 a second): hand-drawn focus lines flicker; tweened ones read as
  a tunnel.

Caveats to tell the client up front: a flipbook repeats exactly (each variant costs memory); a bolt has a fixed shape
(stretching changes its thickness); sequences follow bones but don't bend with a mesh; additive light vanishes on bright
or same-coloured backgrounds (use normal blend for flames there); budget ~10-15 MB of GPU memory per 2048 atlas page.

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
- Crossfading two noise fields (loopify) halves their contrast: anything nonlinear (threshold, levels) must come AFTER
  the crossfade. Alpha and colour want different curves: a hard alpha cut (thin gas vanishes) with a soft colour ramp;
  a soft alpha turns every mid-grey into a dim brown wash over the background.
- A Twirl on a layer whose MASK is inside the twirl drags the mask edge into curved black bands: mask after the twirl
  (a black overlay with an inverted feathered mask).
- A blurred copy of the bolt at 25% is a flash; at 100% (or a full-frame solid) it is a white blob / lit rectangle.
- `a or b and c` is `a or (b and c)`; don't write segment tests like that.
- Flare streaks wider than the view clip hard; keep them ~1.2x the subject, and give streaks real thickness
  (a 1-px hairline reads as a scratch).
- Whitespace stripping cropped mesh images inside their UVs: a 9-slice's soft corner then sampled the NEIGHBOUR on the
  atlas page (a dark speck in every dimmed reel). The packer now never crops inside what a mesh samples.
- A respawn key at exactly the wrap time can land in the OLD life through float error (floor(n - 1e-15)) and smear the
  particle across the screen while it fades in: put the respawn instant in the new life with an epsilon (`_life`).
- Bouncing / hopping motion sampled at a fixed rate cuts the corner at every landing (the grain never touches the ground):
  add a key at every landing time.
- GIF of many different scenes: per-frame 96-colour palettes band and recolour; quantise every frame to one global palette.
- Looping rain that respawns: put keys on EXACT times either side of the wrap. Rounding the wrap time to the key grid can
  land it just before the true wrap, and the piece then slides back up the screen, faintly, until the next key.
- A picture that touches its own edge shows a hard line once tinted and stretched: every glow (and every cut-out, by
  2 px of padding) must reach alpha 0 before the border. The kit is tested for it.
- Polar Coordinates: its interpolation is 0..1 (not percent), and it wraps in the LAYER's pixels using the short
  side as the radius: squeeze a wide strip into a square comp first or the ring comes out a thin oval.
- The fire template's hot body is a ramp sized to the comp WIDTH: on a wide strip leave `body` tiny (0.06) or the
  strip is one solid band of flame; `taper` sets how TALL the body reaches (2.9 for a long trail).
- A flame that "isn't there" in the preview: print the slot's draw bounds from runtime.run(geometry=True) before
  retuning. Twice it was there all along: additive orange on a red background, and a hot base parked on the subject.
- GIF previews of soft gradients dither to 10+ MB. Judge on the contact sheet; share a quantised/resized GIF.
- No book, lotus or vines here by design: they need art (layered PSD) and are rigged with `import_psd` + `rig_mesh` +
  `rig_strand`. Put these recipes `front_of=` / `behind=` those slots.
