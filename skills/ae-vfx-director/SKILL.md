---
name: ae-vfx-director
description: Direct After Effects VFX like a senior game-VFX artist, then hand the result to Spine with mobile-safe frame and texture budgets. Use for realistic, premium slot, stylized or anime VFX when the user wants impact, immersion, clean AE comps, strong timing, self-review, and optimized AE-to-Spine delivery.
---

# AE VFX Director

Use this skill when the task is not merely "make an AE comp", but "make the effect feel premium / realistic / immersive and still ship cleanly to Spine".

The rule is simple:

**plan -> build -> render -> judge -> subtract/fix -> import -> validate**

Never skip the judge pass for hero effects.

## 1. Plan before touching After Effects

Call ae_vfx_plan with the creative brief.

Pick:
- event: impact, fire_hit, electric_hit, magic_reveal, win_burst, or ambient
- style: stylized, premium, realistic, or anime
- target: normally mobile_symbol, mobile_feature, or mobile_hero

Treat the returned comp_structure, layers, beats, look_rules, and handoff as production constraints.

Do not improvise a giant stack of effects first and optimize later.

## 2. Build the AE comp like a VFX shot, not a preset dump

Use the After Effects MCP to create or modify the comp.

Keep this hierarchy:

- 00_CONTROLS
- 01_SOURCE
- 02_CORE
- 03_SECONDARY
- 04_DISTORTION
- 05_LIGHTING
- 06_ATMOSPHERE
- 07_FINISH

Prefer one controller/null per effect family. Keep layer names semantic and deterministic. Precompose only when it reduces noise or creates a reusable unit.

### Physical layering

A strong impact usually reads in this order:

1. anticipation / energy gather
2. core event
3. secondary sparks/debris
4. distortion or shock
5. subject/environment light response
6. atmosphere / smoke / residual
7. subtle finish

The effect should appear to exist **in the scene**. If a fireball or lightning strike is bright, nearby art needs a brief light response. Do not compensate for missing integration with more glow.

## 3. Timing

Do not evenly space keys.

For one-shots:
- anticipation gets room to read
- impact change is compressed into a few frames
- peak is short
- first decay is fast
- residual smoke/embers/light decay more slowly

Use Graph Editor easing that is easy to edit later. Prefer a small number of meaningful keys over sampled noise on every property.

If procedural motion is needed, put noise/expression controls behind named controller properties and keep the animation envelope keyed cleanly.

## 4. Style modes

### realistic

- restrained bloom
- high material breakup inside the effect body
- physically motivated colour/lighting
- softer volumetric edges
- heat/refraction where appropriate
- fewer decorative particles
- longer residual decay
- no giant white additive soup

### premium

- strong slot readability
- controlled saturation
- layered but clean
- polished light response
- enough texture to feel expensive without obscuring the symbol
- mobile readability wins over tiny detail

### stylized

- larger graphic shapes
- faster timing
- fewer, chunkier particles
- stronger silhouette
- exaggerated squash/overshoot
- simpler texture

### anime

- directional energy
- sharp impact frames
- smears/speed accents
- stronger contrast grouping
- aggressive anticipation -> impact change
- keep the main attack direction obvious

## 5. Render and self-review

Call ae_quick_look on the saved comp (or rendered frames) with art= the thing the effect sits on and, when you have
it, background= the game screen. It writes ONE contact sheet: the four judge frames on dark grey and in the scene,
plus the energy curve. Read that image. It picks the frames itself:
- a hit: end of anticipation, impact (the flash), mid decay, final residual
- a build (frost creeping, charge-up): start, half built, fully built, end
- a loop: four evenly spaced frames

Use its hit_ae as the import's hit_ae. A render costs mostly AE opening the project (18-22 s for a 300-comp .aep, 5-8 s
for a small one), so tune the effect in a small .aep and re-run quick look after every change; import only once it
passes review.

Score 0-10:
- readability
- impact
- depth
- lighting_integration
- motion_flow
- texture_quality
- timing
- clarity

Call ae_vfx_review.

If clarity is poor, **remove particles / lens layers first**. Do not solve a muddy effect by adding another effect family.

A hero pass should normally reach 8+ overall with readability, impact, timing and clarity at 8+ before import.

## 6. AE -> Spine handoff

Use ae_vfx_to_spine for production imports.

It wraps the raw ae_fx_to_spine bridge and automatically:
- trims empty lead/trail frames
- caps texture resolution by target
- caps sequence frame count
- preserves playback speed when frames are subsampled
- feathers comp borders by default
- keeps the displayed Spine world size even when source textures are reduced
- exposes the policy in the returned director metadata

Repeated effects should use copies= so all instances share one sequence image set.

Colour variants of a two-tone effect (electricity, lightning, frost, ice, smoke): import once with
tintable=True and give each copy its own tint ({"x": .., "y": .., "tint": "FF3030"}); one grey frame set then plays
red, green and purple. Check the result's tint.grade: "poor" (fire, gold glows, anything white -> yellow -> orange ->
red) means two colours cannot hold it, so render those variants in AE and import without tintable.

For magic effects start from the templates made for this: magic_glow, magic_smoke (luminous by default) and
prism_glow. They are built in grey and coloured once, so they grade good and recolour cleanly. A rainbow / spectrum
light is not a colour to tint: render the light WHITE (prism_glow) and import with spectrum=0.05 spectrum_bands=6
spectrum_turn=2, which redraws the one frame set as rainbow bands that add up to white.

Smoke that must move like smoke (a puff bursting out, swirling, dissolving) is simulated, not keyed: magic_puff_ae runs
a real 2D smoke simulation for a wide banner and writes the AE look script; magic_puff_to_spine lands the render as one
full-width sequence with the light done natively in Spine (lines, flares, rays, pop, glitter on the simulated flow).
Tune the motion on its no-AE preview first: the simulation takes ~2 minutes at res 0.5. Animating a still image of
smoke is not the same thing; artists notice.

Do not bake cheap things into AE just because AE can do them. Keep simple glow pulses, rings, shakes, repeated sparks and similar moving-light effects native Spine when possible.

## 7. Spine cleanup after import

After the effect is imported:

0. light the subject with relight_from_fx (sources = the FX slots, globs allowed; subjects = the art it sits on).
   Never hand-key a face glow: the measured light follows every flare, pulse and frame. Carry `norm` from the idle
   into the one-shots so the aura lights the subject equally in both.
1. run structural validation
2. run qa_budget for the target
3. run qa_fx_premium when subject slots exist
4. preview the actual game animation
5. run optimize_animation on dense Spine timelines only after the full clip is assembled
6. run optimize_draw_order last, and export with the pack_atlas group_sequences value it names. It never changes a
   pixel; trust its runtime call count over qa_budget's static one.

For an effect that should wrap round the subject (orbiting energy, rings), use orbit_ribbons: import `<comp>_back`
behind the subject and `<comp>_front` in front of it.

AE sequences are frame animation; optimize_animation is for Spine animation keys, not for throwing away AE sprite frames. Use the director handoff budget for the sequence itself.

## 8. Production priorities

When performance is too high, optimize in this order:

1. remove empty frames
2. reduce texture dimensions
3. share one sequence across repeated instances
4. remove nonessential decorative layers
5. reduce frame count while preserving impact timing
6. only then simplify the core effect

Never destroy the main impact silhouette just to save a few frames.

## 9. Lessons from real passes (skull-coin job: sparks, frost, fire aura)

Judge every pass against the thing it sits on, not on black: frost composited over the actual coin face, sparks
added (premultiplied) onto the game background. Six rounds were needed for sparks and frost; each failure below was
only visible that way.

- **"Realistic" means real material, not more glow.** Drawn starbursts, cartoon puff lobes, zig-zag line electricity,
  blob fireballs and square blocks read as placeholders. Replace them with photographic / volumetric pictures
  (fx_recipe `kit="realistic"`) or a rendered AE pass; keep the recipe's motion.
- **Sparks:** CC Particle World Line particles + **Echo** (operator Maximum, -1/240 s, ~14 echoes) make long
  gravity-curved streaks at full brightness. A long shutter (CC Force Motion Blur) averages thin sparks to nothing.
  Birth rate is per frame and huge: ~0.7 for a burst; 30 renders a solid white ball. Template: `metal_sparks`.
- **Frost / anything that must sit ON art:** build a greyscale DENSITY, then Shift Channels (alpha from luminance) +
  Fill, so thin frost is see-through; an opaque frost plate hides the art. Any helper layer (Find Edges glints) must
  get its alpha the same way or it exports an opaque black plate. Template: `frost_creep`; in Spine parent it to the
  face bone (it narrows with the spin), clip it to the face disc, add a mirrored twin on the back face.
- **Auras round an object:** the `fire_aura` template's flame band starts at r = 120 px of a 768 comp; scale it so
  the band starts just inside the object's edge and draw it BEHIND the object (only the tongues show), plus a faint
  additive copy in front. Its base band is dark: fade it out before the object it hides behind disappears.
- **Hold loops at a playable rate.** Never subsample a looping flipbook below ~12 fps to meet a frame budget;
  shrink the texture first (import_optimized min_fps).
- **AE scripting:** CC Particle World properties are flat (set by matchName `CC Particle World-00NN`; 0050/0062 are
  groups); Gradient Wipe completion/softness are 0..1; Cell Pattern's contrast is "Contextual Slider"; scripts run
  through the MCP must `return` a string; AE caches renders by comp NAME (new name per attempt); the first
  saveFrameToPng after switching comps can be stale (throw one away).
- **Two optimisations that do NOT work on realistic renders** (measured on 6 fx1008 glows): splitting a sharp core
  from a low-res soft glow saved -19% to +15% of atlas area; shrinking "soft" glows to half size changes 1% of pixels
  by 12-16/255. Realistic glows carry real texture; budget by frame count and copies, not by blur.
- **Repeated hits:** one rendered sequence, played as copies with their own scale / rotation (copies=[[x, y, start,
  scale, rotation], ...]) escalates three impacts without three frame sets.
