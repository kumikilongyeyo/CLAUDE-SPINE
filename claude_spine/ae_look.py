"""Judge an After Effects effect before it goes to Spine: its four key frames, over dark and over the real art.

The director's judge pass (end of anticipation, impact peak, mid decay, final residual) used to need a full import
and a Spine preview. ``quick_look`` reads the frames (aerender, or frames already on disk), finds those beats on the
effect's own energy curve (a build-and-hold such as frost gets start / half built / fully built / end instead, a
steady loop four evenly spaced frames), and puts them on one contact sheet: a row on dark grey and, given ``art`` and/or
``background``, a row in the scene, with the energy curve and the beat times underneath. Its ``hit_ae`` is the
impact time to pass straight to ae_fx_to_spine.

Render time: aerender's fixed cost is opening the project. Measured on this Mac (AE 26.5): a 72 MB project with
300+ comps takes 18-22 s per render whatever the resolution or frame step; a small single-effect project 5-8 s. So
the frames are rendered at full size, and the speed-up worth having is iterating in a small .aep.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import ae_bridge

LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)
DARK = np.array([0.10, 0.10, 0.125], np.float32)


def energy(pm: np.ndarray, mode: str) -> float:
    """How much the frame shows: emitted light (premultiplied luminance), plus coverage for normal-blend effects
    (dark smoke reads by covering, not by light)."""
    e = float((pm[..., :3] @ LUM).sum())
    return e if mode == "additive" else e + 0.25 * float(pm[..., 3].sum())


def heat(pm: np.ndarray) -> float:
    """White-hot area: the fraction of pixels whose premultiplied luminance is above 0.85. A flash peaks here even
    when the spread-out sparks after it carry more total energy (a brightest-pixel measure saturates on every
    frame with a white core, so it cannot tell the flash from what follows)."""
    return float(((pm[..., :3] @ LUM) > 0.85).mean())


def find_beats(en: list[float], ht: list[float] | None = None) -> dict:
    """The four judge frames, by the shape of the energy curve.

    hit (energy falls to half of its peak or less afterwards): anticipation_end, impact = the frame with the most
    white-hot area up to the energy peak (the flash; ``ht``; without any, the biggest energy rise), mid_decay =
    first frame at or below half the peak, residual = last visible. An effect that opens on its impact (no
    anticipation) shows its energy peak (spread) in place of anticipation_end.
    build (rises and holds: frost creeping, a charge-up): start, half_built, fully_built (95% of the peak), end.
    loop (never below 60% of its peak while visible): four evenly spaced frames."""
    e = np.asarray(en, float)
    peak_v = float(e.max())
    if peak_v <= 0:
        raise ValueError("every frame is empty: is the comp transparent/black, or is the work area wrong?")
    vis = np.nonzero(e > 0.02 * peak_v)[0]
    lo, hi = int(vis[0]), int(vis[-1])
    peak = int(np.argmax(e))
    out = {"lo": lo, "hi": hi, "peak": peak}
    if hi - lo >= 3 and e[lo:hi + 1].min() >= 0.6 * peak_v:
        idx = [lo + round(k * (hi - lo) / 4) for k in range(4)]
        return {**out, "kind": "loop", "beats": dict(zip(("loop_1", "loop_2", "loop_3", "loop_4"), idx))}
    after = [i for i in range(peak + 1, hi + 1) if e[i] <= 0.5 * peak_v]
    if not after:
        half = next(i for i in range(lo, peak + 1) if e[i] >= 0.5 * peak_v)
        full = next(i for i in range(lo, peak + 1) if e[i] >= 0.95 * peak_v)
        return {**out, "kind": "build", "beats": {"start": lo, "half_built": half, "fully_built": full, "end": hi}}
    h = np.asarray(ht, float) if ht is not None else np.zeros_like(e)
    if h[lo:peak + 1].max() > 0:
        impact = lo + int(np.argmax(h[lo:peak + 1]))
    elif peak > lo:
        impact = lo + 1 + int(np.argmax(np.diff(e[lo:peak + 1])))
    else:
        impact = lo
    if impact > lo:
        beats = {"anticipation_end": impact - 1, "impact": impact}
    else:
        spread = peak if peak > impact else min(after[0] - 1, impact + max(1, (after[0] - impact) // 2))
        beats = {"impact": impact, "spread": max(impact, spread)}
    return {**out, "kind": "hit", "beats": {**beats, "mid_decay": after[0], "residual": hi}}


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                      # Pillow < 10.1
        return ImageFont.load_default()


def _fit(im: Image.Image, w: int, h: int, cover: bool) -> Image.Image:
    k = (max if cover else min)(w / im.width, h / im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    if cover:
        x, y = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((x, y, x + w, y + h))
    return im


def _composite(pm: np.ndarray, mode: str, under: np.ndarray, over: np.ndarray | None = None) -> np.ndarray:
    """Premultiplied effect frame onto an opaque RGB plate; ``over`` (premultiplied RGBA) goes on top of it."""
    out = under + pm[..., :3] if mode == "additive" else pm[..., :3] + under * (1 - pm[..., 3:4])
    if over is not None:
        out = over[..., :3] + out * (1 - over[..., 3:4])
    return np.clip(out, 0, 1)


def _pm_image(path: str | Path, size: tuple[int, int], scale: float, offset) -> np.ndarray:
    """A picture as premultiplied RGBA float on a ``size`` canvas: centred, scaled, shifted by offset (px, y down)."""
    im = Image.open(Path(path).expanduser()).convert("RGBA")
    if scale != 1:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(im, (round((size[0] - im.width) / 2 + offset[0]), round((size[1] - im.height) / 2 + offset[1])))
    a = np.asarray(canvas, np.float32) / 255
    return np.dstack([a[..., :3] * a[..., 3:4], a[..., 3]])


def quick_look(*, aep: str = "", comp: str = "", frames_dir: str = "", fps: float = 0, mode: str = "alpha",
               art: str = "", art_scale: float = 1.0, art_offset=(0.0, 0.0), art_in_front: bool = False,
               background: str = "", out: str = "", tile: int = 260, start_frame: int | None = None,
               end_frame: int | None = None, keep_frames: str = "") -> dict:
    """Contact sheet of the four judge frames. See the module docstring; art is drawn at comp pixels x art_scale,
    centred on the comp plus art_offset (comp px, y down); art_in_front=True puts it over the effect (an aura
    behind a coin). Returns the sheet path, the beats (comp frame and seconds) and hit_ae."""
    if mode not in ae_bridge.MODES:
        raise ValueError(f"mode must be one of {ae_bridge.MODES}")
    tmp = None
    t_render = 0.0
    try:
        if aep:
            if not comp:
                raise ValueError("aep needs comp=<composition name>")
            dest = Path(keep_frames).expanduser() if keep_frames else Path(tempfile.mkdtemp(prefix="ae_look_"))
            if not keep_frames:
                tmp = dest
            t0 = time.time()
            info = ae_bridge.render_comp(aep, comp, dest, start_frame, end_frame)
            t_render = time.time() - t0
            frames, fps_v, first = info.frames, info.fps, info.start
            name = comp
        elif frames_dir:
            frames = sorted(p for e in ("*.tif", "*.tiff", "*.png") for p in Path(frames_dir).expanduser().glob(e))
            if not frames:
                raise FileNotFoundError(f"no .tif/.png frames in {frames_dir}")
            if fps <= 0:
                raise ValueError("frames_dir needs fps=<the comp's frame rate>")
            fps_v, first = fps, start_frame or 0
            name = Path(frames_dir).expanduser().resolve().name
        else:
            raise ValueError("give aep + comp, or frames_dir + fps")

        pms = [ae_bridge.read_premultiplied(f, mode) for f in frames]
        h, w = pms[0].shape[:2]
        en = [energy(p, mode) for p in pms]
        b = find_beats(en, [heat(p) for p in pms])

        k = min(tile / w, tile / h)
        tw, th = max(1, round(w * k)), max(1, round(h * k))
        small = lambda pm: np.asarray(Image.fromarray(np.round(np.clip(pm, 0, 1) * 255).astype(np.uint8), "RGBA")
                                      .resize((tw, th), Image.LANCZOS), np.float32) / 255
        dark = np.broadcast_to(DARK, (th, tw, 3))
        scene = None
        art_pm = None
        if background:
            bg = _fit(Image.open(Path(background).expanduser()).convert("RGB"), tw, th, cover=True)
            scene = np.asarray(bg, np.float32) / 255
        if art:
            art_pm = _pm_image(art, (w, h), art_scale, art_offset)
            art_pm = small(art_pm)
            if scene is None:
                scene = np.array(dark)
            if not art_in_front:
                scene = art_pm[..., :3] + scene * (1 - art_pm[..., 3:4])

        rows = [("on dark", dark, None)]
        if scene is not None:
            rows.append(("in scene", scene, art_pm if (art and art_in_front) else None))

        pad, label_w, head, curve_h = 8, 86, 34, 90
        W = label_w + 4 * (tw + pad) + pad
        H = head + len(rows) * (th + pad) + curve_h + 30
        sheet = Image.new("RGB", (W, H), (22, 22, 26))
        dr = ImageDraw.Draw(sheet)
        f13, f11 = _font(13), _font(11)
        for c, (bn, i) in enumerate(b["beats"].items()):
            x = label_w + pad + c * (tw + pad)
            dr.text((x, 4), bn.replace("_", " "), fill=(235, 235, 235), font=f13)
            dr.text((x, 19), f"frame {first + i}  ·  {(first + i) / fps_v:.3f}s", fill=(150, 150, 160), font=f11)
            spm = small(pms[i])
            for r, (_, under, over) in enumerate(rows):
                im = _composite(spm, mode, under, over)
                sheet.paste(Image.fromarray(np.round(im * 255).astype(np.uint8)), (x, head + r * (th + pad)))
        for r, (label, *_) in enumerate(rows):
            dr.text((8, head + r * (th + pad) + th // 2 - 7), label, fill=(200, 200, 200), font=f13)

        # energy curve with the beats marked
        y0 = head + len(rows) * (th + pad) + 6
        x0, x1 = label_w + pad, W - pad
        dr.rectangle([x0, y0, x1, y0 + curve_h], outline=(60, 60, 70))
        dr.text((8, y0 + curve_h // 2 - 7), "energy", fill=(200, 200, 200), font=f13)
        n = len(en)
        ex = lambda i: x0 + (x1 - x0) * (i / max(1, n - 1))
        ey = lambda v: y0 + curve_h - 4 - (curve_h - 8) * v / max(en)
        dr.line([(ex(i), ey(v)) for i, v in enumerate(en)], fill=(255, 196, 80), width=2)
        for i in b["beats"].values():
            dr.line([(ex(i), y0), (ex(i), y0 + curve_h)], fill=(110, 160, 255), width=1)
        dr.text((x0, y0 + curve_h + 6),
                f"{name}  ·  {n} frames @ {fps_v:g} fps  ·  visible {first + b['lo']}-{first + b['hi']}"
                + f"  ·  {b['kind']}  ·  energy peak frame {first + b['peak']}",
                fill=(150, 150, 160), font=f11)

        dest_png = Path(out).expanduser() if out else Path(tempfile.gettempdir()) / "claude_spine_looks" / f"{name}.png"
        dest_png.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(dest_png)

        beats = {key: {"frame": first + i, "time": round((first + i) / fps_v, 4)} for key, i in b["beats"].items()}
        res = {"sheet": str(dest_png), "name": name, "fps": fps_v, "frames": n, "size": [w, h], "kind": b["kind"],
               "visible": [first + b["lo"], first + b["hi"]], "peak": {"frame": first + b["peak"],
                                                                       "time": round((first + b["peak"]) / fps_v, 4)},
               "beats": beats}
        if b["kind"] == "hit":
            res["hit_ae"] = beats["impact"]["time"]
        elif b["kind"] == "build":
            res["built_at"] = beats["fully_built"]["time"]
        if aep:
            res["render_seconds"] = round(t_render, 1)
        return res
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
