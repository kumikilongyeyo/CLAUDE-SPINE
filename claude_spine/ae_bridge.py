"""After Effects -> Spine bridge: the ``ae_fx_to_spine`` tool's engine.

After Effects does what Spine cannot (glows driven by depth, relief shimmer, fire, splashes, lighting);
Spine does what a game needs (cheap playback, timing against the symbol's own animation). This module is the
seam: it renders an AE comp to a frame sequence, turns the frames into straight-alpha sprites, and wires them
into a skeleton as a Spine *sequence* attachment whose timing is matched to the AE comp.

Rendering uses ``aerender``, a separate headless AE process that reads the saved ``.aep`` from disk. It never
touches the project open in the AE window (so unsaved edits there are NOT rendered: save first).

Alpha, from the comp's own transparency (``alpha``) or from brightness (``additive``):

* ``alpha``: the "TIFF Sequence with Alpha" template writes premultiplied RGB + alpha. Straight colour is
  ``rgb / a``. PNG sequences were not used because this AE install has no PNG output template.
* ``additive``: light on black. What reaches the screen on an additive slot is just ``rgb``, so
  ``a = max(rgb)`` and the colour is ``rgb / a`` (the atlas packer premultiplies it again).

Timing: Spine's sequence timeline plays ``count`` frames with a per-frame ``delay`` in seconds, so
``delay = step / comp_fps`` reproduces AE's speed exactly. ``hit_ae`` (the moment in the comp that matters,
in seconds) together with ``hit_at`` (where that moment should land in the Spine animation) positions the
sequence, so the AE impact lines up with the Spine one. ``fit_duration`` instead stretches the sequence to
span a given time, which is how a loop is made to divide the symbol's loop length.
"""
from __future__ import annotations

import glob
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .ir import RegionAttachment, Sequence, Slot
from .project import Project
from .timeline import AnimBuilder, r

DEFAULT_TEMPLATE = "TIFF Sequence with Alpha"
MODES = ("alpha", "additive")
SEQ_MODES = ("once", "loop", "pingpong")
THRESH = 6 / 255          # a frame counts as "active" above this (brightest pixel, or alpha)


# ------------------------------------------------------------------ aerender
def find_aerender() -> Path:
    """``AERENDER`` env var, else the newest ``/Applications/Adobe After Effects*/aerender``."""
    env = os.environ.get("AERENDER")
    if env and Path(env).exists():
        return Path(env)
    found = sorted(glob.glob("/Applications/Adobe After Effects*/aerender")
                   + glob.glob("C:/Program Files/Adobe/Adobe After Effects*/Support Files/aerender.exe"))
    if not found:
        raise FileNotFoundError("aerender not found; set the AERENDER environment variable to its path")
    return Path(found[-1])


def available() -> bool:
    try:
        find_aerender()
        return True
    except FileNotFoundError:
        return False


@dataclass
class RenderInfo:
    fps: float
    width: int
    height: int
    start: int                 # first rendered frame number (comp frames)
    end: int
    frames: list[Path]


def parse_render_log(text: str) -> dict:
    """The facts aerender prints about the comp: frame rate, size and the work-area span."""
    def grab(pat, cast=float):
        m = re.search(pat, text)
        return cast(m.group(1)) if m else None
    size = re.search(r"Size:\s*(\d+)\s*x\s*(\d+)", text)
    return {"fps": grab(r"Frame Rate:\s*([\d.]+)"), "start": grab(r"Start:\s*(\d+)", int),
            "end": grab(r"End:\s*(\d+)", int),
            "width": int(size.group(1)) if size else None, "height": int(size.group(2)) if size else None}


def render_comp(aep: str | Path, comp: str, out_dir: str | Path, start: int | None = None,
                end: int | None = None, template: str = DEFAULT_TEMPLATE, timeout: float = 1800) -> RenderInfo:
    """Render ``comp`` of the saved ``aep`` to ``out_dir`` (frame numbers are the comp's own, 0-based).
    Default span is the comp's work area, exactly as AE would render it."""
    aep = Path(aep).expanduser().resolve()
    if not aep.exists():
        raise FileNotFoundError(f"project not found: {aep}")
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cmd = [str(find_aerender()), "-project", str(aep), "-comp", comp, "-OMtemplate", template,
           "-output", str(out / "f_[#####]")]
    if start is not None:
        cmd += ["-s", str(start)]
    if end is not None:
        cmd += ["-e", str(end)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    log = p.stdout + "\n" + p.stderr
    errors = [ln for ln in log.splitlines() if re.search(r"aerender\s+error", ln, re.I)]
    if p.returncode != 0 or errors:
        raise RuntimeError("aerender failed:\n" + ("\n".join(errors) or log[-1500:])[:1500])
    frames = sorted(out.glob("f_*.*"))
    if not frames:
        raise RuntimeError(f"aerender wrote no frames for comp {comp!r}\n{log[-1500:]}")
    info = parse_render_log(log)
    if not info["fps"]:
        raise RuntimeError("could not read the comp's frame rate from aerender's log")
    first = start if start is not None else (info["start"] or 0)
    return RenderInfo(info["fps"], info["width"] or 0, info["height"] or 0, first, first + len(frames) - 1, frames)


# --------------------------------------------------------------- frame input
def read_tiff(path: str | Path) -> np.ndarray:
    """Uncompressed strip TIFF (what AE writes) -> float32 H x W x C in 0..1. PIL cannot read AE's alpha
    (the extra sample is not flagged), so this is read by hand; 8 and 16 bit, either byte order."""
    d = Path(path).read_bytes()
    e = ">" if d[:2] == b"MM" else "<"
    ifd = struct.unpack(e + "I", d[4:8])[0]
    n = struct.unpack(e + "H", d[ifd:ifd + 2])[0]
    size = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i"}
    tags: dict[int, tuple] = {}
    for i in range(n):
        o = ifd + 2 + 12 * i
        tag, typ, cnt = struct.unpack(e + "HHI", d[o:o + 8])
        nbytes = size.get(typ, 1) * cnt
        raw = d[o + 8:o + 8 + nbytes] if nbytes <= 4 else d[struct.unpack(e + "I", d[o + 8:o + 12])[0]:][:nbytes]
        if typ in fmt:
            tags[tag] = struct.unpack(e + str(cnt) + fmt[typ], raw)
    if tags.get(259, (1,))[0] != 1:
        raise ValueError(f"{path}: compressed TIFF; use the 'TIFF Sequence with Alpha' template (uncompressed)")
    w, h, spp, bps = tags[256][0], tags[257][0], tags[277][0], tags[258][0]
    buf = b"".join(d[o:o + c] for o, c in zip(tags[273], tags[279]))
    dt = np.dtype(e + ("u2" if bps == 16 else "u1"))
    a = np.frombuffer(buf, dt)[:w * h * spp].reshape(h, w, spp).astype(np.float32)
    return a / (65535.0 if bps == 16 else 255.0)


def read_premultiplied(path: str | Path, mode: str) -> np.ndarray:
    """One frame as premultiplied RGBA float32 (what an additive or normal blend actually adds)."""
    p = Path(path)
    if p.suffix.lower() in (".tif", ".tiff"):
        a = read_tiff(p)
        if a.shape[2] == 3:
            a = np.dstack([a, np.ones(a.shape[:2], np.float32)])
        return a[..., :4]
    im = Image.open(p)
    if im.mode == "RGBA":                    # PNG: straight alpha by convention
        s = np.asarray(im, np.float32) / 255
        return np.dstack([s[..., :3] * s[..., 3:4], s[..., 3]])
    rgb = np.asarray(im.convert("RGB"), np.float32) / 255
    return np.dstack([rgb, np.ones(rgb.shape[:2], np.float32)])


def to_straight(pm: np.ndarray, mode: str, size: tuple[int, int] | None = None) -> np.ndarray:
    """Premultiplied RGBA -> straight RGBA (uint8-ready 0..1), resized premultiplied so soft edges do not
    fringe."""
    rgb, a = pm[..., :3], pm[..., 3]
    if mode == "additive":
        a = rgb.max(axis=2)                  # light on black: brightness is the alpha
    if size and (size[0], size[1]) != (pm.shape[1], pm.shape[0]):
        stacked = np.dstack([rgb, a])
        im = Image.fromarray(np.round(np.clip(stacked, 0, 1) * 255).astype(np.uint8), "RGBA")
        s = np.asarray(im.resize(size, Image.LANCZOS), np.float32) / 255
        rgb, a = s[..., :3], s[..., 3]
    col = np.divide(rgb, a[..., None], out=np.zeros_like(rgb), where=a[..., None] > 1e-4)
    return np.dstack([np.clip(col, 0, 1), np.clip(a, 0, 1)])


def active_range(pms: list[np.ndarray], mode: str) -> tuple[int, int]:
    """First and last frame with something visible (leading and trailing empty frames cost atlas space)."""
    idx = [i for i, pm in enumerate(pms)
           if (pm[..., :3].max() if mode == "additive" else pm[..., 3].max()) > THRESH]
    if not idx:
        raise ValueError("every frame is empty: is the comp transparent/black, or is the work area wrong?")
    return idx[0], idx[-1]


# ----------------------------------------------------------------- the bridge
def import_sequence(project: Project, name: str, frames: list[str | Path], fps: float, *, mode: str = "alpha",
                    seq_mode: str = "once", animation: str = "", start: float = 0.0, hit_ae: float | None = None,
                    hit_at: float | None = None, fit_duration: float = 0.0, until: float = 0.0, x: float = 0,
                    y: float = 0, scale: float = 1.0, max_size: int = 0, max_frames: int = 0, blend: str = "",
                    color: str = "FFFFFFFF", parent: str = "root", front_of: str = "",
                    behind: str = "", fade: float = 0.0, trim: bool = True, first_frame_time: float = 0.0,
                    manifest_extra: dict | None = None) -> dict:
    """Frames on disk -> sprites in ``images/ae/`` -> a sequence attachment on a new slot, keyed in
    ``animation`` (default ``ae_<name>``; an existing one is merged into).

    ``first_frame_time``: comp time (s) of ``frames[0]`` (its frame number / fps), used with ``hit_ae``."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if seq_mode not in SEQ_MODES:
        raise ValueError(f"seq_mode must be one of {SEQ_MODES}")
    if not frames:
        raise ValueError("no frames")
    if fps <= 0:
        raise ValueError("fps must be positive")
    sk = project.data
    pms = [read_premultiplied(f, mode) for f in frames]
    h, w = pms[0].shape[:2]
    if any(p.shape[:2] != (h, w) for p in pms):
        raise ValueError("frames differ in size")

    lo, hi = active_range(pms, mode) if trim else (0, len(pms) - 1)
    keep = list(range(lo, hi + 1))
    step = 1
    if max_frames and len(keep) > max_frames:
        step = math.ceil(len(keep) / max_frames)
        keep = keep[::step]
    tw, th = w, h
    if max_size and max(w, h) > max_size:
        k = max_size / max(w, h)
        tw, th = max(1, round(w * k)), max(1, round(h * k))

    digits = max(2, len(str(len(keep) - 1)))
    img_dir = project.images_dir / "ae"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob(f"{name}_*.png"):
        old.unlink()
    for n, i in enumerate(keep):
        out = to_straight(pms[i], mode, (tw, th) if (tw, th) != (w, h) else None)
        im = Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA")
        project.write_image(f"ae/{name}_{str(n).zfill(digits)}", im)

    # ---- timing: seconds per sprite, and where the sequence starts in the Spine animation
    n_out = len(keep)
    delay = fit_duration / n_out if fit_duration else step / fps
    sprite_t0 = first_frame_time + lo / fps              # comp time of the first sprite
    if hit_ae is not None:
        if hit_at is None:
            raise ValueError("hit_ae needs hit_at (the Spine time the AE moment should land on)")
        t0 = hit_at - (hit_ae - sprite_t0) * (delay * fps / step)      # fit_duration changes the playback speed
    else:
        t0 = start
    if t0 < -1e-6:
        raise ValueError(f"the sync puts the sequence at t={t0:.3f}s, before the animation starts; "
                         f"raise hit_at to at least {hit_at - t0:.3f} or trim less")
    t0 = max(0.0, t0)
    dur = n_out * delay

    # ---- skeleton: group bone, slot, attachment
    gname = sk.unique_name(f"ae_{name}")
    pw = sk.world()[parent]
    wx, wy = pw.to_world(x, y)
    sk.add_bone_world(gname, parent, wx, wy, 0, color="FF9E00FF")
    bl = blend or ("additive" if mode == "additive" else "normal")
    slot = Slot(name=sk.unique_name(f"{gname}", "slot"), bone=gname, color=color, blend=bl)
    if behind:
        sk.add_slot(slot, before=behind)
    elif front_of:
        sk.add_slot(slot, after=front_of)
    else:
        sk.add_slot(slot)
    sk.set_attachment(slot.name, "fx", RegionAttachment(
        path=f"ae/{name}_", width=round(w * scale, 2), height=round(h * scale, 2),
        sequence=Sequence(count=n_out, start=0, digits=digits)))

    anim = animation or f"ae_{name}"
    ab = AnimBuilder(sk, anim, replace=animation == "")
    end_t = t0 + dur
    if seq_mode == "once":
        t_off = end_t
    else:
        t_off = until or max(end_t, sk.animations[anim].duration() if anim in sk.animations else 0.0)
    pts = [(t0, "fx"), (r(t_off), None)]
    if t0 > 0:
        pts.insert(0, (0.0, None))
    ab.slot_attachment(slot.name, pts)
    ab.sequence(slot.name, "fx", [(t0, seq_mode, 0, delay)])
    if fade > 0 and t_off - fade > t0:
        c, a = color[:6], (color[6:8] if len(color) >= 8 else "FF")
        ab.slot_color(slot.name, [(t0, c + a), (t_off - fade, c + a), (t_off, c + "00")], "linear")
    ab.event(t0, f"ae_{name}")

    return {"name": name, "animation": anim, "slot": slot.name, "bone": gname, "event": f"ae_{name}",
            "frames_in": len(frames), "frames_out": n_out, "trimmed": [lo, hi], "step": step,
            "image_size": [tw, th], "source_size": [w, h], "fps": fps, "delay": round(delay, 5),
            "start": round(t0, 4), "end": round(t_off, 4), "sequence_seconds": round(dur, 4),
            "blend": bl, "mode": mode, "seq_mode": seq_mode, **(manifest_extra or {})}


def fx_to_spine(project: Project, name: str, *, aep: str = "", comp: str = "", frames_dir: str = "",
                fps: float = 0, start_frame: int | None = None, end_frame: int | None = None,
                keep_frames: str = "", template: str = DEFAULT_TEMPLATE, **kw) -> dict:
    """Render (or read) the frames and import them. Either ``aep`` + ``comp`` (rendered with aerender) or
    ``frames_dir`` + ``fps`` (frames already on disk: TIFF premultiplied, or PNG straight RGBA / light-on-black
    RGB)."""
    tmp = None
    try:
        if aep:
            if not comp:
                raise ValueError("aep needs comp=<composition name>")
            dest = Path(keep_frames).expanduser() if keep_frames else Path(tempfile.mkdtemp(prefix="ae_fx_"))
            if not keep_frames:
                tmp = dest
            info = render_comp(aep, comp, dest, start_frame, end_frame, template)
            frames, fps_v = info.frames, info.fps
            first_time = info.start / info.fps
            src = {"aep": str(Path(aep).expanduser().resolve()), "comp": comp, "comp_fps": info.fps,
                   "comp_size": [info.width, info.height], "comp_frames": [info.start, info.end]}
        elif frames_dir:
            exts = ("*.tif", "*.tiff", "*.png")
            frames = sorted(p for e in exts for p in Path(frames_dir).expanduser().glob(e))
            if not frames:
                raise FileNotFoundError(f"no .tif/.png frames in {frames_dir}")
            if fps <= 0:
                raise ValueError("frames_dir needs fps=<the comp's frame rate>")
            fps_v, first_time = fps, (start_frame or 0) / fps
            src = {"frames_dir": str(Path(frames_dir).expanduser().resolve())}
        else:
            raise ValueError("give aep + comp, or frames_dir + fps")
        res = import_sequence(project, name, frames, fps_v, first_frame_time=first_time, **kw)
        res["source"] = src
        return res
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
