"""Fewer draw calls with the same picture: regroup the draw order, proven on the runtime's own geometry.

spine-webgl / spine-pixi flush the batch whenever the blend mode or the atlas page changes along the draw order. FX
skeletons interleave additive light with normal art (aura behind, coin, face glow, aura front), so they pay a call
per switch. Two slots may swap places without changing a single pixel when
  * both are additive (additive light adds, and addition commutes), or
  * they never overlap on screen in any frame where both are drawn (checked on the runtime's vertices).
``optimize`` moves slots only across such neighbours, greedily, keeping a move only when it lowers the real number of
calls summed over every frame of every animation. Clipping slots and the slots inside a clipping range stay put, and
skeletons with draw-order keys are left alone. It then renders sample frames before and after with the same atlas and
reports the largest pixel difference (and keeps the old order if anything moved by more than 2/255).
"""
from __future__ import annotations

import numpy as np

from . import render, runtime
from .ir import ClippingAttachment
from .project import Project


def _atlas(project: Project, group: bool, work) -> str:
    from .atlas import pack
    return pack(project, out_dir=work, name=project.name, pma=False, group=group)["atlas"]


def _frames(project: Project, animations: list[str], fps: float, atlas: str | None = None) -> tuple[list, dict]:
    dump = runtime.run(project, atlas_path=atlas, animations=animations, fps=fps, geometry=True)
    if not dump.get("ok", True) and dump.get("error"):
        raise RuntimeError(dump["error"])
    out = []
    for a in animations:
        for f in dump["animations"][a]["frames"]:
            draws = []
            for d in f["draws"]:
                v = np.asarray(d["v"], float).reshape(-1, 2)
                draws.append((d["slot"], d.get("blend", "normal"), d.get("page"),
                              (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())))
            out.append(draws)
    return out, dump


def calls(order: list[str], frames: list) -> list[int]:
    """Real draw calls per frame for a slot order: runs of (blend, page) among the slots actually drawn."""
    pos = {s: i for i, s in enumerate(order)}
    res = []
    for draws in frames:
        ks = [(b, p) for s, b, p, _ in sorted(draws, key=lambda d: pos[d[0]])]
        res.append(sum(1 for i, k in enumerate(ks) if i == 0 or k != ks[i - 1]))
    return res


def _overlaps(frames: list, margin: float = 1.0) -> set:
    pairs = set()
    for draws in frames:
        for i in range(len(draws)):
            si, _, _, a = draws[i]
            for j in range(i + 1, len(draws)):
                sj, _, _, b = draws[j]
                if si != sj and a[0] - margin < b[2] and b[0] - margin < a[2] and a[1] - margin < b[3] and b[1] - margin < a[3]:
                    pairs.add((si, sj))
                    pairs.add((sj, si))
    return pairs


def _pinned(project: Project) -> set:
    """Clipping slots and everything between a clip and its end slot."""
    sk = project.data
    names = [s.name for s in sk.slots]
    pinned = set()
    for skin in sk.skins:
        for slot, atts in skin.attachments.items():
            for a in atts.values():
                if isinstance(a, ClippingAttachment):
                    i = names.index(slot)
                    j = names.index(a.end) if a.end in names else len(names) - 1
                    pinned.update(names[i:j + 1])
    return pinned


def optimize(project: Project, animations: list[str] | None = None, fps: float = 15, apply: bool = True,
             max_moves: int = 200, group_pages: bool | None = None) -> dict:
    """group_pages None (auto): try the plain packing and the grouped one (pack_atlas group_sequences=True) and
    keep whichever ends with fewer calls (mean over frames, then max): measured on the coin, grouping cut a
    three-coin loop from 8.1 to 5.1 mean calls but raised a one-coin idle from 5.2 to 6.9. Export with the
    packing the result names (group_sequences)."""
    if group_pages is None:
        tries = [optimize(project, animations, fps, False, max_moves, g) for g in (False, True)]
        ok = [t for t in tries if "calls_after" in t]
        if not ok:
            return tries[0]
        best = min(ok, key=lambda t: (t["calls_after"]["mean"], t["calls_after"]["max"]))
        res = optimize(project, animations, fps, apply, max_moves, best["group_pages"]) if apply else best
        res["compared"] = {("grouped" if t["group_pages"] else "plain"): t.get("calls_after") for t in ok}
        res["pack_atlas_group_sequences"] = best["group_pages"]
        return res
    import tempfile
    sk = project.data
    anims = animations or list(sk.animations)
    if any(sk.animations[a].drawOrder for a in anims):
        return {"applied": False, "reason": "an animation keys the draw order; reordering slots would change it"}
    work = tempfile.mkdtemp(prefix="claude-spine-order-")
    atlas = _atlas(project, group_pages, work)
    frames, dump = _frames(project, anims, fps, atlas)
    order = [s.name for s in sk.slots]
    blend = {s.name: s.blend for s in sk.slots}
    over = _overlaps(frames)
    pinned = _pinned(project)

    def commutes(a: str, b: str) -> bool:
        return (blend[a] == "additive" and blend[b] == "additive") or (a, b) not in over

    before = calls(order, frames)
    cost = sum(before)
    moves = []
    for _ in range(max_moves):
        best = None
        for i, x in enumerate(order):
            if x in pinned:
                continue
            for j in range(len(order)):
                if j in (i, i + 1):
                    continue
                lo, hi = (j, i) if j < i else (i + 1, j)
                between = order[lo:hi]
                if any(y in pinned for y in between) or not all(commutes(x, y) for y in between):
                    continue
                cand = order[:i] + order[i + 1:]
                cand.insert(j if j < i else j - 1, x)
                c = sum(calls(cand, frames))
                if c < cost and (best is None or c < best[0]):
                    best = (c, cand, x, order[j] if j < len(order) else "<end>")
        if best is None:
            break
        cost, order, x, nxt = best
        moves.append({"slot": x, "before": nxt})
    after = calls(order, frames)
    res = {"animations": anims, "frames": len(frames), "moves": moves, "group_pages": group_pages,
           "calls_before": {"max": max(before), "mean": round(float(np.mean(before)), 2)},
           "calls_after": {"max": max(after), "mean": round(float(np.mean(after)), 2)}, "applied": False}
    if not moves:
        res["reason"] = "no legal move lowers the calls"     # the packing choice (group_pages) still stands
        return res
    # proof: render sample frames with the old and the new order on the SAME atlas, compare pixels
    old = list(sk.slots)
    by = {s.name: s for s in sk.slots}
    pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
    sk.slots = [by[n] for n in order]          # the atlas packs the same images the same way: same pages
    new_frames_dump = runtime.run(project, atlas_path=atlas, animations=anims, fps=fps, geometry=True)
    sk.slots = old
    pages2 = render._Pages(new_frames_dump["_page_files"], new_frames_dump.get("_pma", False))
    worst = 0.0
    for a in anims:
        fa, fb = dump["animations"][a]["frames"], new_frames_dump["animations"][a]["frames"]
        view = render.union_bounds(dump, [a])
        for k in np.linspace(0, len(fa) - 1, min(len(fa), 8)).round().astype(int):
            ia = np.asarray(render.render_frame(fa[k]["draws"], pages, view, (320, 320), (20, 20, 24, 255)), np.float32)
            ib = np.asarray(render.render_frame(fb[k]["draws"], pages2, view, (320, 320), (20, 20, 24, 255)), np.float32)
            worst = max(worst, float(np.abs(ia - ib).max()))
    res["pixel_max_diff"] = round(worst, 1)
    if worst > 2.0:
        res["reason"] = f"rendered frames changed by up to {worst:.0f}/255: kept the old order"
        return res
    if apply:
        sk.slots = [by[n] for n in order]
        res["applied"] = True
    return res
