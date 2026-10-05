"""Procedural sample projects. Tests and demos run on these, so the repository
never needs to carry real (licensed) game art."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .ir import RegionAttachment, Slot, new_skeleton
from .project import Project


def _soft(im: Image.Image, r: float = 0.8) -> Image.Image:
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(r))
    im.putalpha(a)
    return im


def _shaded(size, shape_fn, top, bottom, outline=(30, 20, 40), ow=4) -> Image.Image:
    W, H = size
    mask = Image.new("L", size, 0)
    shape_fn(ImageDraw.Draw(mask), 0)
    grad = Image.new("RGB", size)
    g = np.linspace(0, 1, H)[:, None, None]
    grad = Image.fromarray((np.array(top)[None, None] * (1 - g) + np.array(bottom)[None, None] * g)
                           .repeat(W, 1).astype(np.uint8))
    inner = Image.new("L", size, 0)
    shape_fn(ImageDraw.Draw(inner), ow)
    base = Image.new("RGBA", size, outline + (255,))
    base.paste(grad, (0, 0), inner)
    base.putalpha(mask)
    return _soft(base)


def _place(project: Project, sk, slot: str, bone: str, im: Image.Image, cx: float, cy: float, **slot_kw):
    project.write_image(slot, im)
    wb = sk.world()[bone]
    lx, ly = wb.to_local(cx, cy)
    sk.slots.append(Slot(name=slot, bone=bone, attachment=slot, **slot_kw))
    sk.set_attachment(slot, slot, RegionAttachment(x=round(lx, 2), y=round(ly, 2), width=im.width, height=im.height,
                                                   rotation=round(-wb.rotation, 3)))


def _arm(project: Project, sk, slot: str, bone: str, im: Image.Image):
    """Arm art lies along its upper-arm bone, reaching past the elbow to the hand."""
    project.write_image(slot, im)
    sk.slots.append(Slot(name=slot, bone=bone, attachment=slot))
    sk.set_attachment(slot, slot, RegionAttachment(x=im.width / 2 - 12, y=0, width=im.width, height=im.height))


def make_symbol(out_dir: str | Path, name: str = "gem") -> Project:
    """A 260px slot symbol: back plate, gem, letter, highlight."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=260, height=260)
    p = Project(out / f"{name}.json", sk)
    plate = _shaded((240, 240), lambda d, o: d.rounded_rectangle([o, o, 239 - o, 239 - o], radius=46 - o, fill=255),
                    (120, 40, 160), (50, 10, 80))
    gem = _shaded((160, 150), lambda d, o: d.polygon([(80, o), (159 - o, 55), (80, 149 - o), (o, 55)], fill=255),
                  (90, 255, 200), (0, 120, 110), ow=5)
    letter = Image.new("RGBA", (90, 90), (0, 0, 0, 0))
    ImageDraw.Draw(letter).polygon([(10, 80), (45, 8), (80, 80), (62, 80), (45, 42), (28, 80)], fill=(255, 236, 160, 255))
    letter = _soft(letter)
    hl = Image.new("RGBA", (70, 30), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([0, 0, 69, 29], fill=(255, 255, 255, 170))
    hl = _soft(hl, 3)
    _place(p, sk, "plate", "root", plate, 0, 0)
    _place(p, sk, "gem", "root", gem, 0, 10)
    _place(p, sk, "letter", "root", letter, 0, -60)
    _place(p, sk, "highlight", "root", hl, -22, 48)
    p.save()
    return p


def make_character(out_dir: str | Path, name: str = "hero") -> Project:
    """A chibi mascot with separated parts for every rig feature: body,
    two-bone arms (IK), a cape (cloth), hair locks (physics), face features
    and ears (turn rig)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=420, height=520)
    p = Project(out / f"{name}.json", sk)
    sk.add_bone_world("hip", "root", 0, 120, 90, length=90)
    sk.add_bone_world("chest", "hip", 0, 210, 90, length=50)
    sk.add_bone_world("head", "chest", 0, 260, 90, length=170)
    # straight arms hanging out and down; IK bends them
    for side, ang in (("l", 235.0), ("r", -55.0)):
        sx = -62 if side == "l" else 62
        c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        sk.add_bone_world(f"arm_{side}1", "chest", sx, 200, ang, length=70)
        sk.add_bone_world(f"arm_{side}2", f"arm_{side}1", sx + 70 * c, 200 + 70 * s_, ang, length=62)
    skin_t, skin_b = (255, 214, 180), (230, 170, 140)
    cape = _shaded((200, 220), lambda d, o: d.polygon([(40 + o, o), (160 - o, o), (199 - o, 219 - o), (o, 219 - o)], fill=255),
                   (200, 30, 50), (110, 10, 30))
    body = _shaded((150, 170), lambda d, o: d.rounded_rectangle([o, o, 149 - o, 169 - o], radius=50 - o, fill=255),
                   (60, 110, 220), (30, 50, 140))

    def arm_img():
        return _shaded((150, 44), lambda d, o: d.rounded_rectangle([o, o, 149 - o, 43 - o], radius=21 - o, fill=255),
                       skin_t, skin_b)

    head = _shaded((230, 210), lambda d, o: d.ellipse([o, o, 229 - o, 209 - o], fill=255), skin_t, skin_b)
    ear = _shaded((50, 70), lambda d, o: d.ellipse([o, o, 49 - o, 69 - o], fill=255), skin_t, skin_b)
    eye = Image.new("RGBA", (34, 44), (0, 0, 0, 0))
    de = ImageDraw.Draw(eye)
    de.ellipse([0, 0, 33, 43], fill=(30, 20, 40, 255))
    de.ellipse([8, 6, 18, 18], fill=(255, 255, 255, 255))
    eye = _soft(eye)
    brow = Image.new("RGBA", (44, 16), (0, 0, 0, 0))
    ImageDraw.Draw(brow).rounded_rectangle([0, 2, 43, 13], radius=6, fill=(70, 40, 30, 255))
    nose = _shaded((26, 22), lambda d, o: d.ellipse([o, o, 25 - o, 21 - o], fill=255), (240, 160, 140), (210, 120, 110), ow=2)
    mouth = Image.new("RGBA", (60, 30), (0, 0, 0, 0))
    ImageDraw.Draw(mouth).chord([0, -30, 59, 29], 0, 180, fill=(150, 40, 60, 255))
    mouth = _soft(mouth)
    hair_back = _shaded((250, 150), lambda d, o: d.ellipse([o, o, 249 - o, 149 - o], fill=255), (110, 60, 30), (70, 35, 15))
    fringe = _shaded((240, 90), lambda d, o: d.chord([o, o - 70, 239 - o, 89 - o], 0, 180, fill=255), (130, 70, 35), (90, 45, 20))

    def lock():
        im = Image.new("RGBA", (60, 190), (0, 0, 0, 0))
        m = Image.new("L", im.size, 0)
        d = ImageDraw.Draw(m)
        pts = [(30 + 14 * math.sin(t / 30), t) for t in range(0, 186, 6)]
        for i, (x, y) in enumerate(pts):
            r = 22 * (1 - y / 230)
            d.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=255)
        col = Image.new("RGBA", im.size, (120, 64, 32, 255))
        col.putalpha(m)
        return _soft(col)

    # draw order back → front
    _place(p, sk, "hair_back", "head", hair_back, 0, 365)
    _place(p, sk, "cape", "chest", cape, 0, 130)
    _arm(p, sk, "arm_r", "arm_r1", arm_img())
    _place(p, sk, "body", "hip", body, 0, 170)
    _place(p, sk, "lock_l", "head", lock(), -112, 300)
    _place(p, sk, "lock_r", "head", lock(), 112, 300)
    _place(p, sk, "ear_l", "head", ear, -112, 360)
    _place(p, sk, "ear_r", "head", ear, 112, 360)
    _place(p, sk, "face", "head", head, 0, 355)
    _place(p, sk, "eye_l", "head", eye, -42, 362)
    _place(p, sk, "eye_r", "head", eye, 42, 362)
    _place(p, sk, "brow_l", "head", brow, -42, 398)
    _place(p, sk, "brow_r", "head", brow, 42, 398)
    _place(p, sk, "nose", "head", nose, 0, 338)
    _place(p, sk, "mouth", "head", mouth, 0, 308)
    _place(p, sk, "fringe", "head", fringe, 0, 448)
    _arm(p, sk, "arm_l", "arm_l1", arm_img())
    p.save()
    return p
