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

Render the comp or representative frames. Inspect at least:
- end of anticipation
- impact peak
- mid decay
- final residual

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

Do not bake cheap things into AE just because AE can do them. Keep simple glow pulses, rings, shakes, repeated sparks and similar moving-light effects native Spine when possible.

## 7. Spine cleanup after import

After the effect is imported:

1. run structural validation
2. run qa_budget for the target
3. run qa_fx_premium when subject slots exist
4. preview the actual game animation
5. run optimize_animation on dense Spine timelines only after the full clip is assembled

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
