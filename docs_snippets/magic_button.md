## Magic button (tap, spin, ready, disabled): `fx_magic_button` + AE `energy_burst`, `edge_aura`

Taken from a reference clip of a fantasy slot SPIN button: a round green disc in a bronze frame with four diagonal spikes, at 30 fps. The button is tapped twice, glows "ready" in between, and is disabled at the end. Every colour is a parameter. Scale 1 = a button about 420 units wide (the reference was 170 px, so its build used scale 0.405).

### AE templates (the noise)

| Template | What | Defaults |
|---|---|---|
| `energy_burst` | Energy-smoke burst shaped like the subject's silhouette, blown up (`spread` 140%, `wide` 165%). Churning Fractal Noise smoke goes through a torn silhouette matte, and inverted Turbulent Sharp veins are streaked outward with CC Radial Fast Blur. **Timing:** pops in 2 frames (opacity 0 / 35 / 100), holds about 0.2 s, falls to a haze (`plateau` 0.4) by 0.47 s and holds it to 0.77 s, gone by 1.2 s; the scale goes 90 → 100 at the pop and contracts to 91. **Output:** additive, one-shot, `hit_ae` = 2/fps. | 768 px, 1.4 s, 30 fps, color 00C8B4, light 50FFE6, art_scale 2, body 0.6, wide_body 0.4, smoke 1, veins 0.75, seed 21 |
| `edge_aura` | Lime energy hugging a silhouette: a hug (3 px blur) and a halo (11 px), with noise tongues streaked radially through a ragged band at `reach` 112%. It has thin electric veins and an exposure flicker on whole cycles. **Output:** an exact loop (rendered twice and crossfaded with `AEFX.loopify`), additive. | 640 px, 1.0 s, 30 fps, color 34F07C, light A8FFB4, art_scale 2, tongues 0.9, veins 0.6, seed 9 |

- **Silhouette input:** `art` is the subject's silhouette PNG: alpha = shape, centred, and each art px becomes `art_scale` comp px. Without it, both templates draw a generic spiked medallion as a shape layer (frame r 80, spikes to 116 art px).
- **Recolouring:** both renders are two-tone. Import them `tintable=True`; at the reference the tints were `10FFD0/00C870` (burst) and `30FF80/08D850` (aura), so a recolour needs no re-render.
- **Placement in Spine:** put both behind the subject.
  - **Burst:** played at alpha 0.68. Land comp frame 2 on the tap + 0.195 s; keep the hit a few ms early, because sampling exactly on a frame boundary can show the previous sprite.
  - **Aura:** starts at the tap + 0.13 s with alpha 0.7 and the `silhouette_halo` envelope.

### Spine recipes (the light)

| Recipe | What | Key options (defaults) |
|---|---|---|
| `magic_circle` | Faint magic circle: double ring with tick teeth, a band of 30 rune glyphs, an inner ring, 12 spokes, a hexagram and 6 glyph circles. It appears at `small` 0.62, snaps open in 0.04 s (sine out), opens to `open` 1.08 and turns `turn` 28°, fading by 1.19 s. `arcs` 2 bright swooshes travel `sweep` 160° clockwise on it. Additive, behind the subject. | radius 375 (152 ref px), glow 1 |
| `disc_flash` | The inner disc lit from inside, **normal blend**: the brighter centre (1.0) and darker rim (0.5) cover the disc art evenly, where additive would show its texture as blotches. `curve` press: 0.06 → 0.92 by 0.2 s, holds to 0.43 s, about 0.8 to 1.03 s, gone by 1.43 s. `curve` ready: 0.42 s ramp, then holds. | radius 156 (63 ref px), color 32FACD |
| `rim_pulse` | "Ready" pulse: light hugging the outline, peaking 4 ref px outside the edge (gaussian 5.5 plus an exp tail of 9), derived from `art={'silhouette': png}` (a medallion without it). It ramps over 0.42 s (5% at 0.05 s, 40% at 0.1, 65% at 0.15, 80% at 0.25) and **holds**; clear the track to cut it. `disc` adds the disc fill in `disc_color`. | size 949 (the silhouette picture's width), color 1E8C48, disc_color 36E08C |
| `silhouette_halo` | Wide soft glow round the silhouette (exp falloff of 18 ref px) with the aura's press envelope: in by 0.07 s, hold, out by 1.32 s. The soft light under `edge_aura`. | size 949, falloff 44, color 10500A |
| `icon_spin` | Icon turning at `speed` deg/s (> 0 = clockwise; the loop is one turn), with `smears` copies trailing at `trail`° steps (alpha 0.36 / 0.2) standing in for motion blur. `art={'icon': png}` (generic curved arrows without it). To stop, set the track's timeScale to 0 so it holds its angle. | speed 708, size 316, smears 2, trail 6.5 |
| `bar_flood` | A progress bar floods with violet plasma: in 0.075 s, scaleX 0.6 → 1 (sine out), fading by 0.24 s. Between 0.11 and 0.21 s it hands over to a gradient fill made from `stops`, with the bar's bevel rows (13 measured per-row multipliers); the fill holds. The fill is a coloured texture, so recolour it with `stops`; `color` sets the plasma. | width 692, height 32, color B040FF, stops magenta-orange-yellow-orange-magenta |
| `mote_loop` | Motes drifting up left and right of the subject with sway and twinkle. Each period divides the loop, so the 8 s loop is exact. | count 8, color 9CFF6A, color2 5CFFD2 |

### Measured facts

- **Press, in order:**
  - **Disc:** lights from the tap (+10 at 0.0 s, +161 by 0.2 s).
  - **Small circle:** appears at 0.167 s.
  - **Burst:** peaks at 0.2 s.
  - **Aura:** in by 0.2 s; it holds while the smoke contracts into a lime band hugging the frame (green +150 within 20 px), and is gone by about 1.43 s.
- **Colour of the burst:** the burst adds almost no red (+5), so a red component in any light colour turns the whole thing milky.
- **Spin:** the arrows turn clockwise at 708°/s; this is an absolute-angle fit, because per-frame deltas alias on a 2-fold icon.
- **Disable:** the bar flashes violet at +0.1 s and is settled by +0.3 s.

### Traps

- **Bone rotate keys are offsets from the setup angle.** Keying `base + 40` on a bone whose setup is `base` puts it at `2 * base + 40`: two arcs at 0° and 180° both land on 40°.
- **Additive glow over textured art** (a disc with cracks) shows the art's own texture and any repair blotches. Use normal blend for a fill light, additive only for light that spills past the art.
- **Silhouette-derived pictures** (rim, halo) are made from distances in units, so give the silhouette's real width as `size`.

### Composition (the reference's press)

- **Tap:** `disc_flash` at 0, `magic_circle` at 0.16, `energy_burst` with its frame 2 on 0.195, `edge_aura` loop from 0.13 to 1.45 with the halo envelope, and `silhouette_halo` at 0.13.
- **Spin:** `icon_spin` on its own track.
- **Ready:** `rim_pulse`.
- **Disabled:** `bar_flood`.
- **Throughout:** `mote_loop`.

CHANGELOG: magic button family from a fantasy slot SPIN button clip: Spine recipes magic_circle, disc_flash, rim_pulse, silhouette_halo, icon_spin, bar_flood, mote_loop (fx_magic_button.py, silhouette art= role derived into rim / halo) and AE templates energy_burst (silhouette-shaped energy smoke burst, pops in 2 frames) and edge_aura (lime energy hugging a silhouette, exact loop); tests/test_fx_magic_button.py.
SKILLROW: | Energy burst / edge aura round a button or symbol (tap burst, spinning-state aura hugging its silhouette) | `energy_burst` (one-shot, hit_ae 2/fps) and `edge_aura` (loop) with art = the subject's silhouette PNG, additive, import tintable; pair with fx_recipe `silhouette_halo`, `magic_circle`, `disc_flash`, `rim_pulse` |
