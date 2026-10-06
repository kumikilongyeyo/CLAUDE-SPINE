"""Working on the artist's slots directly: the ``edit_slots``, ``clone_art``, ``art_twin`` and ``hue_cycle`` tools.

* ``edit_slots``: hide / show a slot in the setup pose, remove it, change its blend or tint, or move it in the
  draw order. Moves and removals rewrite every animation's draw-order keys so they keep meaning the same order
  (Spine stores those keys as offsets from the setup order).
* ``clone_art``: a copy of some slots and the bones they hang from, shifted by an offset, under a prefix. Images
  are shared (one set in the atlas); weighted meshes are re-pointed at the cloned bones. One symbol becomes a
  column of them.
* ``art_twin``: an additive (or any blend) twin of each slot right above it, hidden in the setup pose: the layer a
  glow-bright moment or a colour wash is keyed on.
* ``hue_cycle``: shows the twins for a window and walks their tint round the colour wheel: a rainbow wash that sits
  exactly inside the art's own shape.
"""
from __future__ import annotations

import colorsys

from .ir import Animation, DrawOrderOffset, Key, MeshAttachment, Slot
from .project import Project
from .sphere import _put
from .timeline import color_keys, r

BLENDS = ("normal", "additive", "multiply", "screen")


# ------------------------------------------------------------------ draw order bookkeeping
def _absolute(base: list[str], offsets) -> list[str]:
    """The full draw order a draw-order key means, given the setup order it was written against."""
    if offsets is None:
        return list(base)
    n = len(base)
    out = [None] * n
    moved = set()
    idx = {s: i for i, s in enumerate(base)}
    for o in offsets:
        if o.slot not in idx:
            continue
        out[idx[o.slot] + o.offset] = o.slot
        moved.add(o.slot)
    rest = iter(s for s in base if s not in moved)
    return [s if s is not None else next(rest) for s in out]


def _offsets(base: list[str], order: list[str]):
    """Offsets that turn `base` into `order` (None when they are the same)."""
    if order == base:
        return None
    # list only slots whose relative order changed: the longest run that stays in base order is left implicit
    pos = {s: i for i, s in enumerate(order)}
    seq = [pos[s] for s in base]
    # longest increasing subsequence of seq = slots that need no offset
    import bisect
    tails, tails_i, prev = [], [], [-1] * len(seq)
    for i, v in enumerate(seq):
        k = bisect.bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            tails_i.append(i)
        else:
            tails[k] = v
            tails_i[k] = i
        prev[i] = tails_i[k - 1] if k else -1
    keep, i = set(), tails_i[-1] if tails_i else -1
    while i >= 0:
        keep.add(base[i])
        i = prev[i]
    offs = [DrawOrderOffset(slot=s, offset=pos[s] - i) for i, s in enumerate(base) if s not in keep]
    return offs or None


def _reorder(sk, new_order: list[str], drop: set[str] = frozenset()) -> None:
    """Set the setup draw order and rewrite every animation's draw-order keys to mean the same thing."""
    old = [s.name for s in sk.slots]
    for anim in sk.animations.values():
        for d in anim.drawOrder:
            absolute = [s for s in _absolute(old, d.offsets) if s not in drop]
            d.offsets = _offsets(new_order, absolute)
    by = {s.name: s for s in sk.slots}
    sk.slots = [by[n] for n in new_order]


# ------------------------------------------------------------------ edit_slots
def edit_slots(project: Project, slots: list[str], action: str, value: str = "") -> dict:
    sk = project.data
    for s in slots:
        sk.slot(s)
    action = action.lower()
    if action == "hide":
        for s in slots:
            sk.slot(s).attachment = None
    elif action == "show":
        for s in slots:
            names = list(sk.skin().attachments.get(s, {}))
            name = value or sk.slot(s).attachment or (names[0] if names else None)
            if name is None or name not in names:
                raise ValueError(f"slot {s!r} has no attachment {name!r}; it has {names}")
            sk.slot(s).attachment = name
    elif action == "blend":
        if value not in BLENDS:
            raise ValueError(f"blend is one of {BLENDS}")
        for s in slots:
            sk.slot(s).blend = value
    elif action == "color":
        v = value.upper().lstrip("#")
        if len(v) == 6:
            v += "FF"
        if len(v) != 8 or any(c not in "0123456789ABCDEF" for c in v):
            raise ValueError("color is RRGGBB or RRGGBBAA")
        for s in slots:
            sk.slot(s).color = v
    elif action in ("before", "after"):
        sk.slot(value)
        if value in slots:
            raise ValueError("cannot move slots relative to one of themselves")
        old = [s.name for s in sk.slots]
        moving = [s for s in old if s in set(slots)]
        rest = [s for s in old if s not in set(slots)]
        i = rest.index(value) + (1 if action == "after" else 0)
        _reorder(sk, rest[:i] + moving + rest[i:])
    elif action == "remove":
        gone = set(slots)
        for skin in sk.skins:
            for s in slots:
                skin.attachments.pop(s, None)
            for atts in skin.attachments.values():
                for att in atts.values():
                    if getattr(att, "type", "") == "clipping" and getattr(att, "end", None) in gone:
                        att.end = None
        for anim in sk.animations.values():
            for s in slots:
                anim.slots.pop(s, None)
                for skin in anim.attachments.values():
                    skin.pop(s, None)
        _reorder(sk, [s.name for s in sk.slots if s.name not in gone], drop=gone)
    else:
        raise ValueError("action is hide | show | remove | blend | color | before | after")
    return {"action": action, "slots": slots, "value": value, "slot_count": len(sk.slots)}


# ------------------------------------------------------------------ clone_art
def clone_art(project: Project, slots: list[str], prefix: str, offset=(0.0, 0.0), parent: str = "",
              place: str = "after", visible: bool = True) -> dict:
    """Copy `slots` and their bones (the subtree from their common ancestor) under `prefix`, shifted by `offset`
    in the parent's space. place: after | before the originals in the draw order."""
    sk = project.data
    if not prefix:
        raise ValueError("clone_art needs a prefix (the copies need their own names)")
    for s in slots:
        sk.slot(s)
    names = {b.name for b in sk.bones}
    need = set()
    for s in slots:
        need.add(sk.slot(s).bone)
        for an, att in sk.skin().attachments.get(s, {}).items():
            if isinstance(att, MeshAttachment) and len(att.vertices) != len(att.uvs):
                from .weights import decode_weighted
                for inf in decode_weighted(att.vertices, len(att.uvs) // 2):
                    need.update(sk.bones[bi].name for bi, *_ in inf)

    def chain(b):
        out = []
        while b is not None:
            out.append(b)
            b = sk.bone(b).parent
        return out[::-1]
    chains = [chain(b) for b in need]
    common = None
    for i in range(min(len(c) for c in chains)):
        if len({c[i] for c in chains}) == 1:
            common = chains[0][i]
    if common is None or common == sk.bones[0].name:
        # everything hangs from root: clone each needed bone's chain below root
        top = [c[1] for c in chains if len(c) > 1]
        roots = sorted(set(top))
    else:
        roots = [common]
    clone_set = set()
    for c in chains:
        for b in c:
            if any(b == rt or rt in chain(b) for rt in roots):
                clone_set.add(b)
    order = [b.name for b in sk.bones if b.name in clone_set]
    ren = {b: prefix + b for b in order}
    for b in ren.values():
        if b in names:
            raise ValueError(f"bone {b!r} already exists: pick another prefix")
    for b in order:
        src = sk.bone(b)
        is_root = b in roots
        par = (parent or src.parent) if is_root else ren[src.parent]
        bone = src.model_copy(deep=True)
        bone.name, bone.parent = ren[b], par
        if is_root:
            bone.x, bone.y = src.x + offset[0], src.y + offset[1]
        sk.add_bone(bone)
    index = {b.name: i for i, b in enumerate(sk.bones)}
    new_slots = []
    for s in slots:
        src = sk.slot(s)
        ns = prefix + s
        if sk.has_slot(ns):
            raise ValueError(f"slot {ns!r} already exists: pick another prefix")
        sk.slots.append(Slot(name=ns, bone=ren[src.bone], color=src.color, blend=src.blend,
                             attachment=src.attachment if visible else None))
        for an, att in sk.skin().attachments.get(s, {}).items():
            a = att.model_copy(deep=True)
            if hasattr(a, "path"):
                a.path = getattr(att, "path", None) or an
            if isinstance(a, MeshAttachment) and len(a.vertices) != len(a.uvs):
                v, i = list(a.vertices), 0
                for _ in range(len(a.uvs) // 2):
                    c = int(v[i]); i += 1
                    for _ in range(c):
                        v[i] = index[ren[sk.bones[int(v[i])].name]] if sk.bones[int(v[i])].name in ren else v[i]
                        i += 4
                a.vertices = v
            sk.set_attachment(ns, an, a)
        new_slots.append(ns)
    # place the copies next to the originals, in the setup order and in every animation's draw-order keys
    old = [x.name for x in sk.slots if x.name not in set(new_slots)]
    pos = (max(old.index(x) for x in slots) + 1) if place == "after" else min(old.index(x) for x in slots)
    rebuilt = old[:pos] + new_slots + old[pos:]
    for anim in sk.animations.values():
        for d in anim.drawOrder:
            absolute = _absolute(old, d.offsets)
            j = (max(absolute.index(x) for x in slots) + 1) if place == "after" else min(absolute.index(x) for x in slots)
            d.offsets = _offsets(rebuilt, absolute[:j] + new_slots + absolute[j:])
    by = {x.name: x for x in sk.slots}
    sk.slots = [by[n] for n in rebuilt]
    return {"slots": new_slots, "bones": [ren[b] for b in order], "roots": [ren[b] for b in roots],
            "offset": list(offset), "visible": visible}


# ------------------------------------------------------------------ art_twin + hue_cycle
def art_twin(project: Project, slots: list[str], name: str = "glow", blend: str = "additive") -> dict:
    """A twin of each slot right above it (same bone, same attachments, `blend`), hidden in the setup pose."""
    sk = project.data
    if blend not in BLENDS:
        raise ValueError(f"blend is one of {BLENDS}")
    twins = []
    for s in slots:
        src = sk.slot(s)
        tw = f"{s} {name}"
        if sk.has_slot(tw):
            twins.append(tw)
            continue
        sk.add_slot(Slot(name=tw, bone=src.bone, blend=blend), after=s)
        for an, att in sk.skin().attachments.get(s, {}).items():
            a = att.model_copy(deep=True)
            if hasattr(a, "path"):
                a.path = getattr(att, "path", None) or an
            sk.set_attachment(tw, an, a)
        sk.slot(tw).attachment = None
        twins.append(tw)
    # the twins sit right above their originals in every animation's draw order too
    base_without = [x.name for x in sk.slots if x.name not in set(twins)]
    for anim in sk.animations.values():
        for d in anim.drawOrder:
            if d.offsets is None:
                continue
            absolute = _absolute(base_without, d.offsets)
            for s in slots:
                absolute.insert(absolute.index(s) + 1, f"{s} {name}")
            d.offsets = _offsets([x.name for x in sk.slots], absolute)
    return {"twins": twins, "blend": blend}


RAINBOW = ["FF5FC8", "FFD040", "60E8FF", "B47CFF"]


def hue_cycle(project: Project, animation: str, slots: list[str], start: float, end: float, alpha: float = 0.5,
              cycles: float = 1.0, palette: list[str] | None = None, fade: float = 0.25) -> dict:
    """Show `slots` (twins from art_twin, or any slots) from start to end and walk their tint round the colour wheel
    (`palette` stops, or a smooth hue circle), fading in and out over `fade` seconds."""
    sk = project.data
    if end <= start:
        raise ValueError("end must be after start")
    anim = sk.animations.setdefault(animation, Animation())
    a = round(max(0.0, min(1.0, alpha)) * 255)
    n = max(4, int(round(8 * cycles)))
    pts = []
    for i in range(n + 1):
        u = i / n
        t = start + (end - start) * u
        if palette:
            c = palette[int(u * cycles * len(palette)) % len(palette)] if i < n else palette[int(cycles * len(palette)) % len(palette)]
        else:
            rr, gg, bb = colorsys.hsv_to_rgb((u * cycles) % 1.0, 0.65, 1.0)
            c = f"{round(rr * 255):02X}{round(gg * 255):02X}{round(bb * 255):02X}"
        k = min(1.0, (t - start) / fade if fade else 1.0, (end - t) / fade if fade else 1.0)
        pts.append((t, f"{c}{round(a * max(0.0, k)):02X}", "sine_in_out"))
    for s in slots:
        names = list(sk.skin().attachments.get(s, {}))
        if not names:
            raise ValueError(f"slot {s!r} has no attachment")
        att = sk.slot(s).attachment or names[0]
        node = anim.slots.setdefault(s, {})
        pre = [Key(time=0.0, name=None)] if start > 1e-6 else []
        _put(node, "attachment", pre + [Key(time=r(start), name=att), Key(time=r(end), name=None)], start, end)
        _put(node, "rgba", color_keys(pts), start, end)
    return {"animation": animation, "slots": slots, "start": start, "end": end, "keys": len(pts)}
