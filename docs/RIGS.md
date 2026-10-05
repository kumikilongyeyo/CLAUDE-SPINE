# Rig recipes: faces, bodies, animals, creatures

Every rig recipe takes a project from `import_psd` (or its procedural sample) and RECOGNISES PARTS BY LAYER NAME, so
swapping the theme means swapping the PSD. Each one documents its naming convention as a constant (`FACE_LAYERS`,
`BIPED_LAYERS`, `QUADRUPED_LAYERS`, `SERPENT_LAYERS`, `FLIER_LAYERS`, `ADDON_LAYERS`, ...), lists what is missing, and
skips optional parts. Each ships a procedural sample (`make_*_sample`) so it is tested without your art.

The clip contract is the same everywhere: loops are identical at both ends, one-shots end exactly on the setup pose,
the artist's setup never moves, footfalls fire `sfx_step` (the foot in the string field), other moments `sfx_<clip>`,
and every clip validates and plays in spine-core with physics stepping. Motion is exaggerated real physics: exact
springs (damping solved from the overshoot you ask for), volume-preserving squash, lags by level, planted feet. Anything
that moves a bone you own goes through an inserted carrier bone.

| tool | what | kind |
|---|---|---|
| rig_face | whole-face rig from layer names: turn, clamped eyes, blinking lids, 3-bone brows, viseme mouth + jaw squash, cheeks, hair physics, plus idle / happy / sad / angry / surprised / talk | rig |
| face_clip | rebuild one face clip (intensity, seed, text) | motion |
| look_at | lagged eyes -> head -> spine look chain, works for bodies too | motion |
| lipsync | text/phonemes -> stepped visemes + eased jaw + word events | motion |
| rig_biped | biped skeleton, IK, floor-pinned feet, joint meshes, breathing, look-at, secondary from named PSD layers | rig |
| clip_set | character contract: idle, idle_fidget, walk, run, jump, land, hit, attack, win, lose, talk | motion |
| secondary | physics on every strand-like layer (hair, cloth, silk, leather, chain, feather, tail, ear, pouch) | rig |
| squash_stretch | volume-preserving exact-spring squash on any bone chain | motion |
| qa_character | joint cracks, foot slide, per-rig-type mobile bone budget | QA |
| make_biped_sample | procedural PSD-named adventurer | setup |
| rig_serpent | fish / eel / snake / dragon / tentacle chain: travelling wave, swim, idle_float, turn, reach | rig |
| rig_flier | bird: 3-bone wings + feather fan, flap / glide / perch / takeoff / land, stabilised head | rig |
| attach_rig | ears, tail, wings, horns, digitigrade, mermaid, snake_hair, fur, glow on any rig; clips merge by name | rig add-on |
| gait | footfall tables -> planted-foot IK paths, Froude-scaled stride and cadence, bob and pitch from the ground forces, sfx_step per footfall | motion |
| rig_quadruped | one-call four-legged rig (plantigrade / digitigrade / unguligrade) + idle, alert, walk, trot, gallop, bound, pounce, sleep, shake | rig |
| rig_creature | slime, golem, ghost, tentacle beast, dragon, insect, plant monster or mimic from its layers, with idle + signature clips | rig |
| make_creature_sample | procedural sample for any creature kind, named by its layer convention | setup |

## Face

`rig_face` rigs a whole face in one call and recognises the parts BY LAYER NAME (case-insensitive, any group prefix,
sides `_L`, `_left`, `left_`, `eyeL`). Only the head is required: `face/head` (or `face`, `skin`, `base`). Optional, skipped
and reported when missing: `face/eye_L/{white, iris, pupil, highlight, lid_upper, lid_lower}`, `face/brow_L`, `face/nose`,
`face/jaw` (chin art), `face/cheek_L`, `face/ear_L`, `face/mouth/{A,E,I,O,U,M,F,L}` (+ `rest`, `smile`, `frown`, or one
plain `mouth` layer), `hair/back`, `hair/bangs` (or `fringe`), `hair/strand_*` / `lock_*`. The mouth layers become ONE
`mouth` slot with one attachment per shape. `samples.make_character` rigs too: `rig_face parent=head`.

    make_face_sample out_dir=./face
    rig_face project=face/face.json talk_text="big win tonight"   -> idle happy sad angry surprised talk
    lipsync project=face/face.json animation=line1 text="spin again"
    look_at project=face/face.json animation=look gaze=[[0, 0, 0], [0.4, 0.6, -0.2], [1.2, -0.7, 0]]   (t, gaze x, gaze y in -1..1)

- Turn: `rig_turn` is the base layer; everything hangs under one `face_rig` bone at the chin.
- Eyes: `face_look` is the look target. The socket clamp is a ONE-BONE IK with `compress` and no `stretch` in a parent
  scaled (1, ry/rx): the tip never leaves the socket ELLIPSE however far the game drives the target. The eyeball copies
  the tip's world position (never squashed); the highlight moves 55% of that.
- Lids: per-column weighted meshes; the lash travels exactly to the white's meeting line (upper 70%, lower 30%), the
  corners stay put. Blink = 80 ms down (accelerating), 160 ms up (decelerating).
- Brows: three bones per brow (inner, mid, outer) with hat weights, so a big inner raise bends without a crease.
- Jaw: opens by SCALE, stretching the lower face from the lip line with scaleX = scaleY^-1/2 (volume kept); the mouth
  rides the jaw. Cheeks sit in the face mesh: the jaw stretches them and `face_smile` lifts them into the lower lids, so
  a smile squints.
- Clips: idle (loop: breath, micro-saccades and blinks on a seeded Poisson timer; saccades instant, the head follows
  after 100 ms on a damped spring, the eyes counter-roll as it arrives; the loop is solved periodically so it closes
  exactly), happy / sad / angry / surprised (exact spring steps with a smootherstep release onto setup; brows lead by a
  frame; sad's inner-brow raise is exaggerated; surprised squashes 2 frames then overshoots; angry adds a damped 7 Hz
  shake), talk (stepped visemes one frame ahead of the sound, eased jaw, brows and nods on stressed words).
- `look_at` works on ANY bones: each level has a weight, a dead-time lag, a spring and a limit; the spine twists two
  frames after the head through a carrier bone, so the artist's keys still play.
- `lipsync`: plain text (a small grapheme table timed by wpm, punctuation pauses) or ARPAbet / viseme phonemes; a missing
  viseme falls back to the nearest shape. Events `sfx_talk`, `talk_word` (string = the word), `talk_end`.
- Limits: lids must be skin-coloured layers that overlap the white, lash on the lid's lower edge. Key times are float32:
  a stepped key sampled exactly on its own time can land one frame late.

## Body

`rig_biped` turns a character PSD into a game rig in one call; `clip_set` gives it the character contract; `qa_character`
proves it. Layer names follow `BIPED_LAYERS` (case-insensitive, sides `_l/_r`, `Arm L`, `arm.l`, `left_arm`): torso, head,
arm_l/r (or upper_arm + lower_arm), leg_l/r (or thigh + shin), optional pelvis, neck, hand_l/r, foot_l/r. Import with
origin=bottom.

    import_psd psd=hero.psd out_dir=./hero origin=bottom
    rig_biped project=hero/hero.json            -> skeleton, IK, floor-pinned feet, joint meshes, breathe, look_target, secondary
    clip_set project=hero/hero.json             -> idle idle_fidget walk run jump land hit attack win lose talk
    qa_character project=hero/hero.json         -> cracks, foot slide, bone budget, what to fix

- Skeleton root -> ground -> hips -> spine1-3 -> chest -> neck -> head, shoulders, arms, hands, thighs, shins, feet, placed
  from each layer's own centre line. Two-bone IK on arms and legs with the bend taken from the art; the foot targets sit
  under `ground`, so the body bobs and squashes without the feet moving. One weighted mesh across each shoulder, hip,
  elbow and knee.
- Same clip names for every character, so game code never changes. Loops close, one-shots end on the setup pose.
  Walk is an inverted pendulum, run a spring-mass with a gravity-parabola flight; land squashes to exactly 0.85 and
  overshoots to exactly 1.05 (volume kept); hit anticipates against the blow, then recoils up the chain; hair and cloth
  feel a headwind ~ v^2 while moving.
- walk/run are in place: move the character at the `float` of `sfx_step` (px/s) and the planted feet stay put.
- Other rigs: `clip_set bone_map={hips: hip, ik_hand_r: arm_r2_ik}`. Missing bones skip a clip and say which.
- Look-at: move `look_target` (under `look_base`). Eyes first, head 2 frames later, spine 20%. (`look_at` from the face
  rig does the same for any chain of bones.)
- `secondary` presets: hair, cloth, silk, leather, chain, feather, tail, ear, pouch, found by name and by elongated shape.
  Cloth damping < hair (Spine's damping is velocity KEPT, so cloth settles faster).
- `squash_stretch chain=[...] clip=... squash=0.85 overshoot=1.05`: exact extremes, volume kept, on a carrier bone.
- `qa_character` plays every clip in spine-core: joint cracks (the outer half of each joint checked against the posed
  art), folded triangles, planted-foot drift against the declared ground speed, and the per-rig-type bone budgets
  (biped, quadruped, flier, serpent, face) plus mobile_character.
- Traps: a deep bend past ~110 degrees folds a single mesh (QA reports folds). Physics starts from rest at frame 0 of a
  clip, so judge looping secondary motion on its second pass.

## Chain rigs and add-ons

Two creature rigs and nine snap-on parts, all found BY LAYER NAME, all with real physics exaggerated.
`rig_serpent` swims a travelling wave down one chain (y = A(s) sin 2pi(s/lambda - f t), A growing to the tail); speed
sets the beat the way fish do it (f = U / (0.7 lambda)) and the tail amplitude follows Strouhal 0.3. `turn` is a fish
C-start (a swerve that ends on setup; a lasting heading change is the game's); `mode=tentacle` adds tip IK and a
spring-loaded `reach`. `rig_flier` flaps with a 58% downstroke and a lead -> lag phase down the wing; the body bobs on
every downstroke while the head holds still (a transform constraint to an anchor that does not bob: bird head
stabilisation). `land` hands over to `perch` on its exact first frame (the one one-shot that does not end on setup).

`attach_rig kind=... bone=...` plugs a sub-rig into any rig with that bone and MERGES its clips by name: a host clip
keeps its length, loops refit a whole number of cycles into it, loop content in a host one-shot is faded so the
one-shot still ends on setup. Kinds: ears (perk = exact spring overshoot, swivel toward a sound, the far ear lags),
tail (happy / alert / angry), wings (feathered / bat / insect: breathing fold, flutter), horns (shear-only physics: a
tiny lag), digitigrade legs (reversed hock, planted IK feet, sfx_step l/r), mermaid tail (a serpent chain; legs
hidden), snake hair (8-12 serpents, random exact-loop idles, shared look), fur (outline bones + a wind gust), glow
(the FX shine / electric_frame tiled into the host clips, one fx_* event per pulse).

Traps: rig parts BEFORE meshing them (chains start from region layers). Physics bones are never keyed: keys go on a
control bone above the chain. Glow on surface marks (runes) draws right above its part (two extra batches) so whatever
covers the part also covers the glow; eyes go on top (one batch). digitigrade removes the host's own sfx_step events in
the clips it drives (the new legs own the footfalls); mermaid clears the leg layers' setup attachments.

## Gait

Locomotion is a footfall table plus physics. `gait` keys any rig that has foot IK targets and one body bone;
`rig_quadruped` builds a whole animal from layers and uses it.

- The table: each leg's phase (when it touches down, 0..1) and the duty factor (fraction of the cycle on the ground):
  walk 0.65 (LH LF RH RF), trot 0.42 (diagonals), pace, canter, gallop 0.28 (rotary LH RH RF LF, two flights), bound;
  tripod (L1 R2 L3 / R1 L2 R3) and wave for six legs; biped walk / run.
- Speed sets stride and cadence together (Froude): f = c sqrt(v / L), with L the hip height; stride = v / f. Double the
  speed and both grow by sqrt 2. The period is rounded to 1 ms, so loops are exact.
- Planted means planted. Cycles are IN PLACE (the game scrolls the world at the `speed` in the result). A stance foot
  moves back at exactly `speed` in ONE linear key-to-key segment, so the runtime's interpolation is exact (measured in
  spine-core: worst slip 0.021 px over a stance). The swing covers the stride on a minimum-jerk curve, lifted on a
  clearance arc, with a toe roll.
- The body rides the ground forces: a half-sine load per planted leg. Walks vault (highest at mid-stance), trots and
  gallops bounce (lowest under the load). Pitch comes from hind load minus fore load.
- Reach is checked: if a stride would over-stretch a leg, plant nearer under the hip, carry the hips up to 6% lower,
  then take shorter, quicker steps. Each fix is reported.
- Quadruped: layers `body`, `head`, `{front|hind}_{upper|lower|foot}_{L|R}` (+ optional `_mid`, neck, tail, ears, eyes,
  mane*, tuft*, wattle*); _R is the near side. `leg_type` plantigrade (2-bone IK, flat foot), digitigrade (hock target +
  metapodial IK; without a metapodial layer the lower leg is split into a two-bone mesh) or unguligrade (+ pastern
  carrying the hoof). Foot targets live under root; each foot bone copies its target's rotation, so a planted paw never
  turns. The tail is the emotional readout: loose physics plus keyed swing in every clip. The neck counter-rotates the
  pitch with a lag and nods on each fore footfall. Shake is a damped 4.5 Hz sine travelling head to tail.
- No root motion and no gait-to-gait transitions (Spine's mixing does those). Pounce strikes forward and steps back so it
  ends on setup.

## Creatures

`rig_creature(project, kind=...)` rigs a non-humanoid from its layers and gives it a full clip set by COMPOSING the rigs
above: gait and rig_quadruped for legs, rig_serpent chains for tails, necks and tentacles, rig_flier's stroke for wings,
merge_clips (clips merge by name), juice for the symbol contract and fx_recipes for light. `kind=""` lists the kinds,
each with its layer convention (`CREATURE_LAYERS`), clips and options; `make_creature_sample` draws a sample that
follows it. Every sample fits `mobile_character`.

- slime: one mesh on a core + 6-8 outline bones with jiggle physics. Squash keeps the VOLUME (scaleX = scaleY^-1/2, so
  0.7 -> 1.195; `law="area"` for 1/scaleY). The hop is a ballistic parabola whose stretch follows the speed, the splat
  recovers on an exact spring, and the outline rings in Rayleigh's drop modes (mode 3 at 1.936 x mode 2).
- golem: rigid parts with gaps lag their parent through a critically damped filter (zeta >= 1: heavy things never
  overshoot), one level deeper per joint. Seams glow additively and flash on impact with a 1/t decay; `stomp` fires
  `screen_shake` (float = px, int = ms).
- ghost: a strand-chain body with cloth physics; bob and sway at two incommensurate periods (1.7 s, 2.9 s) closed
  exactly over the loop (`close_periods`); alpha breathes; `fade_out` ends invisible and `fade_in` starts there.
- tentacle: `tentacle<N>` serpent chains with their own phases and reach IK on the tips; suckers swap to stretched art
  while a tentacle stretches; the slam whips from base to tip.
- dragon: rig_quadruped body and gait + serpent neck and tail + bat wings on rig_flier's flap. The breath is a generated,
  exactly looping fire flipbook: a starting turbulent jet (front ~ sqrt(t)) spreading at a constant angle and curling up
  on buoyancy; its `ae_hint` hands it to the AE `fire` template on a bone rotated along the jet.
- insect: 12 leg layers on 2-bone IK walking the tripod (or wave), antenna strands, a 6-frame wing-blur flipbook for fly.
- plant: wind-loaded cantilever sway; `grow` is diffusion-limited like frost (s = sqrt(2 k t): tips race, then slow);
  roots are planted IK feet and leaves are physics fans.
- mimic: a spring hinge (exact overshoot), a lid that falls shut and bounces with restitution, a tongue strand, teeth;
  `open` fires a `shine`; `land` and `win` follow the juice_apply contract.
- Contract exceptions: `fade_out` ends invisible (bones on setup) and `grow` starts tiny (ends on setup). Golem and
  tentacle motion is keyed from exact filters and waves (no Spine physics), so "never overshoots" is guaranteed.
