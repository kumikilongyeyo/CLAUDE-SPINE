# fx_kit credits

Every picture in this folder is processed from two packs by Kenney (kenney.nl), released under
**Creative Commons Zero (CC0 1.0)**: free for personal and commercial use, no attribution required. Credit is given
here because it is nice to. The licence texts are in `LICENSE-kenney.txt`.

- **Particle Pack 1.1** by Kenney Vleugels (filter templates: Indigo Ray, Craig Nisbet, Zoltan Erdokovy, Heliagon,
  ThreeDee, Killst4r, Tim2501). https://kenney.nl/assets/particle-pack
- **Smoke Particles** by Kenney Vleugels. https://kenney.nl/assets/smoke-particles

Nothing else is bundled: no library, After Effects or photo pictures.

| kit picture | source | processing |
|---|---|---|
| glow_s | Particle Pack circle_05 | white + alpha, alpha^1.9 x 0.75 (tight glow, no haze) |
| ring_s | Particle Pack light_02 | white + alpha, x 0.5 |
| ring_floor | Particle Pack light_03 | white + alpha, x 0.8 |
| flash_s | Smoke Particles Flash/flash04 | kept in colour, alpha^1.3 x 0.8 |
| flare_01, star_05, star_06, star_08, star_09 | Particle Pack, same names | white + alpha |
| smoke_07, smoke_08, smoke_10 | Particle Pack, same names | white + alpha |
| spark_01 .. spark_05, spark_07 | Particle Pack, same names (real lightning) | white + alpha |
| bolt_h5, bolt_h6 | Particle Pack spark_05, spark_06 | white + alpha, turned horizontal |
| trace_01, trace_01v | Particle Pack trace_01 | white + alpha, horizontal / vertical |
| trail_up, trail_r | Particle Pack trace_05 | white + alpha, head up / head right |
| twirl_01 .. twirl_03 | Particle Pack, same names | white + alpha |
| muzzle_02 .. muzzle_05, flame_05 | Particle Pack, same names | white + alpha |

"white + alpha": the pack's grey palette pixels become white with alpha = brightness x alpha, so the Spine slot
colour tints them; every picture is trimmed and downsized premultiplied. `build_kit.py` rebuilds the folder.
