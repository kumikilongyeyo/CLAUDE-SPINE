"""rig_coin + coin_spin: an extruded coin (two face bones + one weighted rim mesh) and its spins, on procedural art."""
import asyncio
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from claude_spine import coin, qa, render, runtime
from claude_spine.ir import Bone, MeshAttachment, RegionAttachment, Slot, new_skeleton
from claude_spine.mesh import region_pixel_to_local, to_world
from claude_spine.project import Project
from claude_spine.weights import decode_weighted

from conftest import needs_node

W, H, R, CX, CY = 400, 424, 180.0, 201.0, 199.0       # the disc sits ~13 px above the image centre (shadow below)


def _disc(cx, cy, r, fill, ss=4):
    m = Image.new("L", (W * ss, H * ss), 0)
    ImageDraw.Draw(m).ellipse([(cx - r) * ss, (cy - r) * ss, (cx + r) * ss, (cy + r) * ss], fill=fill)
    return m.resize((W, H), Image.LANCZOS)


def coin_art(emblem=(200, 60, 30)) -> Image.Image:
    """A gold disc with an inner ring and a triangle emblem, plus a soft dark shadow poking out below it."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.paste((20, 10, 0, 255), (0, 0), _disc(CX, CY + 16, R, 200).filter(ImageFilter.GaussianBlur(4)))
    face = Image.new("RGBA", (W, H), (230, 170, 40, 255))
    d = ImageDraw.Draw(face)
    d.ellipse([CX - R * 0.86, CY - R * 0.86, CX + R * 0.86, CY + R * 0.86], outline=(150, 90, 10, 255), width=10)
    d.polygon([(CX, CY - 85), (CX + 70, CY + 55), (CX - 70, CY + 55)], fill=emblem + (255,))
    face.putalpha(_disc(CX, CY, R, 255))
    img.alpha_composite(face)
    return img


@pytest.fixture
def art(tmp_path):
    p = tmp_path / "art" / "face.png"
    p.parent.mkdir()
    coin_art().save(p)
    return p


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "coin"
    (d / "images").mkdir(parents=True)
    p = Project(d / "coin.json", new_skeleton("coin", 600, 600))
    p.save()
    return p


@pytest.fixture
def rigged(proj, art):
    coin.rig_coin(proj, image=str(art))
    return proj


def _cos(theta, t):
    return math.cos(math.radians(theta(t)))


# ------------------------------------------------------------------ measuring the art
def test_fit_disc_finds_the_coin_not_the_shadow():
    img = coin_art()
    cx, cy, r = coin.fit_disc(img)
    assert abs(cx - CX) < 2 and abs(cy - CY) < 2 and abs(r - R) < 2
    ys, xs = np.nonzero(np.asarray(img)[..., 3] > 127)
    assert (ys.min() + ys.max()) / 2 - CY > 5          # the naive bounding-box centre is pulled down by the shadow


def test_rim_texture_and_colour():
    rim = coin.make_rim((180, 180, 190), ridges=10, per=20)
    assert rim.size == (32, 200)
    a = np.asarray(rim).astype(float)
    assert a[..., 3].min() == 255
    assert np.abs(a[:20, 16, :3] - a[20:40, 16, :3]).mean() < 25    # the ridges repeat
    assert a[..., :3].std() > 20                                    # grooves and highlights
    assert coin.rim_colour_from(coin_art(), CX, CY, R)[0] == 226    # sampled from the gold outer ring
    blank = Image.new("RGBA", (40, 40))
    assert coin.rim_colour_from(blank, 20, 20, 18) == coin.GOLD


# ------------------------------------------------------------------ rig_coin
def test_rig_coin_from_an_image(rigged):
    sk = rigged.data
    names = [b.name for b in sk.bones]
    assert names[-3:] == ["coin", "coin_f", "coin_eb"]
    assert [s.name for s in sk.slots][-3:] == ["coin_edge", "coin_back", "coin_front"]
    assert sk.slot("coin_front").attachment == "face" and sk.slot("coin_back").attachment is None
    front = sk.attachment("coin_front", "face")
    assert front.width == W and front.height == H
    assert abs(front.x - (W / 2 - CX)) < 2 and abs(front.y - (CY - H / 2)) < 2     # disc centre = bone origin
    back = sk.attachment("coin_back", "face")
    assert back.scaleX == -1 and back.x == pytest.approx(-front.x) and back.y == pytest.approx(front.y)
    back_x = sk.attachment("coin_back", "face_x")
    assert back_x.scaleY == -1 and back_x.y == pytest.approx(-front.y) and back_x.x == pytest.approx(front.x)
    assert (rigged.images_dir / "coin_face.png").exists() and (rigged.images_dir / "coin_rim.png").exists()
    assert qa.validate(sk)["ok"], qa.validate(sk)["errors"]


def test_rim_mesh_is_a_two_ring_weighted_cylinder(rigged):
    sk = rigged.data
    m = sk.attachment("coin_edge", "edge")
    assert isinstance(m, MeshAttachment)
    n = len(m.uvs) // 2
    assert n == 2 * (coin.RIM_N + 1) and m.hull == n
    fi, bi = sk.bone_index("coin_f"), sk.bone_index("coin_eb")
    inf = decode_weighted(m.vertices, n)
    assert all(len(v) == 1 and v[0][3] == 1.0 for v in inf)
    assert [v[0][0] for v in inf] == [fi] * (n // 2) + [bi] * (n // 2)          # front ring, then back ring
    rr = [math.hypot(v[0][1], v[0][2]) for v in inf]
    assert max(rr) < R + 2 - 0.5 and min(rr) > R - 2 - 1                         # inset just inside the face disc
    uv = np.asarray(m.uvs).reshape(-1, 2)
    assert uv.min() >= 0 and uv.max() <= 1
    tri = np.asarray(m.triangles).reshape(-1, 3)
    assert len(tri) == 2 * coin.RIM_N and tri.min() >= 0 and tri.max() < n
    p = uv[tri]
    area = (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1])
    assert np.all(np.abs(area) > 1e-6) and (np.all(area > 0) or np.all(area < 0))   # no slivers, one winding
    # the coin's dimensions ride on the mesh: coin_spin reads them back
    dims = coin.coin_parts(sk, "coin")
    assert dims["R"] == pytest.approx(R, abs=2) and dims["T"] == pytest.approx(0.13 * 2 * dims["R"], abs=1e-3)


def test_inserted_bones_keep_the_rim_on_its_face_bones(rigged):
    sk = rigged.data
    sk.add_bone(Bone(name="early", parent="root"))
    sk.reorder_bones(["root", "early"] + [b.name for b in sk.bones if b.name not in ("root", "early")])
    m = sk.attachment("coin_edge", "edge")
    idx = {v[0][0] for v in decode_weighted(m.vertices, len(m.uvs) // 2)}
    assert idx == {sk.bone_index("coin_f"), sk.bone_index("coin_eb")}


@pytest.mark.parametrize("depth,ratio", [("thin", 0.065), ("medium", 0.13), ("thick", 0.26), (0.2, 0.2), ("0.1", 0.1)])
def test_depth_presets(proj, art, depth, ratio):
    res = coin.rig_coin(proj, image=str(art), depth=depth)
    assert res["thickness"] == pytest.approx(ratio * 2 * res["radius"], abs=1e-3)
    assert proj.data.attachment("coin_edge", "edge").width == pytest.approx(res["thickness"], abs=1e-3)


def test_depth_in_units_radius_override_and_errors(proj, art):
    res = coin.rig_coin(proj, image=str(art), depth=40, radius=150, rim_color="C0C0C8")
    assert res["thickness"] == 40 and res["radius"] == 150 and res["rim_color"] == "C0C0C8"
    with pytest.raises(ValueError, match="already exists"):
        coin.rig_coin(proj, image=str(art))
    with pytest.raises(ValueError, match="exactly one"):
        coin.rig_coin(proj, name="c2")
    with pytest.raises(ValueError, match="depth"):
        coin.rig_coin(proj, image=str(art), name="c3", depth="chunky")


def test_rig_coin_from_a_face_slot_keeps_it_in_place(proj, art):
    sk = proj.data
    coin_art().save(proj.images_dir / "coin-front.png")
    sk.add_bone_world("symbol", "root", 120, -40, 0)
    sk.slots.append(Slot(name="under", bone="symbol"))
    sk.slots.append(Slot(name="coin-front", bone="symbol", attachment="coin-front"))
    sk.slots.append(Slot(name="over", bone="symbol"))
    sk.set_attachment("coin-front", "coin-front", RegionAttachment(x=10, y=5, width=W * 0.5, height=H * 0.5))
    old = sk.attachment("coin-front", "coin-front")
    f, _ = region_pixel_to_local(old, W, H)
    corners = np.array([[0, 0], [W, 0], [0, H], [W, H]], float)
    want = to_world(sk.world()["symbol"], f(corners))
    disc = to_world(sk.world()["symbol"], f(np.array([[CX, CY]])))[0]
    res = coin.rig_coin(proj, face="coin-front", depth="medium")
    assert res["hidden"] == ["coin-front"] and sk.slot("coin-front").attachment is None
    assert [s.name for s in sk.slots] == ["under", "coin-front", "coin_edge", "coin_back", "coin_front", "over"]
    world = sk.world()
    assert world["coin"].x == pytest.approx(disc[0], abs=1.5) and world["coin"].y == pytest.approx(disc[1], abs=1.5)
    assert res["radius"] == pytest.approx(R * 0.5, abs=1) and res["units_per_px"] == pytest.approx(0.5)
    new = sk.attachment("coin_front", "face")
    g, _ = region_pixel_to_local(new, W, H)
    got = to_world(world["coin_f"], g(corners))
    assert np.abs(got - want).max() < 0.05                                       # the face did not move
    assert qa.validate(sk)["ok"]


def test_rig_coin_with_its_own_back_art(proj, art, tmp_path):
    bp = tmp_path / "back.png"
    coin_art(emblem=(30, 60, 200)).resize((200, 212)).save(bp)
    res = coin.rig_coin(proj, image=str(art), back=str(bp))
    b = proj.data.attachment("coin_back", "face")
    assert b.path == "coin_back" and b.width == pytest.approx(400, abs=6)        # scaled so the discs match
    assert b.scaleX == -1 and res["radius"] == pytest.approx(R, abs=2)


# ------------------------------------------------------------------ coin_spin: keys
def _vals(ks, field="value"):
    return [(k.time, getattr(k, field)) for k in ks]


def test_loop_is_seamless_and_swaps_exactly_edge_on(rigged):
    res = coin.coin_spin(rigged, mode="loop", turns=2, duration=2.0, bob=12, tilt=4)
    sk = rigged.data
    a = sk.animations["spin"]
    assert res["end_angle"] == 720 and res["ends_on"] == "front"
    assert res["face_swaps"] == pytest.approx([0.25, 0.75, 1.25, 1.75], abs=1e-4)
    sx = a.bones["coin_f"]["scalex"]
    tx = a.bones["coin_f"]["translatex"]
    assert sx[0].time == 0 and sx[-1].time == 2.0
    assert sx[0].value == sx[-1].value == 1.0 and tx[0].value == tx[-1].value == 0.0     # first = last = setup
    for s in ("coin_front", "coin_back", "coin_edge"):
        col = a.slots[s]["rgba"]
        assert col[0].color == col[-1].color == sk.slot(s).color                     # no colour pop at the loop
    assert a.bones["coin"]["translate"][0].y == a.bones["coin"]["translate"][-1].y == 0
    assert a.bones["coin"]["rotate"][0].value == a.bones["coin"]["rotate"][-1].value == 0
    by_t = {k.time: k.value for k in sx}
    for t in res["face_swaps"]:
        assert by_t[t] == 0.0                                                         # zero wide at the swap
    fr = [(k.time, k.name) for k in a.slots["coin_front"]["attachment"]]
    bk = [(k.time, k.name) for k in a.slots["coin_back"]["attachment"]]
    assert [t for t, _ in fr[1:]] == res["face_swaps"] and [n for _, n in fr] == ["face", None, "face", None, "face"]
    assert [n for _, n in bk] == [None, "face", None, "face", None]
    gaps = np.diff([k.time for k in sx])
    assert gaps.max() <= 1 / 60 + 1e-3 and gaps.min() > 0                           # dense, strictly increasing
    assert qa.validate(sk)["ok"]


@pytest.mark.parametrize("mode", ["flip", "spin_up", "slow_down", "land"])
def test_one_shots_stop_face_on_after_whole_turns(rigged, mode):
    res = coin.coin_spin(rigged, animation=mode, mode=mode, turns=3, duration=1.6, start=0.2)
    assert res["end_angle"] == 1080 and res["ends_on"] == "front"
    th = coin.spin_theta(mode, 0.2, 1.8, 1080)
    assert len(res["face_swaps"]) == 6
    for t in res["face_swaps"]:
        assert abs(_cos(th, t)) < 2e-3                                               # edge-on at every swap
    assert th(1.8) == 1080 and th(0.2) == 0
    us = np.linspace(0.2, 1.8, 400)
    assert np.all(np.diff([th(t) for t in us]) >= -1e-9)                            # never turns back
    a = rigged.data.animations[mode]
    last = a.bones["coin_f"]["scalex"][-1]
    assert last.value == 1.0
    if mode == "spin_up":                                                            # accelerating, then a brake
        sp = np.diff([th(t) for t in us])
        assert sp[:40].mean() < sp[250:320].mean() and sp[-5:].mean() < 0.2 * sp[250:320].mean()
    if mode == "slow_down":
        sp = np.diff([th(t) for t in us])
        assert sp[:20].mean() > 5 * sp[-20:].mean()
    names = [e.name for e in a.events]
    assert {"flip": "sfx_flip", "spin_up": "sfx_stop", "slow_down": "sfx_spin", "land": "sfx_land"}[mode] in names


def test_land_squashes_with_the_base_planted(rigged):
    res = coin.coin_spin(rigged, animation="land", mode="land", turns=2, duration=0.6, tilt=10)
    a = rigged.data.animations["land"]
    assert res["settle_end"] == pytest.approx(1.3)
    tr = a.bones["coin"]["translate"]
    assert tr[0].y == pytest.approx(4 * res["radius"], rel=1e-3) and tr[0].time == 0
    sc = {k.time: k for k in a.bones["coin"]["scale"]}
    trd = {k.time: k for k in tr}
    squashed = [t for t, k in sc.items() if k.y < 0.95]
    assert squashed and min(squashed) > 0.6                                          # only after the landing
    for t in squashed:
        if not 0.10 < t - 0.6 < 0.40:                                                # outside the little bounce
            assert trd[t].y == pytest.approx(-(1 - sc[t].y) * res["radius"], abs=0.2)  # (scale keys keep 3 decimals)
    assert sc[1.3].x == pytest.approx(1) and sc[1.3].y == pytest.approx(1)
    rot = a.bones["coin"]["rotate"]
    assert rot[0].value == -10 and rot[-1].value == 0
    assert [e.name for e in a.events] == ["sfx_land"] and a.events[0].time == 0.6


def test_stop_sides_and_turn_rules(rigged):
    r1 = coin.coin_spin(rigged, animation="seq", mode="flip", turns=0, duration=0.5, stop="back")
    assert r1["end_angle"] == 180 and r1["ends_on"] == "back"
    r2 = coin.coin_spin(rigged, animation="seq", mode="flip", turns=1, duration=0.5, start=1.0)
    assert r2["start_angle"] == 180 and r2["end_angle"] == 720 and r2["ends_on"] == "front"   # picks up the back
    a = rigged.data.animations["seq"]
    assert a.slots["coin_back"]["attachment"][1].name == "face"
    r3 = coin.coin_spin(rigged, animation="any", mode="flip", turns=1.25, duration=1.0, stop="any")
    assert r3["end_angle"] == 450 and r3["ends_on"] == "edge/angle"
    with pytest.raises(ValueError, match="whole turns"):
        coin.coin_spin(rigged, animation="x", mode="loop", turns=1.5)
    with pytest.raises(ValueError, match="whole turns"):
        coin.coin_spin(rigged, animation="x", mode="flip", turns=1.5)
    with pytest.raises(ValueError, match="rig_coin"):
        coin.coin_spin(rigged, coin="nope")
    with pytest.raises(ValueError, match="ease"):
        coin.coin_spin(rigged, animation="x", mode="flip", ease="wobbly")
    r4 = coin.coin_spin(rigged, animation="e", mode="flip", turns=2, ease="expo_out")
    assert r4["end_angle"] == 720 and r4["face_swaps"][0] < 0.2                     # fast out of the blocks


def test_merges_into_an_animation_and_replace_wipes(rigged):
    sk = rigged.data
    sk.add_bone(Bone(name="other", parent="root"))
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(sk, "show").bone("other", "rotate", [(0, 0), (3, 90)])
    coin.coin_spin(rigged, animation="show", mode="flip", duration=1.0, start=0.0)
    coin.coin_spin(rigged, animation="show", mode="spin_up", turns=2, duration=1.0, start=2.0)
    a = sk.animations["show"]
    assert "other" in a.bones
    sx = a.bones["coin_f"]["scalex"]
    assert any(k.time < 1.01 for k in sx) and any(k.time > 2.99 for k in sx)        # both windows kept
    assert not any(1.001 < k.time < 1.999 for k in sx)
    coin.coin_spin(rigged, animation="show", mode="loop", duration=1.0, replace=True)
    assert "other" not in sk.animations["show"].bones


def test_axis_x_flips_over_the_horizontal_axis(rigged):
    res = coin.coin_spin(rigged, animation="tumble", mode="flip", axis="x", turns=1, duration=1.0)
    a = rigged.data.animations["tumble"]
    assert set(a.bones["coin_f"]) == {"translatey", "scaley"}
    assert {k.name for k in a.slots["coin_back"]["attachment"]} == {None, "face_x"}
    assert res["face_swaps"] == pytest.approx([0.0625 ** (1 / 3), 1 - 0.0625 ** (1 / 3)], abs=2e-4)


# ------------------------------------------------------------------ in the official runtime
def _quad_sign(v):
    p = np.asarray(v).reshape(-1, 2)
    x, y = p[:, 0], p[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


@needs_node
@pytest.mark.parametrize("mode,axis", [("loop", "y"), ("flip", "y"), ("spin_up", "y"), ("land", "y"), ("flip", "x")])
def test_runtime_shows_only_the_face_toward_the_camera(rigged, mode, axis):
    turns, D = (1, 1.0) if mode == "loop" else (2, 1.2)
    res = coin.coin_spin(rigged, animation="a", mode=mode, turns=turns, duration=D, axis=axis)
    rigged.save()
    dump = runtime.run(rigged, animations=["a"], fps=60, geometry=True)
    assert dump["ok"], dump.get("error") or dump["problems"][:3]
    setup = {d["slot"]: d for d in dump["setup"]["draws"]}
    s0 = _quad_sign(setup["coin_front"]["v"])
    w0 = np.ptp(np.asarray(setup["coin_front"]["v"]).reshape(-1, 2)[:, 0 if axis == "y" else 1])
    th = coin.spin_theta(mode, 0, D, 360 * turns)
    frames = dump["animations"]["a"]["frames"]
    for f in frames:
        d = {x["slot"]: x for x in f["draws"]}
        assert "coin_edge" in d
        faces = [s for s in ("coin_front", "coin_back") if s in d]
        assert len(faces) == 1, (f["t"], faces)                                       # never both, never none
        c = _cos(th, f["t"])
        if abs(c) < 0.03 or f["t"] > D + 1e-6:                                    # (land: squash after D)
            continue
        assert faces[0] == ("coin_front" if c > 0 else "coin_back"), (f["t"], c)
        v = d[faces[0]]["v"]
        assert _quad_sign(v) * s0 > 0, f["t"]                                         # never seen mirrored
        span = np.ptp(np.asarray(v).reshape(-1, 2)[:, 0 if axis == "y" else 1])
        assert span == pytest.approx(w0 * abs(c), abs=1.0)
    if mode == "loop":
        first, last = frames[0]["draws"], frames[-1]["draws"]
        assert [x["slot"] for x in first] == [x["slot"] for x in last]
        for a_, b_ in zip(first, last):
            assert np.abs(np.asarray(a_["v"]) - np.asarray(b_["v"])).max() < 0.02
            assert np.abs(np.asarray(a_["color"]) - np.asarray(b_["color"])).max() < 1e-3
        for a_, b_ in zip(dump["setup"]["draws"], first):
            assert np.abs(np.asarray(a_["v"]) - np.asarray(b_["v"])).max() < 0.02  # frame 0 = the setup pose
    assert res["end_angle"] == 360 * turns


@needs_node
def test_edge_on_shows_the_wall_and_renders(rigged, tmp_path):
    coin.coin_spin(rigged, animation="a", mode="loop", turns=1, duration=1.0)
    rigged.save()
    dump = runtime.run(rigged, animations=["a"], fps=8, geometry=True)
    edge_on = min(dump["animations"]["a"]["frames"], key=lambda f: abs(f["t"] - 0.25))
    d = {x["slot"]: x for x in edge_on["draws"]}
    wall = np.asarray(d["coin_edge"]["v"]).reshape(-1, 2)
    T = coin.coin_parts(rigged.data, "coin")["T"]
    assert np.ptp(wall[:, 0]) == pytest.approx(T, abs=1.5)                           # the wall is T wide edge-on
    assert np.ptp(wall[:, 1]) == pytest.approx(2 * R, abs=4)
    out = render.render_animation(dump, "a", tmp_path / "prev", size=128, gif=False)
    im = np.asarray(Image.open(out["sheet"]).convert("RGB")).astype(float)
    assert im.std() > 10
    shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)


@needs_node
def test_validate_and_mcp_tools(proj, art):
    from claude_spine.server import mcp, validate

    def call(name, **args):
        res = asyncio.run(mcp.call_tool(name, args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)

    r1 = call("rig_coin", project=str(proj.path), image=str(art), depth="thick")
    assert r1["thickness_ratio"] == 0.26 and "validation_errors" not in r1
    r2 = call("coin_spin", project=str(proj.path), mode="spin_up", turns=3, duration=2.0)
    assert r2["ends_on"] == "front" and len(r2["face_swaps"]) == 6 and "validation_errors" not in r2
    v = validate(str(proj.path))
    assert v["ok"] and v["runtime"]["ok"], v
