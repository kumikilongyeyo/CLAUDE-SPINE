"""Lay a straight After Effects piece on every segment of a polyline in Spine: the ``ae_polyline_fx`` tool's engine.

For a line with sharp corners (a slot payline) bending one long strip always costs something: a thick strip folds on
the inside of a sharp corner, rounding it smears the glow, and one texture spanning the whole route is magnified on a
long one. Here NOTHING bends:

* ``<name>_c0..cK``  control bones, one per knot. The setup pose is the line you give (a straight row is best: every
  route the game sets is then reached the same way); the game moves them to the winning line's points.
* ``<name>_s0..sK-1`` one segment bone per knot pair, child of its start knot, aimed at the next knot by a one-bone
  IK constraint with ``stretch``: it turns and stretches to reach the next knot wherever the knots move.
* per segment and per layer (e.g. a soft ``aura`` and a sharp ``core`` render of the same piece) an additive region
  playing the AE frames as a sequence. The piece's strip runs past both of its knots by ``pad`` strip px; those ends
  fade out complementarily (over ``fade`` px each side of the knot, per layer), so where two pieces overlap at a knot
  the straight light adds back to one and the glows sum into the corner, like the strokes of the AE comp.
* ``<name>_head``     an optional head-knot sequence on the last knot.

One frame set per layer is shared by every segment (each plays it at its own phase, so the pieces do not repeat in
step). Animations: ``<name>_in`` (pieces draw on one after the other from the first knot, ``stagger`` s apart, the
head fades in at the end), ``<name>_loop`` and ``<name>_out``. Slot alpha ramps from ``tail_alpha`` on the first piece to
1 on the last, so the line is dim at its tail and full at its head.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import ae_bridge
from .ae_path import SEQ_MODES, _frame_source
from .ir import IkConstraint, RegionAttachment, Sequence, Slot
from .project import Project
from .rig import _next_order
from .timeline import AnimBuilder, r

DEFAULT_PARTS = [{"name": "in", "frames": [0, 17], "mode": "once"},
                 {"name": "loop", "frames": [18, 77], "mode": "loop"},
                 {"name": "out", "frames": [78, 89], "mode": "once"}]


def end_ramp(w: int, pad: float, fade: float) -> np.ndarray:
    """Per-column alpha of a piece whose knots sit at strip x = pad and x = w - pad: 0 -> 1 across [pad - fade,
    pad + fade] and back down across [w - pad - fade, w - pad + fade]. Two pieces overlapping at a knot sum to 1."""
    x = np.arange(w) + 0.5
    f = max(float(fade), 0.5)
    up = np.clip((x - (pad - f)) / (2 * f), 0, 1)
    down = np.clip(((w - pad + f) - x) / (2 * f), 0, 1)
    return np.minimum(up, down)


def _write(project: Project, prefix: str, pms: list[np.ndarray], fps: float, mode: str, seq_mode: str,
           max_size: int, max_frames: int, ramp: np.ndarray | None) -> dict:
    h, w = pms[0].shape[:2]
    budget = ae_bridge.frame_budget(len(pms), fps, w, h, max_size=max_size, max_frames=max_frames, seq_mode=seq_mode)
    step, (tw, th) = budget["step"], budget["size"]
    keep = list(range(0, len(pms), step))
    resize = (tw, th) if (tw, th) != (w, h) else None
    digits = max(2, len(str(len(keep) - 1)))
    img_dir = project.images_dir / "ae"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob(f"{prefix.split('/')[-1]}[0-9]*.png"):
        old.unlink()
    for n, i in enumerate(keep):
        pm = pms[i].copy()
        if ramp is not None:                         # fade the premultiplied light, then make it straight
            pm *= ramp[None, :, None]
        out = ae_bridge.to_straight(pm, mode, resize)
        project.write_image(f"ae/{prefix}{str(n).zfill(digits)}", Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA"))
    return {"n": len(keep), "digits": digits, "w": w, "h": h, "tw": tw, "th": th, "delay": step / fps,
            "dur": len(keep) * step / fps}


def polyline_fx(project: Project, name: str, points: list[list[float]], layers: list[dict], *, aep: str = "",
                frames_dir: str = "", fps: float = 0, pad: float = 96.0, across_scale: float = 1.0,
                baseline: float = 0.5, mode: str = "additive", parts: list[dict] | None = None, head: dict | None = None,
                stagger: float = 0.06, tail_alpha: float = 0.3, tail_curve: float = 1.6, phase: int = 17,
                parent: str = "root",
                max_size: int = 0, max_frames: int = 0) -> dict:
    """Pieces on every segment of ``points`` (knots in the parent bone's space, >= 2).

    ``layers``: ``[{"name": "aura", "comp": "...", "fade": 96, "max_size": 320}, {"name": "core", "comp": "...",
    "fade": 24}]`` drawn in that order (first = behind). Each is a straight piece rendered by the energy_payline template
    with ``piece=segment`` (or any strip whose knots sit ``pad`` px in from both ends); ``frames_dir`` + ``fps`` per
    layer work too. ``fade``: strip px each side of a knot over which the piece fades out (small for a sharp core,
    about ``pad`` for soft light). ``parts``: comp frame ranges of in / loop / out (default: the energy_payline
    timeline); a part may set ``max_frames`` (or a layer ``loop_frames``) to subsample. ``head``: ``{"comp": "...",
    "size": [w, h]}`` a head-knot render (``piece=head``) placed on the last knot. ``across_scale``: world units per
    strip px across the line. Slot alpha = ``tail_alpha`` + (1 - tail_alpha) * u ** ``tail_curve`` along the pieces (u = 0
    at the tail, 1 at the head), times a layer's ``alpha`` (overlapping soft pieces add up: ~0.85 matches one AE
    stroke). Along the line each piece spans its segment exactly (strip px between the knots map
    onto the segment's length, so a longer segment stretches its piece)."""
    if len(points) < 2:
        raise ValueError("points needs at least two [x, y] knots")
    if not layers:
        raise ValueError("layers needs at least one {name, comp | frames_dir}")
    parts = parts or DEFAULT_PARTS
    for p in parts:
        if not p.get("name") or len(p.get("frames", [])) != 2 or p.get("mode", "once") not in SEQ_MODES:
            raise ValueError('each part is {"name": str, "frames": [first, last], "mode": "once|loop|pingpong|hold"}')
    names = [p["name"] for p in parts]
    sk = project.data
    pw = sk.world()[parent]
    wp = np.array([pw.to_world(float(x), float(y)) for x, y in points])
    seg_len = np.hypot(*np.diff(wp, axis=0).T)
    if (seg_len < 1e-3).any():
        raise ValueError("two neighbouring knots coincide")
    K = len(wp) - 1

    # ---- frames: one set per layer and part, shared by every segment
    def load(src: dict):
        with _frame_source(aep=src.get("aep", aep), comp=src.get("comp", ""), frames_dir=src.get("frames_dir", frames_dir),
                           fps=src.get("fps", fps), start_frame=None, end_frame=None, keep_frames="") as (frames, f, info):
            return [ae_bridge.read_premultiplied(fr, mode) for fr in frames], f, info

    sets, sources = {}, {}
    for L in layers:
        pms, f, info = load(L)
        h, w = pms[0].shape[:2]
        if 2 * pad >= w:
            raise ValueError(f"layer {L['name']!r}: pad={pad} leaves no piece (strip is {w} px wide)")
        ramp = end_ramp(w, pad, L.get("fade", pad))
        for p in parts:
            a, b = int(p["frames"][0]), int(p["frames"][1])
            if not 0 <= a <= b < len(pms):
                raise ValueError(f"part {p['name']!r}: frames {a}..{b} outside the {len(pms)} rendered frames")
            mf = int(L.get("loop_frames", 0)) if p.get("mode") == "loop" and L.get("loop_frames") else int(p.get("max_frames", max_frames))
            sets[(L["name"], p["name"])] = _write(project, f"{name}_{L['name']}_{p['name']}_", pms[a:b + 1], f, mode,
                                                  p.get("mode", "once"), int(L.get("max_size", max_size)), mf, ramp)
        sources[L["name"]] = info
    head_set = {}
    if head:
        pms, f, info = load(head)
        for p in parts:
            a, b = int(p["frames"][0]), int(p["frames"][1])
            head_set[p["name"]] = _write(project, f"{name}_head_{p['name']}_", pms[a:b + 1], f, mode, p.get("mode", "once"),
                                         int(head.get("max_size", max_size)), int(p.get("max_frames", max_frames)), None)

    # ---- bones: knots, then one IK-stretched segment bone per knot pair
    ctrl = []
    for i, (x, y) in enumerate(wp):
        ctrl.append(sk.add_bone_world(sk.unique_name(f"{name}_c{i}"), parent, float(x), float(y), 0.0, length=20,
                                      color="FF3F00FF").name)
    segs = []
    for i in range(K):
        d = wp[i + 1] - wp[i]
        b = sk.add_bone_world(sk.unique_name(f"{name}_s{i}"), ctrl[i], float(wp[i][0]), float(wp[i][1]),
                              math.degrees(math.atan2(d[1], d[0])), length=float(seg_len[i]), color="FFB000FF")
        segs.append(b.name)
        sk.ik.append(IkConstraint(name=sk.unique_name(f"{name}_aim{i}", "constraint"), order=_next_order(sk),
                                  bones=[b.name], target=ctrl[i + 1], mix=1, stretch=True))

    # ---- slots: per layer (back to front), per segment; alpha ramps from the tail to the head
    slots: dict[str, list[str]] = {}
    for L in layers:
        slots[L["name"]] = []
        for i in range(K):
            u = i / (K - 1) if K > 1 else 1.0
            a = (tail_alpha + (1 - tail_alpha) * u ** tail_curve) * float(L.get("alpha", 1.0))
            sname = sk.unique_name(f"{name}_{L['name']}{i}", "slot")
            sk.add_slot(Slot(name=sname, bone=segs[i], color="FFFFFF" + f"{round(a * 255):02X}",
                             blend="additive" if mode == "additive" else "normal"))
            for p in parts:
                st = sets[(L["name"], p["name"])]
                sx = seg_len[i] / (st["w"] - 2 * pad)                      # world units per strip px along
                sk.set_attachment(sname, f"{L['name']}_{p['name']}", RegionAttachment(
                    path=f"ae/{name}_{L['name']}_{p['name']}_", x=round(float(seg_len[i]) / 2, 3),
                    y=round((0.5 - baseline) * st["h"] * across_scale, 3), width=round(st["w"] * sx, 3),
                    height=round(st["h"] * across_scale, 3), sequence=Sequence(count=st["n"], start=0, digits=st["digits"])))
            slots[L["name"]].append(sname)
    head_slot = ""
    if head:
        head_slot = sk.unique_name(f"{name}_head", "slot")
        sk.add_slot(Slot(name=head_slot, bone=ctrl[-1], blend="additive" if mode == "additive" else "normal"))
        hw, hh = head.get("size", [head_set[names[0]]["w"], head_set[names[0]]["h"]])
        for p in parts:
            st = head_set[p["name"]]
            # the head comp's knot sits at its centre; scale its pixels like the pieces' thickness
            sk.set_attachment(head_slot, f"head_{p['name']}", RegionAttachment(
                path=f"ae/{name}_head_{p['name']}_", width=round(hw * across_scale, 3), height=round(hh * across_scale, 3),
                sequence=Sequence(count=st["n"], start=0, digits=st["digits"])))

    # ---- animations
    anims = {}
    for p in parts:
        pn, m = p["name"], p.get("mode", "once")
        anim = f"{name}_{pn}"
        ab = AnimBuilder(sk, anim, replace=True)
        end = 0.0
        shown = []                                                         # (slot, attachment, t0): closed at the end
        for L in layers:
            st = sets[(L["name"], pn)]
            for i, sname in enumerate(slots[L["name"]]):
                an = f"{L['name']}_{pn}"
                t0 = r(i * stagger) if pn == names[0] else 0.0             # the first part draws on piece by piece
                idx = 0 if m == "once" else (i * phase) % st["n"]          # loops run out of step
                shown.append((sname, an, t0))
                ab.sequence(sname, an, [(t0, m, idx, st["delay"])])
                end = max(end, t0 + st["dur"])
        if head:
            st = head_set[pn]
            if pn == names[0]:                                              # the head lands with the last piece
                t_in = r((K - 1) * stagger + 0.25)
                ab.slot_attachment(head_slot, [(0.0, None), (t_in, f"head_{names[1] if len(names) > 1 else pn}")])
                loop_st = head_set[names[1] if len(names) > 1 else pn]
                ab.sequence(head_slot, f"head_{names[1] if len(names) > 1 else pn}", [(t_in, "loop", 0, loop_st["delay"])])
                ab.slot_color(head_slot, [(t_in, "FFFFFF00"), (r(t_in + 0.2), "FFFFFFFF")])
            else:
                ab.slot_attachment(head_slot, [(0.0, f"head_{pn}")])
                ab.sequence(head_slot, f"head_{pn}", [(0.0, m, 0, st["delay"])])
            end = max(end, st["dur"])
        if m == "loop":                                                    # a loop lasts one cycle of its frames
            end = max(sets[(L["name"], pn)]["dur"] for L in layers)
        for sname, an, t0 in shown:                                        # the animation's length = its last key
            ab.slot_attachment(sname, ([(0.0, None)] if t0 > 0 else []) + [(t0, an), (r(end), an)])
        ab.event(0.0, f"{name}_{pn}")
        anims[pn] = {"animation": anim, "duration": round(end, 4), "mode": m}

    return {"name": name, "control_bones": ctrl, "segment_bones": segs, "slots": slots, "head_slot": head_slot,
            "animations": anims, "segment_lengths": [round(float(x), 2) for x in seg_len],
            "frame_sets": {f"{k[0]}/{k[1]}": {"frames": v["n"], "image_size": [v["tw"], v["th"]], "source_size": [v["w"], v["h"]]}
                           for k, v in sets.items()},
            "head_sets": {k: {"frames": v["n"], "image_size": [v["tw"], v["th"]]} for k, v in head_set.items()},
            "sources": sources}
