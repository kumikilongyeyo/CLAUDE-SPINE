## Round spin-button light (fx_button_glow): hover_pulse, press_flash, bloom_collar, anamorphic_streak, rainbow_halo, glitter_halo, spin_button_glow

Measured frame by frame (30 fps) on a hot-air-balloon slot's round SPIN button (radius 88 px): it glows while the
cursor hovers, is pressed (dark frame, squash, white-hot rim flash), then shows a gold "spinning" light until the reels
stop. All native Spine, procedural pictures, one colour per part (a recolour is one argument). Sizes follow
`radius` (88 = the reference) x `scale`; x, y = the button centre.

**Timing model** (all but hover_pulse): `start` = the flash frame (press_flash: the pressed frame; its flash comes
`dark` s later), `duration` = how long the light HOLDS (flash -> reels stop; 35 frames = 1.167 s on the reference),
then `stop`: `fade` (normal stop, gone in 0.47-0.63 s), `quick` (turbo stop: 5-frame drop, then an after-glow, the
long line and the spectrum linger ~1.25 s) or `hold` (no stop keys).

| recipe | what | defaults | options |
|---|---|---|---|
| `hover_pulse` (loop) | face glow (cyan), thin lilac edge line, violet halo hugging the rim (breathing), a pink-white ring leaving the rim every period, 84 -> 114 px (~1 px/frame), fading | color FFB8D8, 1.0 s | radius, period, rings, halo_color 7C8CFF, rim_color D4CCFF, face_color 6CE0FF |
| `press_flash` | pressed frame(s), squash .955 .922 .903 .906 .94 .985 -> 1 by f+8, white-hot ring ON THE RIM (not squashed), pink-white flash halo (peak f+1, gone f+12), face glow; the rim decays while it holds | color C8EEFF, dark 2 frames | radius, stop, dark, depth .097, button (your bone, squashed through a carrier), halo_color FFB8D8, rim_color D4CCFF, face_color 6CE0FF; art role `disc` = your button picture on the squash bone. Event fx_press_flash |
| `bloom_collar` | normal-blend gold WASH (r 89-212) + additive bloom + a fiery collar broken into rays (r 92-127) + three thin ripple rings creeping out (95->117, 106->114, 128->136); snaps in f+1..f+5, grows 12 % while it holds; `quick` adds an after-glow | color FFA81C | radius, stop, wash, light_color FFC428, afterglow_color FFE45A |
| `anamorphic_streak` | normal-blend wash + bright flat band (+-10 px, 540 wide) + yellow hairline beside the button + a long pale line across the screen (640) and a fainter one 21 below; grows out from 35 % width in 5 frames | color FFE45A | radius, stop, wash, wash_color FFA81C, line_color 88E4FF, length, second_line |
| `rainbow_halo` | spectrum ring (violet in -> cyan -> green -> yellow -> orange/red out), brightest left/right; r 110 -> 122 (f+1) -> 150 -> 168 -> 183 (f+5, ease out), creeps to 196 while it holds | color FFFFFF (a tint: the spectrum is the picture) | radius, stop |
| `glitter_halo` | 64 gold dots pop, twinkle twice while drifting out/up, vanish, respawn (r 94-200, 45 % near the sides) | color FFB848, duration hold + 0.35 | radius, band, sides |
| `spin_button_glow` (bundle) | the whole press -> spin -> stop: bloom_collar, anamorphic_streak, rainbow_halo, glitter_halo (behind) + press_flash (front), timed like the reference | start = pressed frame | radius, hold, stop, dark, button, wash, skip, steps {recipe: {color, count, intensity, options}}; art={'press_flash': {'disc': ...}} |

Measured facts:
- **The gold is not additive**: where it passes, the background's blue channel drops 50-100 levels. So bloom_collar
  and anamorphic_streak lay a normal-blend wash under the additive light. `wash=False` = additive only (over dark
  backgrounds a wash only darkens).
- The flash ring stays at the rim radius while the button squashes to 90 %; only the face glow and the edge line
  squash with it.
- Normal stop: gold fades over 17 frames, rim 14, spectrum 19. Quick (turbo) stop: washes gone in 5 frames, an
  additive after-glow, the long line and the spectrum (~50 %) linger ~0.5 s, ~45 % left at 0.9 s, gone at 1.25 s.
- Draw this light UNDER a semi-transparent UI bar if the game has one (the reference does, at 0.53 opacity).

Traps:
- Put hover_pulse and press_flash IN FRONT of the button art (face glow / rim are additive on it), bloom_collar,
  anamorphic_streak, rainbow_halo and glitter_halo BEHIND it (the bloom is hollow behind the button; the bundle
  orders them for you).
- A disabled / grey-arrow state during the spin (the reference dims its rim then) is the game's own art state, not
  part of these recipes: key the face glow / rim slots down yourself if you need it.
- rainbow_halo's colour is a tint: red / blue tints still read as a spectrum, darker.

CHANGELOG: New fx_button_glow family (round spin-button light, measured on a slot spin button): hover_pulse, press_flash (squash through a carrier or your disc art=, white-hot rim flash), bloom_collar and anamorphic_streak (normal-blend wash + additive light, wash= option), rainbow_halo (spectrum ring), glitter_halo, and the spin_button_glow bundle; stop = fade | quick | hold.
