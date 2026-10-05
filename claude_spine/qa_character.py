"""Character QA: joint cracks, foot slide and a mobile bone budget per rig type — the ``qa_character`` tool.

All three read what the official spine-core runtime actually draws (``runtime.run(..., geometry=True)``: IK, physics
and transform constraints solved), never the Python setup maths.

**Joint cracks.** At every joint (neck, shoulders, elbows, wrists, hips, knees, ankles) the two parts that meet
there must keep the joint's core covered when the limb bends. The core is the largest disc around the joint that the
setup pose covers; each frame the joint is tracked through the posed triangles (barycentric, so it follows weighted
meshes and rigid regions alike) and points on the OUTER half of the core (the side away from the bend: the inner
side of a bend is a crease and closes naturally) are tested against the ART, not the quads: the point's triangle
gives its UV and the atlas page gives its alpha. A gap opening there is a crack (two square-ended parts rotating
apart); for a single mesh across the joint, folded triangles near the joint are reported as a fold (pinch).

**Foot slide.** A planted foot (vertices within ``tol`` of the floor in two consecutive frames) must move at the
ground speed the clip declares in its ``sfx_step`` events (float field, px/s, backward) or stand still. The drift is
the median per-frame displacement of the touching vertices minus the expected one, summed over each contact phase.

**Bone budget.** Mobile limits per rig type (:data:`RIG_BUDGETS`: biped, quadruped, flier, serpent, face) on bones,
IK, transform and physics constraints and chain depth, plus ``qa.budget(sk, "mobile_character")``. Over budget comes
back with what to cut.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import qa, runtime
from .ir import SkeletonData
from .project import Project

RIG_BUDGETS: dict[str, dict] = {
    # bones counts every helper (IK targets, carriers, look-at); physics counts constraints, not bones
    "biped":     dict(bones=64, ik=6, transform=16, physics=18, depth=14),
    "quadruped": dict(bones=80, ik=8, transform=16, physics=18, depth=14),
    "flier":     dict(bones=72, ik=4, transform=20, physics=26, depth=14),
    "serpent":   dict(bones=48, ik=2, transform=8, physics=26, depth=24),
    "face":      dict(bones=40, ik=2, transform=24, physics=8, depth=10),
}

JOINTS_BIPED = (
    # name, (parent-side part keys, first found), (child-side part keys), joint bone (its head is the joint)
    ("neck", ("torso", "neck"), ("head",), "head"),
    ("shoulder_{s}", ("torso",), ("arm_{s}", "upper_arm_{s}"), "upper_arm_{s}"),
    ("elbow_{s}", ("arm_{s}", "upper_arm_{s}"), ("arm_{s}", "lower_arm_{s}"), "lower_arm_{s}"),
    ("wrist_{s}", ("arm_{s}", "lower_arm_{s}"), ("hand_{s}",), "hand_{s}"),
    ("hip_{s}", ("pelvis", "torso"), ("leg_{s}", "thigh_{s}"), "thigh_{s}"),
    ("knee_{s}", ("leg_{s}", "thigh_{s}"), ("leg_{s}", "shin_{s}"), "shin_{s}"),
    ("ankle_{s}", ("leg_{s}", "shin_{s}"), ("foot_{s}",), "foot_{s}"),
)


# ---------------------------------------------------------------------------------------- rig type + budget
def rig_type(sk: SkeletonData) -> str:
    """biped | quadruped | flier | serpent | face, from bone-name tokens and the chain shape."""
    import re
    names = {b.name.lower() for b in sk.bones}
    toks = {t for n in names for t in re.split(r"[_\W\d]+", n) if t}
    legs = {n for n in names if re.match(r"^(thigh|leg|front_leg|back_leg|hind_leg|foreleg)", n)}
    if toks & {"hind", "foreleg", "paw", "hoof"} or len({n.rstrip("0123456789") for n in legs}) >= 4:
        return "quadruped"
    if toks & {"wing", "wings", "feather", "pinion"}:
        return "flier"
    if {"thigh_l", "thigh_r"} <= names or {"hips", "chest"} <= names:
        return "biped"
    if _max_chain(sk) >= 10 and not toks & {"arm", "leg", "thigh"}:
        return "serpent"
    if toks & {"brow", "lid", "jaw", "mouth", "eye", "lip"}:
        return "face"
    return "biped"


def _depths(sk: SkeletonData) -> dict[str, int]:
    d: dict[str, int] = {}
    for b in sk.bones:
        d[b.name] = 0 if b.parent is None else d[b.parent] + 1
    return d


def _max_chain(sk: SkeletonData) -> int:
    """Longest run of single-child bones (a tail, a spine, a tentacle)."""
    kids: dict[str, list[str]] = {}
    for b in sk.bones:
        if b.parent:
            kids.setdefault(b.parent, []).append(b.name)
    best = 0
    for b in sk.bones:
        n, cur = 1, b.name
        while len(kids.get(cur, [])) == 1:
            cur = kids[cur][0]
            n += 1
        best = max(best, n)
    return best


def bone_budget(sk: SkeletonData, kind: str = "auto") -> dict:
    """Bone / constraint counts against the mobile limits for the rig type, with what to cut when over."""
    kind = rig_type(sk) if kind == "auto" else kind
    if kind not in RIG_BUDGETS:
        raise ValueError(f"unknown rig type {kind!r}; one of {sorted(RIG_BUDGETS)} or auto")
    lim = RIG_BUDGETS[kind]
    depth = max(_depths(sk).values()) if sk.bones else 0
    m = {"bones": len(sk.bones), "ik": len(sk.ik), "transform": len(sk.transform), "physics": len(sk.physics),
         "depth": depth}
    over = {k: {"value": v, "limit": lim[k]} for k, v in m.items() if v > lim[k]}
    tips = []
    if "physics" in over or "bones" in over:
        per: dict[str, int] = {}
        for c in sk.physics:
            root = c.bone.rstrip("0123456789").rstrip("_")
            per[root] = per.get(root, 0) + 1
        long = sorted(per.items(), key=lambda kv: -kv[1])[:3]
        tips.append(f"shorten strand chains (3-4 bones read the same on a phone; physics on every bone costs a solve "
                    f"each): longest {long}")
    if "bones" in over:
        tips.append("merge spine2/spine3, drop shoulder bones on small characters, and share one IK target per "
                    "limb pair where both move together")
    if "ik" in over:
        tips.append("IK is solved every frame: keep it on the limbs that touch something (feet on the floor, hands "
                    "on props); swing the rest with keys")
    if "transform" in over:
        tips.append("collapse transform constraints that copy the same target into one constraint with several bones")
    if "depth" in over:
        tips.append("deep hierarchies update in series: parent strands to the body bone they hang from, not to "
                    "the end of another chain")
    return {"rig_type": kind, "ok": not over, "metrics": m, "limits": lim, "over_budget": over, "tips": tips}


# ---------------------------------------------------------------------------------------- geometry helpers
class _Pages:
    def __init__(self, dump: dict):
        self.alpha = {k: np.asarray(Image.open(f).convert("RGBA"), np.uint8)[..., 3]
                      for k, f in dump.get("_page_files", {}).items()}


def _arr(draw: dict):
    v = np.asarray(draw["v"], float).reshape(-1, 2)
    uv = np.asarray(draw["uv"], float).reshape(-1, 2)
    tri = np.asarray(draw["tri"], int).reshape(-1, 3)
    return v, uv, tri


def _bary(P: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray):
    """Barycentric coordinates of points P (n,2) in triangles (m,·,2) → (n, m, 3)."""
    v0, v1 = B - A, C - A
    d00 = (v0 * v0).sum(-1)
    d01 = (v0 * v1).sum(-1)
    d11 = (v1 * v1).sum(-1)
    den = d00 * d11 - d01 * d01
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    v2 = P[:, None, :] - A[None]
    d20 = (v2 * v0[None]).sum(-1)
    d21 = (v2 * v1[None]).sum(-1)
    b1 = (d11[None] * d20 - d01[None] * d21) / den[None]
    b2 = (d00[None] * d21 - d01[None] * d20) / den[None]
    return np.stack([1 - b1 - b2, b1, b2], -1)


def _covered(P: np.ndarray, draw: dict, pages: _Pages, thr: int = 128) -> np.ndarray:
    """Whether each point lands on opaque ART of this slot (alpha through the posed triangle's UVs)."""
    if draw is None or len(P) == 0:
        return np.zeros(len(P), bool)
    v, uv, tri = _arr(draw)
    page = pages.alpha.get(draw.get("page"))
    if page is None or not len(tri):
        return np.zeros(len(P), bool)
    bc = _bary(P, v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]])
    inside = (bc >= -1e-6).all(-1)
    out = np.zeros(len(P), bool)
    PH, PW = page.shape
    for i in range(len(P)):
        ks = np.nonzero(inside[i])[0]
        for k in ks:
            u = bc[i, k] @ uv[tri[k]]
            x, y = int(min(max(u[0] * PW, 0), PW - 1)), int(min(max(u[1] * PH, 0), PH - 1))
            if page[y, x] >= thr:
                out[i] = True
                break
    return out


def _anchor(draw: dict, J: np.ndarray):
    """(triangle index, barycentric) of J in a slot's triangles: the containing one, else the nearest."""
    v, _, tri = _arr(draw)
    bc = _bary(J[None], v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]])[0]
    inside = (bc >= -1e-6).all(-1)
    if inside.any():
        k = int(np.nonzero(inside)[0][0])
    else:
        c = v[tri].mean(1)
        k = int(np.argmin(np.hypot(*(c - J).T)))
    return k, bc[k]


def _track(draw: dict, anchor) -> np.ndarray:
    v, _, tri = _arr(draw)
    k, b = anchor
    if k >= len(tri):
        return None
    return b @ v[tri[k]]


def _by_slot(frame_draws: list[dict]) -> dict[str, dict]:
    return {d["slot"]: d for d in frame_draws}


def _ring(J, r, n=24):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[J[0] + r * np.cos(a), J[1] + r * np.sin(a)]


# ---------------------------------------------------------------------------------------- joint cracks
def biped_joints(project: Project) -> list[dict]:
    """The joints of a rig_biped rig: [{"name", "a", "b", "bone"}] (a == b for one mesh across the joint)."""
    from .rig_body import find_parts
    sk = project.data
    parts = find_parts(sk)
    out = []
    for name, pa, pb, bone in JOINTS_BIPED:
        for s in ("l", "r") if "{s}" in name else (None,):
            fm = (lambda x: x.format(s=s)) if s else (lambda x: x)
            a = next((parts[fm(k)] for k in pa if fm(k) in parts), None)
            b = next((parts[fm(k)] for k in pb if fm(k) in parts), None)
            bn = fm(bone)
            if a and b and sk.has_bone(bn):
                out.append({"name": fm(name), "a": a, "b": b, "bone": bn})
    return out


def _core_radius(J, da, db, pages, r_max: float) -> float:
    best = 0.0
    for r in np.linspace(1.0, r_max, 40):
        P = _ring(J, r, 32)
        cov = _covered(P, da, pages) | _covered(P, db, pages)
        if cov.mean() < 0.98:
            break
        best = r
    return 0.85 * best


def joint_cracks(project: Project, dump: dict, joints: list[dict] | None = None, threshold: float = 0.08,
                 animations: list[str] | None = None) -> list[dict]:
    """Per joint and animation: the worst fraction of the joint core's outer half that opens up (crack) and the
    number of folded triangles near the joint (fold). ``threshold``: crack fraction that fails."""
    sk = project.data
    joints = joints if joints is not None else biped_joints(project)
    pages = _Pages(dump)
    w = sk.world()
    setup = _by_slot(dump["setup"]["draws"])
    res = []
    for jd in joints:
        da0, db0 = setup.get(jd["a"]), setup.get(jd["b"])
        if da0 is None or db0 is None:
            continue
        J0 = np.array(w[jd["bone"]].head, float) if isinstance(jd.get("bone"), str) else np.asarray(jd["at"], float)
        r_max = 0.25 * max(np.ptp(np.asarray(da0["v"]).reshape(-1, 2), 0).max(), 1.0) + 40
        R = _core_radius(J0, da0, db0, pages, r_max)
        if R < 2.0:
            res.append({"joint": jd["name"], "skipped": "the setup pose does not cover the joint"})
            continue
        anc = [(nm, _anchor(setup[nm], J0)) for nm in {jd["a"], jd["b"]}]
        # vertex groups for the bend direction: setup vertices near the joint, split by side of the joint
        child_dir = np.array([w[jd["bone"]].a, w[jd["bone"]].c]) if isinstance(jd.get("bone"), str) else None
        groups = {}
        for nm in {jd["a"], jd["b"]}:
            v0 = _arr(setup[nm])[0]
            near = np.hypot(*(v0 - J0).T) < 3.0 * R
            if jd["a"] == jd["b"] and child_dir is not None:
                side = (v0 - J0) @ child_dir
                groups["a"] = (nm, near & (side < 0))
                groups["b"] = (nm, near & (side >= 0))
            else:
                groups["a" if nm == jd["a"] else "b"] = (nm, near)
        tri_sign0 = _tri_signs(setup[jd["a"]], J0, 2.5 * R) if jd["a"] == jd["b"] else None
        base = _outer_open(J0, setup, jd, groups, R, pages, straight_ok=True)
        for an in animations or list(dump["animations"]):
            worst, wt, folds = 0.0, None, 0
            for fr in dump["animations"][an]["frames"]:
                ds = _by_slot(fr["draws"])
                if jd["a"] not in ds or jd["b"] not in ds:
                    continue
                pts = [_track(ds[nm], a) for nm, a in anc]
                pts = [p for p in pts if p is not None]
                if not pts:
                    continue
                J = np.mean(pts, 0)
                op = _outer_open(J, ds, jd, groups, R, pages)
                crack = max(0.0, op - base)
                if crack > worst:
                    worst, wt = crack, fr["t"]
                if tri_sign0 is not None:
                    sg = _tri_signs(ds[jd["a"]], None, None, idx=tri_sign0[1])
                    folds = max(folds, int((sg != tri_sign0[0]).sum()))
            # a fold or two in the crease of a deep bend is what linear skinning does and stays hidden in the crease
            fold_ok = folds <= max(2, int(0.06 * len(tri_sign0[1]))) if tri_sign0 is not None else True
            item = {"joint": jd["name"], "animation": an, "crack": round(worst, 3), "at": wt,
                    "core_radius": round(float(R), 2), "single_mesh": jd["a"] == jd["b"],
                    "ok": worst <= threshold and fold_ok}
            if folds:
                item["folded_triangles"] = folds
            res.append(item)
    return res


def _tri_signs(draw: dict, J, radius, idx=None):
    v, _, tri = _arr(draw)
    if idx is None:
        c = v[tri].mean(1)
        idx = np.nonzero(np.hypot(*(c - J).T) < radius)[0]
    T = tri[idx]
    a, b, c_ = v[T[:, 0]], v[T[:, 1]], v[T[:, 2]]
    cr = (b[:, 0] - a[:, 0]) * (c_[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c_[:, 0] - a[:, 0])
    sg = np.sign(np.where(np.abs(cr) < 1e-6, 0, cr))
    return (sg, idx) if J is not None else sg


def _outer_open(J, ds, jd, groups, R, pages, straight_ok: bool = False) -> float:
    """Fraction of the outer half of the joint core (radii .3/.55/.8 R) that is not on art. Straight joints test
    both sides and report the worse."""
    cents = []
    for g in ("a", "b"):
        nm, mask = groups[g]
        v = _arr(ds[nm])[0]
        if mask.sum() == 0 or len(v) != len(mask):
            return 0.0
        cents.append(v[mask].mean(0) - J)
    ua, ub = (c / max(np.hypot(*c), 1e-9) for c in cents)
    bis = ua + ub
    if np.hypot(*bis) < 0.25:
        perp = np.array([-ua[1], ua[0]])
        dirs = [perp, -perp]
    else:
        dirs = [-bis / np.hypot(*bis)]
    da, db = ds.get(jd["a"]), ds.get(jd["b"])
    worst = 0.0
    for o in dirs:
        base = math.atan2(o[1], o[0])
        angs = base + np.radians(np.linspace(-70, 70, 9))
        P = np.vstack([np.c_[J[0] + r * R * np.cos(angs), J[1] + r * R * np.sin(angs)] for r in (0.3, 0.55, 0.8)])
        cov = _covered(P, da, pages) | _covered(P, db, pages)
        worst = max(worst, 1.0 - float(cov.mean()))
    return worst


# ---------------------------------------------------------------------------------------- foot slide
def _feet(project: Project) -> dict[str, str]:
    from .rig_body import find_parts
    parts = find_parts(project.data)
    out = {}
    for s in ("l", "r"):
        for k in (f"foot_{s}", f"leg_{s}", f"shin_{s}"):
            if k in parts:
                out[f"foot_{s}"] = parts[k]
                break
    return out


def _is_loop(sk: SkeletonData, anim: str, frames) -> bool:
    from .rig_body import CHARACTER_CLIPS
    if anim in CHARACTER_CLIPS:
        return CHARACTER_CLIPS[anim]["loop"]
    if anim == "breathe":
        return True
    if len(frames) < 3:
        return False
    a, b = frames[0]["draws"], frames[-1]["draws"]
    return len(a) == len(b) and all(np.allclose(x["v"], y["v"], atol=0.05) for x, y in zip(a, b))


def _ground_speed(sk: SkeletonData, anim: str) -> float:
    a = sk.animations.get(anim)
    if a is None:
        return 0.0
    for e in a.events:
        if e.name == "sfx_step":
            return float((e.model_extra or {}).get("float", 0.0) or 0.0)
    return 0.0


def foot_slide(project: Project, dump: dict, feet: dict[str, str] | None = None, tol: float | None = None,
               slide_tol: float | None = None, facing: int | None = None, animations: list[str] | None = None) -> list[dict]:
    """Per animation and foot: contact phases and how far the planted foot drifted from the ground speed."""
    from .rig_body import _facing
    sk = project.data
    feet = feet if feet is not None else _feet(project)
    f = facing if facing is not None else _facing(sk)
    setup = _by_slot(dump["setup"]["draws"])
    allv = np.vstack([_arr(d)[0] for d in dump["setup"]["draws"]]) if dump["setup"]["draws"] else np.zeros((1, 2))
    H = float(np.ptp(allv[:, 1])) or 100.0
    tol = tol if tol is not None else 0.5 + 0.002 * H
    slide_tol = slide_tol if slide_tol is not None else max(1.0, 0.003 * H)
    out = []
    for foot, slot in feet.items():
        if slot not in setup:
            continue
        floor = float(_arr(setup[slot])[0][:, 1].min())
        for an in animations or list(dump["animations"]):
            v_g = _ground_speed(sk, an)
            frames = dump["animations"][an]["frames"]
            loop = _is_loop(sk, an, frames)
            if loop and len(frames) > 2:
                frames = frames[:-1]                     # the last frame repeats the first
            phases, cur = [], None
            sink = 0.0
            V = []
            for fr in frames:
                d = _by_slot(fr["draws"]).get(slot)
                V.append(None if d is None else _arr(d)[0])
            for i in range(len(frames) - 1):
                v0, v1 = V[i], V[i + 1]
                if v0 is None or v1 is None or len(v0) != len(v1):
                    continue
                sink = max(sink, floor - float(v0[:, 1].min()))
                # planted = on the floor for 4 frames in a row; the touch-down and lift-off pairs are transitions
                touch = (v0[:, 1] <= floor + tol) & (v1[:, 1] <= floor + tol)
                for j in (i - 1, i + 2):
                    vj = V[j] if 0 <= j < len(V) else (V[j % len(V)] if loop else None)
                    if vj is None or len(vj) != len(v0):
                        touch &= False
                    else:
                        touch &= vj[:, 1] <= floor + tol
                dt = frames[i + 1]["t"] - frames[i]["t"]
                if touch.any() and dt > 0:
                    dx = float(np.median(v1[touch, 0] - v0[touch, 0]))
                    dy = float(np.median(v1[touch, 1] - v0[touch, 1]))
                    err = math.hypot(dx - (-f * v_g * dt), dy)
                    if cur is None:
                        cur = {"t0": frames[i]["t"], "t1": frames[i + 1]["t"], "drift": 0.0, "max_step": 0.0}
                    cur["t1"] = frames[i + 1]["t"]
                    cur["drift"] += err
                    cur["max_step"] = max(cur["max_step"], err)
                elif cur is not None:
                    phases.append(cur)
                    cur = None
            if cur is not None:
                phases.append(cur)
            worst = max((p["drift"] for p in phases), default=0.0)
            out.append({"foot": foot, "slot": slot, "animation": an, "ground_speed": v_g,
                        "phases": [{k: round(v, 3) for k, v in p.items()} for p in phases],
                        "max_drift": round(worst, 3), "sinks": round(max(0.0, sink - tol), 3),
                        "ok": worst <= slide_tol and sink <= 2 * tol})
    return out


# ---------------------------------------------------------------------------------------- the report
def qa_character(project: Project, animations: list[str] | None = None, kind: str = "auto", fps: float = 30,
                 dump: dict | None = None, joints: list[dict] | None = None, feet: dict[str, str] | None = None,
                 crack_threshold: float = 0.08) -> dict:
    """Joint cracks, foot slide and the bone budget, played in spine-core; returns what to fix."""
    sk = project.data
    if dump is None:
        if not runtime.available():
            raise RuntimeError("qa_character plays the clips in spine-core: install Node 18+")
        dump = runtime.run(project, animations=animations, fps=fps, geometry=True)
        if not dump.get("ok", False) and dump.get("error"):
            return {"ok": False, "error": dump["error"]}
    anims = animations or list(dump["animations"])
    cracks = joint_cracks(project, dump, joints, crack_threshold, anims)
    slides = foot_slide(project, dump, feet, animations=anims)
    bb = bone_budget(sk, kind)
    mob = qa.budget(sk, "mobile_character")
    fixes = []
    for c in cracks:
        if c.get("ok", True):
            continue
        if c.get("folded_triangles"):
            fixes.append(f"{c['joint']} folds {c['folded_triangles']} triangles in {c['animation']}: the bend is past "
                         "what linear skinning holds; widen the weights there (rig_mesh smooth=1.5) or cap the bend")
        else:
            fixes.append(f"{c['joint']} cracks in {c['animation']} at t={c['at']} ({c['crack']:.0%} of the joint core "
                         "opens): weight both parts across the joint (rig_mesh bones=[parent, child]) or give them round, "
                         "overlapping ends centred on the pivot")
    for s in slides:
        if not s["ok"]:
            if s["max_drift"] > 0:
                fixes.append(f"{s['foot']} slides {s['max_drift']:.1f} px in {s['animation']}: a planted foot must move "
                             f"at exactly the ground speed ({s['ground_speed']} px/s back) or stay still; key the IK "
                             "target on the treadmill (clip_set walk/run do) and keep the hips low enough that the leg "
                             "never locks")
            if s["sinks"] > 0:
                fixes.append(f"{s['foot']} sinks {s['sinks']:.1f} px under the floor in {s['animation']}")
    fixes += [f"budget ({bb['rig_type']}): {k} {v['value']} > {v['limit']}" for k, v in bb["over_budget"].items()]
    fixes += bb["tips"]
    fixes += [f"mobile_character: {k} {v['value']} > {v['limit']}" for k, v in mob["over_budget"].items()]
    ok = all(c.get("ok", True) for c in cracks) and all(s["ok"] for s in slides) and bb["ok"]
    return {"ok": ok, "cracks": [c for c in cracks if not c.get("ok", True)] or [],
            "joints_checked": sorted({c["joint"] for c in cracks}), "worst_crack": max((c.get("crack", 0) for c in cracks), default=0),
            "foot_slide": [s for s in slides if not s["ok"]],
            "worst_slide": max((s["max_drift"] for s in slides), default=0.0),
            "feet_checked": sorted({s["foot"] for s in slides}), "budget": bb,
            "mobile_character": {"ok": mob["ok"], "metrics": mob["metrics"], "over_budget": mob["over_budget"]},
            "fix": fixes, "animations": anims, "_all_cracks": cracks, "_all_slides": slides}
