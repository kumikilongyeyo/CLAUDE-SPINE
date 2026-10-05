"""Typed model of the Spine 4.2 skeleton JSON format.

This is the one place that knows what Spine's JSON looks like. Every tool loads a
skeleton into these models, changes it, and saves it back. Keep it that way:
nothing else should build skeleton dicts by hand.

Two rules make round-trips safe:

* **Defaults are Spine's defaults.** Saving drops every field still at its
  default (``exclude_defaults``). A wrong default here would silently change a
  skeleton that only passed through a tool, so each one matches the runtime's
  ``SkeletonJson`` reader.
* **Unknown fields survive.** Every model allows extras, so a field this module
  does not know about (a newer Spine version, a nonessential editor field) is
  written back untouched rather than dropped.

Coordinates follow Spine: +Y is up, rotations are degrees counter-clockwise.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, Discriminator, Tag

SPINE_VERSION = "4.2.43"

_int, _float = int, float
Inherit = Literal["normal", "onlyTranslation", "noRotationOrReflection", "noScale", "noScaleOrReflection"]
Blend = Literal["normal", "additive", "multiply", "screen"]


class _M(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, validate_assignment=False)


# --------------------------------------------------------------------- setup pose
class SkeletonInfo(_M):
    hash: str = ""
    spine: str = SPINE_VERSION
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    referenceScale: float = 100
    fps: float = 30
    images: str = ""
    audio: str = ""


class Bone(_M):
    name: str
    parent: Optional[str] = None
    length: float = 0
    x: float = 0
    y: float = 0
    rotation: float = 0
    scaleX: float = 1
    scaleY: float = 1
    shearX: float = 0
    shearY: float = 0
    inherit: Inherit = "normal"
    skin: bool = False
    color: str = "989898FF"


class Slot(_M):
    name: str
    bone: str
    color: str = "FFFFFFFF"
    dark: Optional[str] = None
    attachment: Optional[str] = None
    blend: Blend = "normal"


class IkConstraint(_M):
    name: str
    order: int = 0
    skin: bool = False
    bones: list[str]
    target: str
    mix: float = 1
    softness: float = 0
    bendPositive: bool = True
    compress: bool = False
    stretch: bool = False
    uniform: bool = False


class TransformConstraint(_M):
    name: str
    order: int = 0
    skin: bool = False
    bones: list[str]
    target: str
    rotation: float = 0
    x: float = 0
    y: float = 0
    scaleX: float = 0
    scaleY: float = 0
    shearY: float = 0
    mixRotate: float = 1
    mixX: float = 1
    # Spine reads a missing mixY as mixX, and a missing mixScaleY as mixScaleX.
    mixY: Optional[float] = None
    mixScaleX: float = 1
    mixScaleY: Optional[float] = None
    mixShearY: float = 1
    local: bool = False
    relative: bool = False


class PhysicsConstraint(_M):
    """Spine 4.2 physics: secondary motion solved at runtime, not baked."""
    name: str
    order: int = 0
    skin: bool = False
    bone: str
    x: float = 0
    y: float = 0
    rotate: float = 0
    scaleX: float = 0
    shearX: float = 0
    limit: float = 5000
    fps: float = 60
    inertia: float = 1
    strength: float = 100
    damping: float = 1
    mass: float = 1
    wind: float = 0
    gravity: float = 0
    mix: float = 1
    inertiaGlobal: bool = False
    strengthGlobal: bool = False
    dampingGlobal: bool = False
    massGlobal: bool = False
    windGlobal: bool = False
    gravityGlobal: bool = False
    mixGlobal: bool = False


# -------------------------------------------------------------------- attachments
class Sequence(_M):
    count: int
    start: int = 1
    digits: int = 0
    setup: int = 0


class RegionAttachment(_M):
    type: Literal["region"] = "region"
    name: Optional[str] = None
    path: Optional[str] = None
    x: float = 0
    y: float = 0
    scaleX: float = 1
    scaleY: float = 1
    rotation: float = 0
    width: float = 32
    height: float = 32
    color: str = "FFFFFFFF"
    sequence: Optional[Sequence] = None


class MeshAttachment(_M):
    """``vertices`` is either 2 floats per vertex (unweighted, slot-bone space)
    or, when weighted, per vertex ``[boneCount, (boneIndex, x, y, weight) * n]``
    with x/y in each bone's own space. ``hull`` counts the leading vertices that
    form the outline, in order."""
    type: Literal["mesh"] = "mesh"
    name: Optional[str] = None
    path: Optional[str] = None
    uvs: list[float]
    triangles: list[int]
    vertices: list[float]
    hull: int
    edges: Optional[list[int]] = None
    width: float = 0
    height: float = 0
    color: str = "FFFFFFFF"
    sequence: Optional[Sequence] = None


class LinkedMeshAttachment(_M):
    type: Literal["linkedmesh"] = "linkedmesh"
    name: Optional[str] = None
    path: Optional[str] = None
    parent: str
    skin: Optional[str] = None
    timelines: bool = True
    width: float = 0
    height: float = 0
    color: str = "FFFFFFFF"
    sequence: Optional[Sequence] = None


class ClippingAttachment(_M):
    type: Literal["clipping"] = "clipping"
    end: Optional[str] = None
    vertexCount: int
    vertices: list[float]
    color: str = "CE3A3AFF"


class BoundingBoxAttachment(_M):
    type: Literal["boundingbox"] = "boundingbox"
    vertexCount: int
    vertices: list[float]
    color: str = "60F000FF"


class PointAttachment(_M):
    type: Literal["point"] = "point"
    x: float = 0
    y: float = 0
    rotation: float = 0
    color: str = "F1F100FF"


class PathAttachment(_M):
    type: Literal["path"] = "path"
    closed: bool = False
    constantSpeed: bool = True
    vertexCount: int
    vertices: list[float]
    lengths: list[float]
    color: str = "FF7F00FF"


def _att_type(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("type", "region")
    return getattr(v, "type", "region")


Attachment = Annotated[
    Union[
        Annotated[RegionAttachment, Tag("region")],
        Annotated[MeshAttachment, Tag("mesh")],
        Annotated[LinkedMeshAttachment, Tag("linkedmesh")],
        Annotated[ClippingAttachment, Tag("clipping")],
        Annotated[BoundingBoxAttachment, Tag("boundingbox")],
        Annotated[PointAttachment, Tag("point")],
        Annotated[PathAttachment, Tag("path")],
    ],
    Discriminator(_att_type),
]


class Skin(_M):
    name: str
    bones: list[str] = Field(default_factory=list)
    ik: list[str] = Field(default_factory=list)
    transform: list[str] = Field(default_factory=list)
    path: list[str] = Field(default_factory=list)
    physics: list[str] = Field(default_factory=list)
    attachments: dict[str, dict[str, Attachment]] = Field(default_factory=dict)


class EventData(_M):
    # Spine's keys are literally "int", "float" and "string".
    int_: _int = Field(0, alias="int")
    float_: _float = Field(0, alias="float")
    string: str = ""
    audio: str = ""
    volume: float = 1
    balance: float = 0


# --------------------------------------------------------------------- animations
Curve = Union[Literal["stepped"], list[float]]


class Key(_M):
    """One keyframe. Value fields depend on the timeline (``value``, ``x``/``y``,
    ``color``, ``name``, mixes...) and are carried as extras. ``curve`` shapes the
    segment from this key to the next: ``"stepped"`` or, per animated value,
    four absolute bezier numbers ``cx1, cy1, cx2, cy2`` (times and values, not
    0..1 fractions)."""
    time: float = 0
    curve: Optional[Curve] = None


class DrawOrderOffset(_M):
    slot: str
    offset: int


class DrawOrderKey(_M):
    time: float = 0
    offsets: Optional[list[DrawOrderOffset]] = None


class EventKey(_M):
    time: float = 0
    name: str


class Animation(_M):
    slots: dict[str, dict[str, list[Key]]] = Field(default_factory=dict)
    bones: dict[str, dict[str, list[Key]]] = Field(default_factory=dict)
    ik: dict[str, list[Key]] = Field(default_factory=dict)
    transform: dict[str, list[Key]] = Field(default_factory=dict)
    path: dict[str, dict[str, list[Key]]] = Field(default_factory=dict)
    physics: dict[str, dict[str, list[Key]]] = Field(default_factory=dict)
    attachments: dict[str, dict[str, dict[str, dict[str, list[Key]]]]] = Field(default_factory=dict)
    drawOrder: list[DrawOrderKey] = Field(default_factory=list)
    events: list[EventKey] = Field(default_factory=list)

    def duration(self) -> float:
        t = 0.0

        def walk(o):
            nonlocal t
            if isinstance(o, list):
                for k in o:
                    if isinstance(k, (Key, DrawOrderKey, EventKey)):
                        t = max(t, k.time)
                    else:
                        walk(k)
            elif isinstance(o, dict):
                for v in o.values():
                    walk(v)

        for f in ("slots", "bones", "ik", "transform", "path", "physics", "attachments"):
            walk(getattr(self, f))
        walk(self.drawOrder)
        walk(self.events)
        return t


# -------------------------------------------------------------------------- world
class WorldBone:
    """A bone's setup-pose world transform: the 2x2 matrix [[a, b], [c, d]] plus
    translation, exactly as the runtime's ``Bone.updateWorldTransform``."""
    __slots__ = ("a", "b", "c", "d", "x", "y", "length")

    def __init__(self, a, b, c, d, x, y, length):
        self.a, self.b, self.c, self.d, self.x, self.y, self.length = a, b, c, d, x, y, length

    def to_world(self, lx: float, ly: float) -> tuple[float, float]:
        return self.a * lx + self.b * ly + self.x, self.c * lx + self.d * ly + self.y

    def to_local(self, wx: float, wy: float) -> tuple[float, float]:
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-12:
            raise ValueError("bone has zero scale; world→local is undefined")
        dx, dy = wx - self.x, wy - self.y
        return (self.d * dx - self.b * dy) / det, (self.a * dy - self.c * dx) / det

    @property
    def rotation(self) -> float:
        return math.degrees(math.atan2(self.c, self.a))

    @property
    def tail(self) -> tuple[float, float]:
        return self.to_world(self.length, 0)

    @property
    def head(self) -> tuple[float, float]:
        return self.x, self.y


def _local_matrix(b: Bone):
    r = math.radians(b.rotation)
    rx, ry = r + math.radians(b.shearX), r + math.radians(90 + b.shearY)
    return (math.cos(rx) * b.scaleX, math.cos(ry) * b.scaleY,
            math.sin(rx) * b.scaleX, math.sin(ry) * b.scaleY)


# ----------------------------------------------------------------------- skeleton
class SkeletonData(_M):
    skeleton: SkeletonInfo = Field(default_factory=SkeletonInfo)
    bones: list[Bone] = Field(default_factory=list)
    slots: list[Slot] = Field(default_factory=list)
    ik: list[IkConstraint] = Field(default_factory=list)
    transform: list[TransformConstraint] = Field(default_factory=list)
    path: list[dict[str, Any]] = Field(default_factory=list)
    physics: list[PhysicsConstraint] = Field(default_factory=list)
    skins: list[Skin] = Field(default_factory=list)
    events: dict[str, EventData] = Field(default_factory=dict)
    animations: dict[str, Animation] = Field(default_factory=dict)

    # ---- io
    @classmethod
    def load(cls, path: str | Path) -> "SkeletonData":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("skins"), dict):  # Spine 3.x layout
            data["skins"] = [{"name": k, "attachments": v} for k, v in data["skins"].items()]
        return cls.model_validate(data)

    def to_dict(self) -> dict:
        out = self.model_dump(mode="json", exclude_defaults=True, exclude_none=True, by_alias=True)
        out["skeleton"] = self.skeleton.model_dump(mode="json", exclude_defaults=True, exclude_none=True)
        out["skeleton"].setdefault("spine", self.skeleton.spine)
        # Bones and slots need their names even when everything else is default,
        # and Spine requires a root bone entry to exist.
        # exclude_defaults also drops each attachment's ``type``, which is only
        # optional for regions.
        for sk_m, sk_d in zip(self.skins, out.get("skins", [])):
            for slot, atts in sk_m.attachments.items():
                for an, a in atts.items():
                    if a.type != "region":
                        sk_d["attachments"][slot][an] = {"type": a.type, **sk_d["attachments"][slot][an]}
                    else:
                        # spine-core has NO default for a region's size (Spine always writes it): dropping a 32 x 32
                        # that matches the model default loads as NaN vertices, so the size is always written
                        d = sk_d.setdefault("attachments", {}).setdefault(slot, {}).setdefault(an, {})
                        d.setdefault("width", a.width)
                        d.setdefault("height", a.height)
        order = ["skeleton", "bones", "slots", "ik", "transform", "path", "physics", "skins", "events", "animations"]
        if "animations" in out:
            for a in out["animations"].values():
                for k in [k for k, v in a.items() if not v]:
                    del a[k]
        return {k: out[k] for k in order if k in out} | {k: v for k, v in out.items() if k not in order}

    def save(self, path: str | Path, indent: int | None = 1) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=indent, ensure_ascii=False), encoding="utf-8")
        return p

    # ---- lookup
    def bone(self, name: str) -> Bone:
        for b in self.bones:
            if b.name == name:
                return b
        raise KeyError(f"no bone {name!r}")

    def has_bone(self, name: str) -> bool:
        return any(b.name == name for b in self.bones)

    def bone_index(self, name: str) -> int:
        for i, b in enumerate(self.bones):
            if b.name == name:
                return i
        raise KeyError(f"no bone {name!r}")

    def slot(self, name: str) -> Slot:
        for s in self.slots:
            if s.name == name:
                return s
        raise KeyError(f"no slot {name!r}")

    def has_slot(self, name: str) -> bool:
        return any(s.name == name for s in self.slots)

    def slot_index(self, name: str) -> int:
        for i, s in enumerate(self.slots):
            if s.name == name:
                return i
        raise KeyError(f"no slot {name!r}")

    def skin(self, name: str = "default", create: bool = True) -> Skin:
        for s in self.skins:
            if s.name == name:
                return s
        if not create:
            raise KeyError(f"no skin {name!r}")
        s = Skin(name=name)
        self.skins.insert(0 if name == "default" else len(self.skins), s)
        return s

    def attachment(self, slot: str, name: str | None = None, skin: str = "default"):
        sk = self.skin(skin, create=False)
        atts = sk.attachments.get(slot, {})
        if name is None:
            name = self.slot(slot).attachment
        if name not in atts:
            raise KeyError(f"no attachment {name!r} in slot {slot!r} (skin {skin!r})")
        return atts[name]

    def set_attachment(self, slot: str, name: str, att, skin: str = "default") -> None:
        self.skin(skin).attachments.setdefault(slot, {})[name] = att

    def children(self, name: str) -> list[Bone]:
        return [b for b in self.bones if b.parent == name]

    def descendants(self, name: str) -> list[str]:
        out, stack = [], [name]
        while stack:
            n = stack.pop()
            for c in self.children(n):
                out.append(c.name)
                stack.append(c.name)
        return out

    # ---- edits
    def add_bone(self, bone: Bone, after: str | None = None) -> Bone:
        """Insert a bone after its parent's subtree so parents always precede
        children, which the runtime requires."""
        if self.has_bone(bone.name):
            raise ValueError(f"bone {bone.name!r} already exists")
        if bone.parent is None and self.bones:
            raise ValueError("only the first bone may be parentless")
        if bone.parent is not None and not self.has_bone(bone.parent):
            raise KeyError(f"parent bone {bone.parent!r} does not exist")
        anchor = after or bone.parent
        if anchor is None:
            self.bones.append(bone)
            return bone
        before = [b.name for b in self.bones]
        idx = self.bone_index(anchor)
        sub = set(self.descendants(anchor))
        while idx + 1 < len(self.bones) and self.bones[idx + 1].name in sub:
            idx += 1
        self.bones.insert(idx + 1, bone)
        self.remap_bone_indices(before)
        return bone

    def reorder_bones(self, names: list[str]) -> None:
        """Put bones in the given order, keeping weighted vertices pointing at
        the same bones."""
        before = [b.name for b in self.bones]
        if sorted(before) != sorted(names):
            raise ValueError("reorder_bones needs exactly the existing bone names")
        by = {b.name: b for b in self.bones}
        self.bones = [by[n] for n in names]
        self.remap_bone_indices(before)

    def remap_bone_indices(self, old_order: list[str]) -> int:
        """Weighted vertices (meshes, clipping, bounding boxes, paths) name
        bones by *index*. After any change to the bone list, rewrite those
        indices so each vertex still follows the bone it followed before.
        Without this, inserting one bone silently re-targets every weighted
        mesh after it. Returns how many attachments were rewritten."""
        new_index = {b.name: i for i, b in enumerate(self.bones)}
        remap = [new_index.get(n, -1) for n in old_order]
        if remap == list(range(len(old_order))):
            return 0
        changed = 0
        for skin in self.skins:
            for atts in skin.attachments.values():
                for att in atts.values():
                    if att.type == "mesh":
                        n = len(att.uvs) // 2
                    elif att.type in ("clipping", "boundingbox", "path"):
                        n = att.vertexCount
                    else:
                        continue
                    v = att.vertices
                    if len(v) == 2 * n:
                        continue
                    out, i = list(v), 0
                    for _ in range(n):
                        c = int(v[i]); i += 1
                        for _ in range(c):
                            j = remap[int(v[i])]
                            if j < 0:
                                raise ValueError("a weighted vertex uses a bone that no longer exists")
                            out[i] = j
                            i += 4
                    att.vertices = out
                    changed += 1
        return changed

    def add_bone_world(self, name: str, parent: str, x: float, y: float,
                       rotation: float = 0, length: float = 0, **kw) -> Bone:
        """Add a bone whose head sits at world (x, y) with world ``rotation``,
        converting both into the parent's space."""
        world = self.world()
        p = world[parent]
        lx, ly = p.to_local(x, y)
        local_rot = rotation - p.rotation
        return self.add_bone(Bone(name=name, parent=parent, x=round(lx, 3), y=round(ly, 3),
                                  rotation=round(_wrap(local_rot), 3), length=round(length, 3), **kw))

    def add_slot(self, slot: Slot, before: str | None = None, after: str | None = None) -> Slot:
        if self.has_slot(slot.name):
            raise ValueError(f"slot {slot.name!r} already exists")
        if not self.has_bone(slot.bone):
            raise KeyError(f"slot bone {slot.bone!r} does not exist")
        if before is not None:
            self.slots.insert(self.slot_index(before), slot)
        elif after is not None:
            self.slots.insert(self.slot_index(after) + 1, slot)
        else:
            self.slots.append(slot)
        return slot

    def unique_name(self, base: str, kind: str = "bone") -> str:
        taken = {b.name for b in self.bones} if kind == "bone" else (
            {s.name for s in self.slots} if kind == "slot" else
            {c.name for c in [*self.ik, *self.transform, *self.physics]})
        if base not in taken:
            return base
        i = 2
        while f"{base}{i}" in taken:
            i += 1
        return f"{base}{i}"

    # ---- setup-pose world transforms
    def world(self) -> dict[str, WorldBone]:
        out: dict[str, WorldBone] = {}
        for b in self.bones:
            la, lb, lc, ld = _local_matrix(b)
            if b.parent is None:
                out[b.name] = WorldBone(la, lb, lc, ld, b.x, b.y, b.length)
                continue
            p = out[b.parent]
            wx = p.a * b.x + p.b * b.y + p.x
            wy = p.c * b.x + p.d * b.y + p.y
            if b.inherit == "onlyTranslation":
                a, bb, c, d = la, lb, lc, ld
            elif b.inherit == "normal":
                a = p.a * la + p.b * lc
                bb = p.a * lb + p.b * ld
                c = p.c * la + p.d * lc
                d = p.c * lb + p.d * ld
            else:
                # The no-scale / no-rotation modes need the runtime's full
                # decomposition. Treated as normal for setup-pose geometry, which
                # is exact whenever ancestors are unscaled and unrotated.
                a = p.a * la + p.b * lc
                bb = p.a * lb + p.b * ld
                c = p.c * la + p.d * lc
                d = p.c * lb + p.d * ld
            out[b.name] = WorldBone(a, bb, c, d, wx, wy, b.length)
        return out


def _wrap(deg: float) -> float:
    deg = (deg + 180) % 360 - 180
    return 180.0 if deg == -180 else deg


def new_skeleton(name: str = "", width: float = 0, height: float = 0, images: str = "./images/") -> SkeletonData:
    sk = SkeletonData(skeleton=SkeletonInfo(width=width, height=height, images=images))
    sk.bones.append(Bone(name="root"))
    sk.skins.append(Skin(name="default"))
    return sk


def color_hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    c = [max(0, min(255, round(v * 255))) for v in (r, g, b, a)]
    return "".join(f"{v:02X}" for v in c)


def parse_color(s: str) -> tuple[float, float, float, float]:
    s = s.strip().lstrip("#")
    vals = [int(s[i:i + 2], 16) / 255 for i in range(0, len(s), 2)]
    while len(vals) < 4:
        vals.append(1.0)
    return tuple(vals[:4])  # type: ignore[return-value]
