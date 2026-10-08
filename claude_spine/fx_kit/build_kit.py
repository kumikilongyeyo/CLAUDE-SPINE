"""Rebuild the bundled realistic kit (``claude_spine/fx_kit/*.png``) from the two Kenney CC0 packs.

Not needed at runtime: the processed pictures are committed next to this file. Run it only to change the kit:

    python -m claude_spine.fx_kit.build_kit "/path/to/textures_cc0"

where ``textures_cc0`` holds ``kenney_particle-pack/`` (Particle Pack 1.1) and ``kenney_smoke-particles/`` (Smoke
Particles), both CC0 1.0 from kenney.nl (see LICENSE-kenney.txt and CREDITS.md).

Processing (the same as the job that proved the look, coin-fx-test/prep_kit.py):

* Kenney particle PNGs are grey PALETTE images on transparency. They become WHITE + alpha, alpha = max(r, g, b) x a
  (x 1.15, clipped), so a slot colour tints them exactly like the procedural white textures.
* Every picture is trimmed to its visible pixels and downsized PREMULTIPLIED (soft edges keep their colour instead
  of fringing dark), longest side capped per picture (128-512 px).
* Painted smoke puffs (Smoke Particles) keep their colour.
* Tuned variants are baked once here. A photographic glow / ring is fuller than a drawn one, and when it is big it
  turns into a pink / white haze over the subject; retuning every effect for that does not scale, so the kit ships
  tighter pictures: glow_s = circle_05 with alpha^1.9 x 0.75, ring_s = light_02 x 0.5, ring_floor = light_03 x 0.8,
  flash_s = flash04 with alpha^1.3 x 0.8.
* Orientation variants: trace_01 turned horizontal (light_streak) and kept vertical (trace_01v); trace_05 is a comet
  with its head at the top (trail_up) and turned head-RIGHT (trail_r); the vertical real-lightning bolts spark_05 /
  spark_06 turned horizontal (bolt_h5, bolt_h6) so a bone aimed at a target stretches them along +x.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent

# name -> (particle-pack source, max side, rotation in degrees counter-clockwise)
WHITE: dict[str, tuple[str, int, int]] = {
    "flare_01": ("flare_01", 384, 0), "star_05": ("star_05", 128, 0), "star_06": ("star_06", 256, 0),
    "star_08": ("star_08", 384, 0), "star_09": ("star_09", 384, 0),
    "smoke_07": ("smoke_07", 384, 0), "smoke_08": ("smoke_08", 384, 0), "smoke_10": ("smoke_10", 384, 0),
    "spark_01": ("spark_01", 320, 0), "spark_02": ("spark_02", 320, 0), "spark_03": ("spark_03", 320, 0),
    "spark_04": ("spark_04", 320, 0), "spark_05": ("spark_05", 512, 0), "spark_07": ("spark_07", 512, 0),
    "bolt_h5": ("spark_05", 512, 90), "bolt_h6": ("spark_06", 512, 90),
    "twirl_01": ("twirl_01", 384, 0), "twirl_02": ("twirl_02", 384, 0), "twirl_03": ("twirl_03", 384, 0),
    "muzzle_02": ("muzzle_02", 256, 0), "muzzle_03": ("muzzle_03", 256, 0), "muzzle_04": ("muzzle_04", 256, 0),
    "muzzle_05": ("muzzle_05", 256, 0), "flame_05": ("flame_05", 256, 0),
    "trace_01": ("trace_01", 512, 90), "trace_01v": ("trace_01", 512, 0),
    "trail_up": ("trace_05", 512, 0), "trail_r": ("trace_05", 512, -90),
}
# tuned variants: name -> (source, white?, max side, alpha power, alpha gain)
TUNED: dict[str, tuple[str, bool, int, float, float]] = {
    "glow_s": ("circle_05", True, 256, 1.9, 0.75),
    "ring_s": ("light_02", True, 384, 1.0, 0.5),
    "ring_floor": ("light_03", True, 384, 1.0, 0.8),
    "flash_s": ("Flash/flash04", False, 384, 1.3, 0.8),
}


def fit(im: Image.Image, side: int) -> Image.Image:
    """Trim to the visible pixels, then downsize premultiplied so soft edges keep their colour."""
    bb = im.getchannel("A").point(lambda v: 255 if v > 3 else 0).getbbox()
    if bb:
        im = im.crop(bb)
    s = side / max(im.size)
    if s < 1:
        a = np.asarray(im, np.float32) / 255
        pm = np.dstack([a[..., :3] * a[..., 3:4], a[..., 3]])
        pm = np.asarray(Image.fromarray((pm * 255).astype(np.uint8)).resize(
            (max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS), np.float32) / 255
        al = pm[..., 3:4]
        rgb = np.where(al > 1e-4, pm[..., :3] / np.maximum(al, 1e-4), 0)
        im = Image.fromarray((np.dstack([np.clip(rgb, 0, 1), al]) * 255).astype(np.uint8), "RGBA")
    return im


def white(src: Path, side: int, rot: int = 0) -> Image.Image:
    """Grey palette particle -> white + alpha (alpha = brightness x alpha), turned, trimmed, downsized."""
    a = np.asarray(Image.open(src).convert("RGBA"), np.float32) / 255
    lum = a[..., :3].max(axis=2)
    alpha = np.clip(lum * a[..., 3] * 1.15, 0, 1)
    im = Image.fromarray((np.dstack([np.ones_like(lum)] * 3 + [alpha]) * 255).astype(np.uint8), "RGBA")
    if rot:
        im = im.rotate(rot, expand=True)
    im = fit(im, side)
    a = np.asarray(im).copy()
    a[..., :3] = 255                 # pure white again (resampling round-off darkens the faintest edge pixels)
    return Image.fromarray(a, "RGBA")


def build(textures: Path, out: Path = OUT) -> list[Path]:
    kp = textures / "kenney_particle-pack" / "PNG (Transparent)"
    ks = textures / "kenney_smoke-particles" / "PNG"
    for d in (kp, ks):
        if not d.is_dir():
            raise SystemExit(f"missing {d}")
    written = []
    for name, (src, side, rot) in WHITE.items():
        p = out / f"{name}.png"
        white(kp / f"{src}.png", side, rot).save(p, optimize=True)
        written.append(p)
    for name, (src, is_white, side, power, gain) in TUNED.items():
        im = white(kp / f"{src}.png", side) if is_white else fit(Image.open(ks / f"{src}.png").convert("RGBA"), side)
        a = np.asarray(im, np.float32) / 255
        a[..., 3] = np.clip(a[..., 3] ** power * gain, 0, 1)
        p = out / f"{name}.png"
        Image.fromarray((a * 255).astype(np.uint8), "RGBA").save(p, optimize=True)
        written.append(p)
    return written


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        raise SystemExit(__doc__)
    files = build(Path(argv[0]).expanduser())
    total = sum(f.stat().st_size for f in files)
    print(f"{len(files)} kit pictures, {total / 1e6:.2f} MB in {OUT}")


if __name__ == "__main__":
    main()
