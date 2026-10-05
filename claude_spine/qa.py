"""Validation and performance budgets — the ``qa_budget`` / ``validate`` tools.

``validate`` catches what makes a skeleton fail to load or render wrong:
dangling references, bad weights, broken triangulations, UVs outside 0..1
(the editor clamps them and the texture shifts), timelines on missing bones,
unsorted keys, curve arrays of the wrong length, undefined events.

``budget`` estimates what a skeleton costs on a phone and compares it to a
profile. The number that surprises people is **draw calls**: a batch breaks
every time the blend mode or atlas page changes along the draw order, and
every clipping attachment adds its own cost (spine-webgl and spine-pixi both
flush on a blend change). An additive glow sandwiched between normal parts
costs two extra batches; moving it next to the other additive slots costs none.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from .geometry import triangulation_ok
from .ir import (BoundingBoxAttachment, ClippingAttachment, Key, LinkedMeshAttachment, MeshAttachment,
                 PathAttachment, RegionAttachment, SkeletonData)
from .weights import decode_weighted

PROFILES = {
    # one symbol of many on a reel grid (mobile web, 3x5 = 15 visible)
    "mobile_symbol": dict(bones=40, slots=30, vertices=600, weighted_vertices=400, clipping=1, draw_calls=3,
                          atlas_pages=1, atlas_page_px=1024, physics=6, deform_keys=0, max_influences=4),
    # a big-win banner / feature intro: one at a time, full screen
    "mobile_banner": dict(bones=120, slots=80, vertices=2500, weighted_vertices=1800, clipping=2, draw_calls=6,
                          atlas_pages=2, atlas_page_px=2048, physics=16, deform_keys=4, max_influences=4),
    # a hero character / mascot on screen with the reels
    "mobile_character": dict(bones=90, slots=60, vertices=2000, weighted_vertices=1500, clipping=1, draw_calls=4,
                             atlas_pages=1, atlas_page_px=2048, physics=20, deform_keys=2, max_influences=4),
    "desktop": dict(bones=250, slots=150, vertices=8000, weighted_vertices=6000, clipping=4, draw_calls=12,
                    atlas_pages=4, atlas_page_px=4096, physics=40, deform_keys=20, max_influences=4),
}

CURVE_VALUES = {"rotate": 1, "translatex": 1, "translatey": 1, "scalex": 1, "scaley": 1, "shearx": 1, "sheary": 1,
                "translate": 2, "scale": 2, "shear": 2, "alpha": 1, "rgba": 4, "rgb": 3, "rgba2": 7, "rgb2": 6}


def _mesh_n(att: MeshAttachment) -> int:
    return len(att.uvs) // 2


def validate(sk: SkeletonData) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    bones = {b.name for b in sk.bones}
    slots = {s.name for s in sk.slots}
    seen = set()
    for i, b in enumerate(sk.bones):
        if i == 0 and b.parent is not None:
            errors.append(f"first bone {b.name!r} must be the parentless root")
        if i > 0 and b.parent is None:
            errors.append(f"bone {b.name!r} has no parent (only the first bone may)")
        if b.parent is not None and b.parent not in seen:
            errors.append(f"bone {b.name!r} comes before its parent {b.parent!r}")
        if b.name in seen:
            errors.append(f"duplicate bone {b.name!r}")
        seen.add(b.name)
    sseen = set()
    for s in sk.slots:
        if s.bone not in bones:
            errors.append(f"slot {s.name!r} uses missing bone {s.bone!r}")
        if s.name in sseen:
            errors.append(f"duplicate slot {s.name!r}")
        sseen.add(s.name)
    cnames = Counter(c.name for c in [*sk.ik, *sk.transform, *sk.physics])
    for n, c in cnames.items():
        if c > 1:
            errors.append(f"constraint name {n!r} used {c} times")
    for c in sk.ik:
        for b in [*c.bones, c.target]:
            if b not in bones:
                errors.append(f"ik {c.name!r} references missing bone {b!r}")
        if c.target in c.bones:
            errors.append(f"ik {c.name!r} targets one of its own bones")
    for c in sk.transform:
        for b in [*c.bones, c.target]:
            if b not in bones:
                errors.append(f"transform {c.name!r} references missing bone {b!r}")
    for c in sk.physics:
        if c.bone not in bones:
            errors.append(f"physics {c.name!r} references missing bone {c.bone!r}")
        if c.mass <= 0:
            errors.append(f"physics {c.name!r} has mass {c.mass} (must be > 0)")

    att_names: dict[tuple[str, str], object] = {}
    for skin in sk.skins:
        for slot, atts in skin.attachments.items():
            if slot not in slots:
                errors.append(f"skin {skin.name!r} has attachments for missing slot {slot!r}")
            for an, att in atts.items():
                att_names[(slot, an)] = att
                where = f"{skin.name}/{slot}/{an}"
                if isinstance(att, MeshAttachment):
                    _check_mesh(att, where, len(sk.bones), errors, warnings)
                elif isinstance(att, ClippingAttachment):
                    if len(att.vertices) != 2 * att.vertexCount:
                        if not _weighted_len_ok(att.vertices, att.vertexCount, len(sk.bones)):
                            errors.append(f"{where}: clipping vertexCount {att.vertexCount} does not match vertices")
                    if att.end and att.end not in slots:
                        errors.append(f"{where}: clipping ends at missing slot {att.end!r}")
                    if att.vertexCount > 16:
                        warnings.append(f"{where}: clipping polygon has {att.vertexCount} vertices; clipping cost grows with it (aim ≤ 8–16)")
                elif isinstance(att, LinkedMeshAttachment):
                    if att.parent not in atts and not any(att.parent in s.attachments.get(slot, {}) for s in sk.skins):
                        errors.append(f"{where}: linked mesh parent {att.parent!r} not found")
    for s in sk.slots:
        if s.attachment and (s.name, s.attachment) not in att_names:
            errors.append(f"slot {s.name!r} setup attachment {s.attachment!r} is not in any skin")

    for an, a in sk.animations.items():
        for bn, tls in a.bones.items():
            if bn not in bones:
                errors.append(f"animation {an!r} keys missing bone {bn!r}")
            for tl, ks in tls.items():
                _check_keys(ks, f"{an}/bones/{bn}/{tl}", CURVE_VALUES.get(tl), errors)
        for sn, tls in a.slots.items():
            if sn not in slots:
                errors.append(f"animation {an!r} keys missing slot {sn!r}")
            for tl, ks in tls.items():
                _check_keys(ks, f"{an}/slots/{sn}/{tl}", CURVE_VALUES.get(tl), errors)
                if tl == "attachment":
                    for k in ks:
                        nm = (k.model_extra or {}).get("name")
                        if nm is not None and (sn, nm) not in att_names:
                            errors.append(f"{an}/slots/{sn}: attachment key names unknown attachment {nm!r}")
        for cn in a.ik:
            if cn not in {c.name for c in sk.ik}:
                errors.append(f"animation {an!r} keys missing ik constraint {cn!r}")
        for cn in a.transform:
            if cn not in {c.name for c in sk.transform}:
                errors.append(f"animation {an!r} keys missing transform constraint {cn!r}")
        for e in a.events:
            if e.name not in sk.events:
                errors.append(f"animation {an!r} fires undefined event {e.name!r}")
        for d in a.drawOrder:
            for o in d.offsets or []:
                if o.slot not in slots:
                    errors.append(f"animation {an!r} draw order moves missing slot {o.slot!r}")
                else:
                    j = sk.slot_index(o.slot) + o.offset
                    if not 0 <= j < len(sk.slots):
                        errors.append(f"animation {an!r} draw order moves {o.slot!r} out of range")
        for skn, slots_ in a.attachments.items():
            for sn, atts in slots_.items():
                for atn, tls in atts.items():
                    att = att_names.get((sn, atn))
                    if att is None:
                        errors.append(f"animation {an!r} deforms/sequences unknown attachment {sn}/{atn}")
                        continue
                    for k in tls.get("deform", []):
                        ex = k.model_extra or {}
                        if isinstance(att, MeshAttachment) and "vertices" in ex:
                            n = _mesh_n(att)
                            w = len(att.vertices) != 2 * n
                            size = 2 * sum(int(c) for c in [len(v) for v in decode_weighted(att.vertices, n)]) if w else 2 * n
                            if ex.get("offset", 0) + len(ex["vertices"]) > size:
                                errors.append(f"{an}/deform/{sn}/{atn}: deform key longer than the mesh")
                                break
        if a.duration() == 0 and not (a.events or a.drawOrder):
            warnings.append(f"animation {an!r} has no keys after time 0 (duration 0)")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _weighted_len_ok(v, n, nb) -> bool:
    try:
        inf = decode_weighted(v, n)
    except (ValueError, IndexError):
        return False
    return all(0 <= bi < nb for vtx in inf for bi, *_ in vtx)


def _check_mesh(att: MeshAttachment, where: str, n_bones: int, errors: list[str], warnings: list[str]) -> None:
    n = _mesh_n(att)
    if len(att.uvs) % 2:
        errors.append(f"{where}: odd uv count")
        return
    if att.hull < 3 or att.hull > n:
        errors.append(f"{where}: hull {att.hull} invalid for {n} vertices")
    if len(att.triangles) % 3:
        errors.append(f"{where}: triangle index count not a multiple of 3")
    if att.triangles and (max(att.triangles) >= n or min(att.triangles) < 0):
        errors.append(f"{where}: triangle index out of range")
    uv = np.asarray(att.uvs)
    if (uv < -1e-6).any() or (uv > 1 + 1e-6).any():
        errors.append(f"{where}: uvs outside 0..1 (the editor clamps them; texture shifts)")
    weighted = len(att.vertices) != 2 * n
    if weighted:
        try:
            inf = decode_weighted(att.vertices, n)
        except (ValueError, IndexError) as e:
            errors.append(f"{where}: weighted vertices malformed ({e})")
            return
        for i, vtx in enumerate(inf):
            s = sum(w for *_, w in vtx)
            if abs(s - 1) > 2e-3:
                errors.append(f"{where}: vertex {i} weights sum to {s:.4f}")
                break
            if any(not 0 <= bi < n_bones for bi, *_ in vtx):
                errors.append(f"{where}: vertex {i} uses a bone index out of range")
                break
        mx = max(len(v) for v in inf)
        if mx > 4:
            warnings.append(f"{where}: up to {mx} bone influences per vertex (4 is the usual budget)")
        pts_uv = uv.reshape(-1, 2)
    else:
        pts_uv = uv.reshape(-1, 2)
    if att.triangles and att.width and att.height:
        P = pts_uv * [att.width, att.height]
        ok, why = triangulation_ok(P, att.hull, np.asarray(att.triangles).reshape(-1, 3))
        if not ok:
            warnings.append(f"{where}: triangulation check: {why}")


def _check_keys(ks: list[Key], where: str, nvals: int | None, errors: list[str]) -> None:
    last = -1.0
    for k in ks:
        if k.time < last - 1e-9:
            errors.append(f"{where}: keys out of time order")
            break
        last = k.time
        if isinstance(k.curve, list) and nvals and len(k.curve) != 4 * nvals:
            errors.append(f"{where}: curve has {len(k.curve)} numbers, expected {4 * nvals}")
            break


# ------------------------------------------------------------------------ budget
def budget(sk: SkeletonData, profile: str = "mobile_symbol", atlas: dict | None = None,
           page_sizes: list[tuple[int, int]] | None = None, region_pages: dict[str, str] | None = None) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; one of {sorted(PROFILES)}")
    lim = PROFILES[profile]
    verts = weighted = clip = 0
    max_inf = 1
    per_slot = {}
    for s in sk.slots:
        if not s.attachment:
            continue
        att = None
        for skin in sk.skins:
            att = skin.attachments.get(s.name, {}).get(s.attachment) or att
        if att is None:
            continue
        if isinstance(att, MeshAttachment):
            n = _mesh_n(att)
            verts += n
            per_slot[s.name] = n
            if len(att.vertices) != 2 * n:
                weighted += n
                try:
                    max_inf = max(max_inf, max(len(v) for v in decode_weighted(att.vertices, n)))
                except (ValueError, IndexError):
                    pass
        elif isinstance(att, RegionAttachment):
            verts += 4
            per_slot[s.name] = 4
    # FX slots are hidden in setup but shown by animations: count their largest attachment
    anim_verts = 0
    for s in sk.slots:
        if s.attachment:
            continue
        best = 0
        for skin in sk.skins:
            for att in skin.attachments.get(s.name, {}).values():
                best = max(best, 4 if isinstance(att, RegionAttachment) else
                           (_mesh_n(att) if isinstance(att, MeshAttachment) else 0))
        anim_verts += best
    for skin in sk.skins:
        for atts in skin.attachments.values():
            clip += sum(isinstance(a, ClippingAttachment) for a in atts.values())

    # draw-call estimate over the full draw order (assuming every slot visible)
    calls, breaks = 0, []
    prev = None
    for s in sk.slots:
        has = False
        page = None
        for skin in sk.skins:
            atts = skin.attachments.get(s.name, {})
            for an, a in atts.items():
                if isinstance(a, (RegionAttachment, MeshAttachment)):
                    has = True
                    if region_pages:
                        page = region_pages.get(getattr(a, "path", None) or an)
                    break
        if not has:
            continue
        # spine-webgl and spine-pixi set the blend func per slot and flush the
        # batch whenever it (or the texture page) changes
        batch_key = (s.blend, page)
        if prev is None or batch_key != prev[1]:
            calls += 1
            if prev is not None:
                breaks.append(f"{prev[0]} → {s.name} ({batch_key[0]}{', page ' + str(page) if page else ''})")
        prev = (s.name, batch_key)
    calls += clip  # clipping forces the clipped run into its own path
    blend_switches = 0
    last_blend = None
    for s in sk.slots:
        if last_blend is not None and s.blend != last_blend:
            blend_switches += 1
        last_blend = s.blend

    deform_keys = sum(len(tls.get("deform", [])) for a in sk.animations.values()
                      for slots_ in a.attachments.values() for atts in slots_.values() for tls in atts.values())
    m = {
        "bones": len(sk.bones), "slots": len(sk.slots), "vertices": verts + anim_verts,
        "weighted_vertices": weighted, "clipping": clip, "draw_calls": calls,
        "physics": len(sk.physics), "deform_keys": deform_keys, "max_influences": max_inf,
    }
    if page_sizes is not None:
        m["atlas_pages"] = len(page_sizes)
        m["atlas_page_px"] = max(max(p) for p in page_sizes) if page_sizes else 0
    over = {k: {"value": v, "limit": lim[k]} for k, v in m.items() if k in lim and v > lim[k]}
    tips = []
    if "draw_calls" in over or blend_switches > 2:
        tips.append("group slots by blend mode in the draw order (e.g. all additive FX in one run above the art): "
                    "each change of blend mode or atlas page along the draw order is a new draw call")
    if "vertices" in over:
        heavy = sorted(per_slot.items(), key=lambda kv: -kv[1])[:3]
        tips.append(f"re-mesh the heaviest parts with lower detail: {heavy}")
    if "clipping" in over:
        tips.append("clipping is the most expensive feature on mobile; prefer a pre-masked texture or a shine baked into a sequence")
    if "deform_keys" in over:
        tips.append("replace deform keys with bones/weights (they bloat the file and cannot be retargeted)")
    if "atlas_pages" in over or "atlas_page_px" in over:
        tips.append("pack at scale 0.5–0.75 or quantise the page; a second page is an extra texture bind per frame")
    largest = sorted(per_slot.items(), key=lambda kv: -kv[1])[:5]
    return {"profile": profile, "ok": not over, "metrics": m, "over_budget": over, "blend_switches": blend_switches,
            "batch_breaks": breaks, "heaviest_slots": largest, "tips": tips}
