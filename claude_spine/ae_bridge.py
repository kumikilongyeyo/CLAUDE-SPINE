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

from . import ae_tint
from .ir import Bone, MeshAttachment, RegionAttachment, Sequence, Slot
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
def frame_budget(n: int, fps: float, w: int, h: int, *, max_size: int = 0, max_frames: int = 0,
                 seq_mode: str = "once", min_fps: float = 0.0, min_size: int = 0) -> dict:
    """How ``n`` active frames of ``w`` x ``h`` at ``fps`` fit ``max_frames`` / ``max_size``: ``{step, size, note}``.

    min_fps = 0: every Nth frame until it fits max_frames, texture capped at max_size (the plain behaviour).
    min_fps > 0: max_frames x max_size^2 is a pixel BUDGET and the playback rate never falls below min_fps:
    * loop / pingpong (a choppy cycle shows on every repeat): shrink the texture first, down to min_size (default half
      of the max_size side), then drop frames, but only down to min_fps; past both, the texture shrinks further;
    * once (an impact survives dropped frames): drop frames first, but only down to min_fps, then shrink the texture.
    """
    tw0, th0 = w, h
    if max_size and max(w, h) > max_size:
        k = max_size / max(w, h)
        tw0, th0 = max(1, round(w * k)), max(1, round(h * k))
    if not max_frames or n <= max_frames:
        return {"step": 1, "size": (tw0, th0), "note": ""}
    if min_fps <= 0:
        return {"step": math.ceil(n / max_frames), "size": (tw0, th0), "note": ""}
    long0 = max(tw0, th0)
    max_step = max(1, math.floor(fps / min_fps + 1e-9))
    floor_s = min(1.0, (min_size or long0 / 2) / long0)
    note = ""

    def fit(frames: int) -> float:            # texture scale that puts `frames` frames inside the budget
        return min(1.0, math.sqrt(max_frames / frames))

    if seq_mode in ("loop", "pingpong"):
        step, s = 1, fit(n)
        if s < floor_s:
            for st in range(2, max_step + 1):
                if fit(math.ceil(n / st)) >= floor_s:
                    step, s = st, fit(math.ceil(n / st))
                    break
            else:
                step = max_step
                s = fit(math.ceil(n / step))
                note = (f"kept {fps / step:.3g} fps (min_fps {min_fps:g}): the texture went below min_size to stay in "
                        f"the budget; raise max_frames or lower min_fps for a sharper loop")
    else:
        step = min(math.ceil(n / max_frames), max_step)
        s = fit(math.ceil(n / step))
        if step < math.ceil(n / max_frames):
            note = f"kept {fps / step:.3g} fps (min_fps {min_fps:g}): more frames at a smaller texture"
    size = (max(1, round(tw0 * s)), max(1, round(th0 * s)))
    return {"step": step, "size": size, "note": note}


def import_sequence(project: Project, name: str, frames: list[str | Path], fps: float, *, mode: str = "alpha",
                    seq_mode: str = "once", animation: str = "", start: float = 0.0, hit_ae: float | None = None,
                    hit_at: float | None = None, fit_duration: float = 0.0, until: float = 0.0, x: float = 0,
                    y: float = 0, scale: float = 1.0, max_size: int = 0, max_frames: int = 0, blend: str = "",
                    color: str = "FFFFFFFF", parent: str = "root", front_of: str = "",
                    behind: str = "", fade: float = 0.0, trim: bool = True, first_frame_time: float = 0.0,
                    manifest_extra: dict | None = None, feather: float = 0.0, anchor=None,
                    deform_like: list[str] | None = None, min_fps: float = 0.0, min_size: int = 0,
                    tintable: bool = False, tint: str = "") -> dict:
    """Frames on disk -> sprites in ``images/ae/`` -> a sequence attachment on a new slot, keyed in
    ``animation`` (default ``ae_<name>``; an existing one is merged into).

    ``first_frame_time``: comp time (s) of ``frames[0]`` (its frame number / fps), used with ``hit_ae``.
    ``min_fps`` (0 = off): never subsample below this playback rate; ``max_frames`` x ``max_size`` is then a memory
    budget that loops meet by shrinking the texture first (down to ``min_size``, default half of ``max_size``) and
    one-shots by dropping frames first (see ``frame_budget``).

    ``tintable``: store the frames as grey and colour them with the slot's light + dark colour (Spine two-colour
    tint), fitted so the default look matches the render; ``tint`` recolours (see ``ae_tint.recolour``) and copies
    can take their own. The result's ``tint`` reports the fit; grade "poor" means the effect is not two-tone."""
    if tint and not tintable:
        raise ValueError("tint needs tintable=True (the frames must be stored as grey to be recoloured)")
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
    budget = frame_budget(len(keep), fps, w, h, max_size=max_size, max_frames=max_frames, seq_mode=seq_mode,
                          min_fps=min_fps, min_size=min_size)
    step, (tw, th) = budget["step"], budget["size"]
    keep = keep[::step]
    resize = (tw, th) if (tw, th) != (w, h) else None

    tint_info = None
    if tintable:                     # pass 1: fit the two colours on a sample of every kept frame
        stride = math.ceil(len(keep) * tw * th / ae_tint.SAMPLE)
        f = ae_tint.fit(np.concatenate([ae_tint.sample_pixels(to_straight(pms[i], mode, resize), stride)
                                        for i in keep]), mode)
        light, dark = ae_tint.recolour(f["light"], f["dark"], tint) if tint else (f["light"], f["dark"])
        color = ae_tint.rgb_hex(light) + (color[6:8] if len(color) >= 8 else "FF")
        tint_info = {"light": ae_tint.rgb_hex(light), "dark": ae_tint.rgb_hex(dark),
                     "fitted_light": ae_tint.rgb_hex(f["light"]), "fitted_dark": ae_tint.rgb_hex(f["dark"]), "ramp": f["ramp"],
                     "error_mean": f["error_mean"], "error_p99": f["error_p99"], "grade": f["grade"],
                     "note": f["note"], **({"tint": tint} if tint else {})}

    digits = max(2, len(str(len(keep) - 1)))
    img_dir = project.images_dir / "ae"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob(f"{name}_*.png"):
        old.unlink()
    for n, i in enumerate(keep):
        out = to_straight(pms[i], mode, resize)
        if tint_info:
            out = ae_tint.to_grey(out, ae_tint.hex_rgb(tint_info["fitted_light"]),
                                  ae_tint.hex_rgb(tint_info["fitted_dark"]), tint_info["ramp"])
        if feather > 0:
            out[..., 3] *= edge_window(out.shape[1], out.shape[0], feather)
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
    # a plain child at (x, y) in the parent's own space: it inherits the parent's rotation and scale, so a sequence
    # parented to a rotated bone (a flame pointed along a reel edge, a trail aimed away from a punch) turns with it
    # (placing it in world space with world rotation 0 silently cancelled the parent's rotation)
    if parent not in {bn.name for bn in sk.bones}:
        raise ValueError(f"no bone named {parent!r} to parent the sequence to")
    sk.bones.append(Bone(name=gname, parent=parent, x=x, y=y, length=0, color="FF9E00FF"))
    bl = blend or ("additive" if mode == "additive" else "normal")
    slot = Slot(name=sk.unique_name(f"{gname}", "slot"), bone=gname, color=color, blend=bl,
                dark=tint_info["dark"] if tint_info else None)
    if behind:
        sk.add_slot(slot, before=behind)
    elif front_of:
        sk.add_slot(slot, after=front_of)
    else:
        sk.add_slot(slot)
    ax, ay = (0.0, 0.0) if anchor is None else ((0.5 - anchor[0]) * w * scale, (anchor[1] - 0.5) * h * scale)
    seq = Sequence(count=n_out, start=0, digits=digits)
    if deform_like:
        sk.set_attachment(slot.name, "fx", follow_mesh(sk, gname, f"ae/{name}_", w * scale, h * scale, ax, ay,
                                                       deform_like, tw, th, seq))
    else:
        sk.set_attachment(slot.name, "fx", RegionAttachment(
            path=f"ae/{name}_", x=round(ax, 2), y=round(ay, 2), width=round(w * scale, 2),
            height=round(h * scale, 2), sequence=seq))

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
            "playback_fps": round(1 / delay, 3), **({"budget_note": budget["note"]} if budget["note"] else {}),
            "start": round(t0, 4), "end": round(t_off, 4), "sequence_seconds": round(dur, 4),
            "blend": bl, "mode": mode, "seq_mode": seq_mode, **({"tint": tint_info} if tint_info else {}),
            **(manifest_extra or {})}


def copy_sequence(project: Project, res: dict, *, x: float = 0.0, y: float = 0.0, start: float | None = None,
                  until: float = 0.0, parent: str | None = None, scale: float = 1.0, rotation: float = 0.0,
                  tint: str = "", offset: int = 0) -> str:
    """Another instance of an imported sequence (``res`` = the import's result) on a new slot that SHARES its frames:
    the atlas holds one set of images however many copies play (glitter in every cell of a cluster, sparks on every
    coin). x, y in ``parent``'s space (default: the original's parent); start defaults to the original's, until to the
    original's end for loops. scale multiplies this instance's size and rotation (degrees) turns it, both on the copy's
    own bone (escalating hits from one frame set: scale 1 / 1.3 / 1.7). tint recolours this copy (the import must be
    tintable). offset starts this copy's sequence that many frames in (two plumes of one looping smoke out of step).
    Returns the new slot (``copy_instance`` returns the slot, bone and placement)."""
    return copy_instance(project, res, x=x, y=y, start=start, until=until, parent=parent, scale=scale,
                         rotation=rotation, tint=tint, offset=offset)["slot"]


def copy_instance(project: Project, res: dict, *, x: float = 0.0, y: float = 0.0, start: float | None = None,
                  until: float = 0.0, parent: str | None = None, scale: float = 1.0, rotation: float = 0.0,
                  tint: str = "", offset: int = 0) -> dict:
    """``copy_sequence`` returning ``{slot, bone, x, y, start, end, scale, rotation}`` (+ ``light``, ``dark``
    when tinted)."""
    sk = project.data
    src = next(s for s in sk.slots if s.name == res["slot"])
    src_bone = next(b for b in sk.bones if b.name == res["bone"])
    parent = parent or src_bone.parent
    if parent not in {b.name for b in sk.bones}:
        raise ValueError(f"no bone named {parent!r} to parent the sequence copy to")
    if not scale or scale <= 0:
        raise ValueError(f"copy scale must be positive, not {scale!r}")
    color, dark = src.color, src.dark
    if tint:
        if not res.get("tint"):
            raise ValueError("a copy's tint needs the sequence imported with tintable=True")
        light, dk = ae_tint.recolour(ae_tint.hex_rgb(res["tint"]["fitted_light"]),
                                     ae_tint.hex_rgb(res["tint"]["fitted_dark"]), tint)
        color, dark = ae_tint.rgb_hex(light) + src.color[6:8], ae_tint.rgb_hex(dk)
    t0 = res["start"] if start is None else start
    bn = sk.unique_name(res["bone"])
    sk.bones.append(Bone(name=bn, parent=parent, x=x, y=y, rotation=rotation, scaleX=scale, scaleY=scale, length=0,
                         color="FF9E00FF"))
    slot = Slot(name=sk.unique_name(bn, "slot"), bone=bn, color=color, dark=dark, blend=src.blend)
    sk.add_slot(slot, after=res["slot"])
    sk.set_attachment(slot.name, "fx", sk.attachment(res["slot"], "fx").model_copy(deep=True))
    ab = AnimBuilder(sk, res["animation"], replace=False)
    if res["seq_mode"] == "once":
        end = t0 + res["sequence_seconds"]
    else:
        end = until or (t0 + (res["end"] - res["start"]))
    pts = [(r(t0), "fx"), (r(end), None)]
    if t0 > 0:
        pts.insert(0, (0.0, None))
    ab.slot_attachment(slot.name, pts)
    if offset and not 0 <= offset < res["frames_out"]:
        raise ValueError(f"copy offset {offset} is outside the sequence's {res['frames_out']} frames")
    ab.sequence(slot.name, "fx", [(t0, res["seq_mode"], int(offset), res["delay"])])
    return {"slot": slot.name, "bone": bn, "x": x, "y": y, "start": round(t0, 4), "end": round(end, 4),
            "scale": scale, "rotation": rotation, **({"light": color[:6], "dark": dark} if tint else {}),
            **({"offset": int(offset)} if offset else {})}


def parse_copy(cp) -> dict:
    """One ``copies`` entry: [x, y], [x, y, start], [x, y, start, scale] or [x, y, start, scale, rotation]
    (start may be null = the original's start), or a dict with those keys plus ``tint`` (a tintable import's copy in
    its own colour: "RRGGBB" or "light/dark"), ``offset`` (frames into the sequence the copy starts at) and ``parent``
    (the bone the copy hangs from, default the original's: an aura on each of three coins from one frame set)."""
    tint, offset, parent = "", 0, None
    if isinstance(cp, dict):
        unknown = set(cp) - {"x", "y", "start", "scale", "rotation", "tint", "offset", "parent"}
        if unknown or "x" not in cp or "y" not in cp:
            raise ValueError(f"copy {cp!r}: give x, y and optionally start, scale, rotation, tint, offset, parent")
        parent = cp.get("parent") or None
        tint = cp.get("tint") or ""
        offset = int(cp.get("offset") or 0)
        if offset < 0:
            raise ValueError(f"copy {cp!r}: offset is a frame count, 0 or more")
        if tint:
            for part in str(tint).split("/"):
                ae_tint.hex_rgb(part)                    # a bad colour fails before anything is written
        cp = [cp["x"], cp["y"], cp.get("start"), cp.get("scale"), cp.get("rotation")]
    cp = list(cp)
    if not 2 <= len(cp) <= 5:
        raise ValueError(f"copy {cp!r}: use [x, y], [x, y, start], [x, y, start, scale] or [x, y, start, scale, rotation]")
    cp += [None] * (5 - len(cp))
    x, y, start, scale, rot = cp
    if scale is not None and float(scale) <= 0:
        raise ValueError(f"copy {cp[:5]!r}: scale must be positive")
    return {"x": float(x), "y": float(y), "start": None if start is None else float(start),
            "scale": 1.0 if scale is None else float(scale), "rotation": 0.0 if rot is None else float(rot),
            **({"tint": str(tint)} if tint else {}), **({"offset": offset} if offset else {}),
            **({"parent": str(parent)} if parent else {})}


# Spectrum bands, outermost (largest) first. Additive copies of one frame set in these colours sum to white where
# they overlap: 3 = red / green / blue; 6 = red, yellow, green, cyan, blue, magenta at a third each (smoother).
SPECTRUM_BANDS = {3: ["FF0000", "00FF00", "0000FF"],
                  6: ["550000", "555500", "005500", "005555", "000055", "550055"]}


def disperse(project: Project, res: dict, spread: float, bands: int = 3, turn: float = 0.0) -> dict:
    """Split every instance of a tintable sequence (the import and its copies) into a spectrum: the instance's own
    slot becomes the middle band and the other bands are copies on child bones, each one scaled ``spread`` more
    than the next (red outermost) and turned ``turn`` degrees, all sharing the one frame set. They are drawn
    additive, so where they overlap they add back up to the render's own light and only the edges split into
    colour: real dispersion (a prism, a lens's chromatic fringe) for no extra frames. Fill cost grows with
    ``bands`` (every band covers the glow's area again): 3 is the cheap one."""
    if not res.get("tint"):
        raise ValueError("spectrum needs tintable=True")
    if bands not in SPECTRUM_BANDS:
        raise ValueError(f"spectrum_bands must be one of {sorted(SPECTRUM_BANDS)}")
    if not 0 < spread <= 0.3:
        raise ValueError("spectrum (the scale step between bands) must be in (0, 0.3]; 0.02-0.05 looks like light")
    sk = project.data
    cols = SPECTRUM_BANDS[bands]
    m = bands // 2
    insts = [{"slot": res["slot"], "bone": res["bone"], "start": res["start"]}] + list(res.get("copy_instances", []))
    out = []
    for inst in insts:
        slot = sk.slot(inst["slot"])
        alpha = slot.color[6:8] or "FF"
        slot.color, slot.dark, slot.blend = cols[m] + alpha, cols[m], "additive"
        anim = sk.animations[res["animation"]]
        for k in anim.slots.get(slot.name, {}).get("rgba", []):          # a fade keys the slot colour: keep the band
            k.color = cols[m] + k.color[6:]
        made = [slot.name]
        for k, c in enumerate(cols):
            if k == m:
                continue
            ci = copy_instance(project, res, x=0.0, y=0.0, start=inst["start"], parent=inst["bone"],
                               scale=1 + spread * (m - k), rotation=turn * (m - k), tint=f"{c}/{c}")
            s = sk.slot(ci["slot"])
            s.color, s.blend = c + alpha, "additive"
            made.append(ci["slot"])
        out.append(made)
    return {"bands": cols, "spread": spread, "turn": turn, "slots": out}


def fx_to_spine(project: Project, name: str, *, aep: str = "", comp: str = "", frames_dir: str = "",
                fps: float = 0, start_frame: int | None = None, end_frame: int | None = None,
                keep_frames: str = "", template: str = DEFAULT_TEMPLATE, copies: list | None = None,
                spectrum: float = 0.0, spectrum_bands: int = 3, spectrum_turn: float = 0.0, **kw) -> dict:
    """Render (or read) the frames and import them. Either ``aep`` + ``comp`` (rendered with aerender) or
    ``frames_dir`` + ``fps`` (frames already on disk: TIFF premultiplied, or PNG straight RGBA / light-on-black
    RGB)."""
    placed = [parse_copy(cp) for cp in copies or []]       # a bad entry fails before anything is rendered or written
    if any("tint" in c for c in placed) and not kw.get("tintable"):
        raise ValueError("copies with a tint need tintable=True")
    if spectrum and not kw.get("tintable"):
        raise ValueError("spectrum needs tintable=True")
    if spectrum and spectrum_bands not in SPECTRUM_BANDS:
        raise ValueError(f"spectrum_bands must be one of {sorted(SPECTRUM_BANDS)}")
    if kw.get("tint"):
        for part in str(kw["tint"]).split("/"):
            ae_tint.hex_rgb(part)
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
        if placed:   # [[x, y], [x, y, start], [x, y, start, scale, rotation], ...]: more instances sharing the frames
            inst = [copy_instance(project, res, until=kw.get("until", 0.0), **c) for c in placed]
            res["copies"] = [c["slot"] for c in inst]          # slot names, as before
            res["copy_instances"] = inst                        # slot + bone + placement of each copy
        if spectrum:
            res["spectrum"] = disperse(project, res, spectrum, spectrum_bands, spectrum_turn)
        return res
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------- placement helpers
def edge_window(w: int, h: int, feather: float) -> np.ndarray:
    """1 inside, falling to 0 over `feather` (fraction of the longest side) toward the frame border: light the
    comp edge would cut square (a lens-flare halo near the border) fades out instead."""
    yy, xx = np.mgrid[0:h, 0:w]
    e = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy]) / (feather * max(w, h))
    return np.clip(e, 0, 1) ** 1.5


def follow_mesh(sk, bone: str, path: str, W: float, H: float, ox: float, oy: float, like: list[str],
                tw: int, th: int, seq: Sequence, nx: int = 12, ny: int = 12) -> MeshAttachment:
    """A grid mesh over the sequence whose vertices take their bone weights from the nearest vertices of the
    `like` slots (skin transfer), so baked light on the art deforms exactly like the art does."""
    from .mesh import mesh_world_vertices, region_pixel_to_local, to_world
    from .weights import decode_weighted, skin_vertices
    world = sk.world()
    src_pts, src_inf = [], []
    for sl in like:
        s = sk.slot(sl)
        names = [s.attachment] if s.attachment else list(sk.skin().attachments.get(sl, {}))
        att = sk.attachment(sl, names[0])
        if isinstance(att, MeshAttachment):
            n = len(att.uvs) // 2
            wv = mesh_world_vertices(sk, sl, att, world)
            infs = decode_weighted(att.vertices, n) if len(att.vertices) != 2 * n else                 [[(sk.bone_index(s.bone), 0, 0, 1.0)]] * n
            for p, inf in zip(wv, infs):
                src_pts.append(p)
                src_inf.append({bi: wt for bi, _, _, wt in inf})
        elif isinstance(att, RegionAttachment):
            f, _ = region_pixel_to_local(att, 2, 2)
            for p in to_world(world[s.bone], f(np.array([[0, 0], [2, 0], [0, 2], [2, 2], [1, 1]], float))):
                src_pts.append(p)
                src_inf.append({sk.bone_index(s.bone): 1.0})
    if not src_pts:
        raise ValueError(f"deform_like: none of {like} has a region or mesh to follow")
    src = np.asarray(src_pts, float)
    gx, gy = np.meshgrid(np.arange(nx), np.arange(ny))
    idx = np.arange(nx * ny).reshape(ny, nx)
    ring = list(idx[0, :]) + list(idx[1:, -1]) + list(idx[-1, -2::-1]) + list(idx[-2:0:-1, 0])
    inner = [i for i in range(nx * ny) if i not in set(ring)]
    order = ring + inner
    pos = {v: k for k, v in enumerate(order)}
    u = (gx.ravel() / (nx - 1))[order]
    v = (gy.ravel() / (ny - 1))[order]
    local = np.c_[ox - W / 2 + u * W, oy + H / 2 - v * H]
    wpts = to_world(world[bone], local)
    bones = sorted({b for inf in src_inf for b in inf})
    col = {b: i for i, b in enumerate(bones)}
    Wt = np.zeros((len(wpts), len(bones)))
    for i, p in enumerate(wpts):
        d = np.hypot(*(src - p).T)
        near = np.argsort(d)[:4]
        ws = 1 / np.maximum(d[near], 1.0) ** 2
        for j, wv in zip(near, ws / ws.sum()):
            for b, wt in src_inf[j].items():
                Wt[i, col[b]] += wv * wt
        top = np.argsort(Wt[i])[::-1][4:]
        Wt[i, top] = 0
        Wt[i] /= Wt[i].sum()
    tris = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = idx[j, i], idx[j, i + 1], idx[j + 1, i], idx[j + 1, i + 1]
            tris += [pos[a], pos[b], pos[c], pos[b], pos[d], pos[c]]
    verts = skin_vertices(wpts, Wt, bones, [world[sk.bones[b].name] for b in bones])
    hull_edges = []
    for i in range(len(ring)):
        hull_edges += [i * 2, ((i + 1) % len(ring)) * 2]
    return MeshAttachment(path=path, uvs=[round(float(q), 5) for q in np.c_[u, v].ravel()], triangles=tris,
                          vertices=verts, hull=len(ring), edges=hull_edges, width=tw, height=th, sequence=seq)


def check_aep(aep: str | Path, comps: list[str] | None = None) -> dict:
    """What a SAVED .aep holds, without After Effects: every item / layer / effect name (the file's Utf8
    chunks), the ``CLAUDE_ERR ...`` comps a template script leaves when it fails, and whether the given comps
    exist. Use it after running a template in AE to confirm the comps are there before aerender."""
    data = Path(aep).expanduser().read_bytes()
    names, i = [], 0
    while True:
        i = data.find(b"Utf8", i)
        if i < 0 or i + 8 > len(data):
            break
        n = struct.unpack(">I", data[i + 4:i + 8])[0]
        if 0 < n < 4096:
            try:
                names.append(data[i + 8:i + 8 + n].decode("utf-8"))
            except UnicodeDecodeError:
                pass
        i += 8
    uniq = list(dict.fromkeys(names))
    errors = [x for x in uniq if x.startswith("CLAUDE_ERR")]
    out = {"aep": str(Path(aep).expanduser()), "names": len(uniq), "errors": errors}
    if comps:
        out["found"] = {c: c in uniq for c in comps}
    out["sample"] = [x for x in uniq if not x.startswith("ADBE")][:60]
    return out
