"""Recolour one After Effects render in Spine: grey frames + the slot's light and dark colours.

Spine's two-colour tint ("tint black") draws a texture as ``out = g * light + (1 - g) * dark`` per pixel, where g is
the texture's grey level (straight colour; the runtime does it premultiplied). So a render whose colours lie on ONE
line in RGB space (white-hot core -> blue edge, white frost -> grey-blue, bright smoke -> dark smoke) can be stored
as grey and recoloured per slot: one frame set in the atlas plays red, green and purple electricity.

The fit is measured, not assumed. On the fx1008 / skull-coin renders (mean premultiplied error, 0..255):
frost 4, lightning 4, smoke 6, electric ring / sphere 7, electric star 9, ice shatter 10 (good); cooling sparks
10.3 and energy orb 13 (fair: the sparks recolour pale, the orb loses its cyan rim); gold win glow 18, fire 19-23 (poor: white -> yellow -> orange -> red is a
curve, two colours turn it pink). Fire and gold keep their colours only when rendered in colour; make colour
variants of those in AE.
"""
from __future__ import annotations

import colorsys
import re

import numpy as np

LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)
SAMPLE = 400_000                 # pixels used for the fit (a deterministic stride over all frames)
GRADES = ((10.0, "good"), (14.0, "fair"))          # mean error thresholds; above the last one: "poor"
COLOURLESS = 0.15               # chroma of the light/dark midpoint below which an effect counts as colourless
GRADE_NOTES = {
    "good": "two colours reproduce it; recolour freely with tint / per-copy tints",
    "fair": "close, but a second hue flattens (a cyan rim on a purple glow); judge it in the preview",
    "poor": "not a two-tone effect (fire, gold, rainbow): grey + two colours turns it pale; render colour "
            "variants in After Effects instead and import without tintable",
}


def hex_rgb(h: str) -> np.ndarray:
    h = h.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", h):
        raise ValueError(f"bad colour {h!r}: use RRGGBB")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def rgb_hex(c) -> str:
    return "".join(f"{int(round(float(np.clip(x, 0, 1)) * 255)):02X}" for x in c[:3])


def sample_pixels(st: np.ndarray, stride: int) -> np.ndarray:
    """Every ``stride``-th visible pixel of one straight RGBA frame, as rows of r, g, b, a."""
    px = st.reshape(-1, 4)
    px = px[px[:, 3] > 2 / 255]
    return px[::max(1, stride)]


def fit(px: np.ndarray, mode: str = "alpha") -> dict:
    """Best line through the visible colours (alpha-weighted principal axis), as a light and a dark end.

    ``px``: rows of straight r, g, b, a. Returns light / dark (RGB 0..1, light = the brighter end) and the error
    of ``g * light + (1 - g) * dark`` against the real colours, premultiplied (what reaches the screen), 0..255.

    ramp "colour": g is each pixel's place on that line. ramp "brightness" (an additive effect with no colour of its
    own: white lightning, white flashes): every pixel is near-white and only its brightness varies, so a colour ramp
    has nothing to work with and a tint on the dark end would never show. g is then the pixel's brightness (its
    alpha) and both ends start as the fitted white, which reproduces the render exactly; a tint on the dark end
    colours the dim glow and leaves the bright core white."""
    if len(px) < 8:
        raise ValueError("tintable: the frames have almost no visible pixels to fit")
    cs, w = px[:, :3].astype(np.float64), px[:, 3].astype(np.float64)
    m = (cs * w[:, None]).sum(0) / w.sum()
    _, _, vt = np.linalg.svd((cs - m) * np.sqrt(w)[:, None], full_matrices=False)
    v = vt[0]
    t = (cs - m) @ v
    a_end, b_end = np.clip(m + np.percentile(t, 0.5) * v, 0, 1), np.clip(m + np.percentile(t, 99.5) * v, 0, 1)
    light, dark = (b_end, a_end) if b_end @ LUM >= a_end @ LUM else (a_end, b_end)
    ramp = "colour"
    mid = (light + dark) / 2
    if mode == "additive" and mid.max() - mid.min() < COLOURLESS:
        ramp, dark = "brightness", light.copy()
        err = np.abs(light - cs).max(1) * w * 255
    else:
        g = grey_level(cs, light, dark)
        err = np.abs(g[:, None] * light + (1 - g[:, None]) * dark - cs).max(1) * w * 255
    mean = float(err.mean())
    grade = next((name for lim, name in GRADES if mean <= lim), "poor")
    return {"light": light.astype(np.float32), "dark": dark.astype(np.float32), "ramp": ramp, "error_mean": round(mean, 2),
            "error_p99": round(float(np.percentile(err, 99)), 1), "grade": grade, "note": GRADE_NOTES[grade]}


def grey_level(cs: np.ndarray, light: np.ndarray, dark: np.ndarray) -> np.ndarray:
    """Where each colour sits between dark (0) and light (1): its projection on the line, clamped."""
    d = (light - dark).astype(np.float64)
    return np.clip(((cs - dark) @ d) / max(float(d @ d), 1e-9), 0, 1)


def to_grey(st: np.ndarray, light: np.ndarray, dark: np.ndarray, ramp: str = "colour") -> np.ndarray:
    """Straight RGBA frame -> the same frame with rgb = its grey level (alpha untouched; see ``fit`` for ramp)."""
    if ramp == "brightness":
        return np.dstack([st[..., 3], st[..., 3], st[..., 3], st[..., 3]])
    g = grey_level(st[..., :3].reshape(-1, 3), light, dark).reshape(st.shape[:2]).astype(np.float32)
    return np.dstack([g, g, g, st[..., 3]])


def recolour(light: np.ndarray, dark: np.ndarray, tint: str) -> tuple[np.ndarray, np.ndarray]:
    """The slot colours for ``tint``.

    ``"LLLLLL/DDDDDD"``: exactly that light and dark colour. ``"RRGGBB"``: the fitted pair turned to that hue
    (each end keeps its own lightness and saturation, so a white-hot core stays white-hot). A colourless fit (white
    lightning, frost, grey smoke: the colour halfway between light and dark has chroma below COLOURLESS) instead takes
    the tint as its dark end, which colours the glow and keeps the core."""
    if "/" in tint:
        light_hex, dark_hex = tint.split("/", 1)
        return hex_rgb(light_hex), hex_rgb(dark_hex)
    want = colorsys.rgb_to_hls(*hex_rgb(tint))
    mid = (np.asarray(light, np.float64) + np.asarray(dark, np.float64)) / 2
    if mid.max() - mid.min() < COLOURLESS:
        # white lightning fits white -> near-black navy: turning that navy blue leaves it near-black, so a colourless
        # effect is coloured through its dark end instead
        return light, hex_rgb(tint)
    hl = [colorsys.rgb_to_hls(*map(float, c)) for c in (light, dark)]
    ref = max(hl, key=lambda h: h[2] * (1 - abs(2 * h[1] - 1)))          # the more colourful end leads
    dh = want[0] - ref[0]
    out = [np.array(colorsys.hls_to_rgb((h + dh) % 1.0, l, s), np.float32) for h, l, s in hl]
    return out[0], out[1]
