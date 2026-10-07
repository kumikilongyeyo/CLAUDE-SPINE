"""Conservative project cleanup for animator-friendly Spine files."""
from __future__ import annotations
from collections import defaultdict
from .project import Project
from .timeline import FIELDS
from .weights import decode_weighted

MODES = ("editable", "production", "runtime")

def _same(a, b, timeline: str, eps: float = 1e-6) -> bool:
    fields = FIELDS.get(timeline, ())
    return bool(fields) and all(abs(float(getattr(a,f)) - float(getattr(b,f))) <= eps for f in fields)

def _dedupe(keys, timeline: str):
    if len(keys) < 3 or timeline not in FIELDS:
        return keys, 0
    out, removed = [keys[0]], 0
    for i in range(1, len(keys)-1):
        cur, nxt = keys[i], keys[i+1]
        if cur.curve is None and _same(out[-1], cur, timeline) and _same(cur, nxt, timeline):
            removed += 1
        else:
            out.append(cur)
    out.append(keys[-1])
    return out, removed

def _cap_mesh_influences(sk, limit: int) -> dict:
    changed = vertices = max_before = 0
    for skin in sk.skins:
        for atts in skin.attachments.values():
            for att in atts.values():
                if att.type != "mesh":
                    continue
                n = len(att.uvs)//2
                if len(att.vertices) == 2*n:
                    continue
                decoded = decode_weighted(att.vertices, n)
                max_before = max(max_before, max((len(v) for v in decoded), default=0))
                if all(len(v) <= limit for v in decoded):
                    continue
                rebuilt = []
                for inf in decoded:
                    keep = sorted(inf, key=lambda x: float(x[3]), reverse=True)[:limit]
                    vertices += int(len(keep) != len(inf))
                    total = sum(max(0.0, float(x[3])) for x in keep) or 1.0
                    weights = [round(max(0.0,float(x[3]))/total, 4) for x in keep]
                    if weights:
                        weights[-1] = round(1.0 - sum(weights[:-1]), 4)
                    rebuilt.append(len(keep))
                    for (bi,x,y,_), w in zip(keep, weights):
                        rebuilt += [int(bi), float(x), float(y), float(w)]
                att.vertices = rebuilt
                changed += 1
    return {"attachments": changed, "vertices": vertices, "max_before": max_before}

def clean(project: Project, mode: str = "editable", max_influences: int = 4,
          dedupe_keys: bool = True, remove_empty_animations: bool = True) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode is one of {MODES}")
    if max_influences < 1:
        raise ValueError("max_influences must be >= 1")
    sk = project.data
    removed = 0
    touched = defaultdict(int)

    if dedupe_keys:
        for an, anim in sk.animations.items():
            for bone, tls in anim.bones.items():
                for tl, ks in list(tls.items()):
                    new, n = _dedupe(ks, tl)
                    if n:
                        tls[tl] = new
                        removed += n
                        touched[f"{an}/{bone}/{tl}"] += n

    influence = {"attachments":0,"vertices":0,"max_before":0}
    if mode in ("production","runtime"):
        influence = _cap_mesh_influences(sk, max_influences)

    empty = []
    if remove_empty_animations:
        for name in list(sk.animations):
            a = sk.animations[name]
            has = any(bool(g) for g in (a.bones,a.slots,a.ik,a.transform,a.path,a.physics,a.attachments))
            if not has and not a.events and not a.drawOrder:
                del sk.animations[name]
                empty.append(name)

    return {
        "mode": mode,
        "removed_redundant_keys": removed,
        "touched_timelines": dict(touched),
        "removed_empty_animations": empty,
        "influence_cleanup": influence,
        "policy": {
            "editable":"timeline hygiene only",
            "production":"timeline hygiene + influence cap",
            "runtime":"production-safe cleanup without destructive rig rebuilds",
        }[mode],
    }
