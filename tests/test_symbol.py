"""Symbol tools built from the artist's art: sphere_spin, liquid_splat, shake, plus the AE helpers they lean on
(surface_sweep / lens_flare templates, feather / anchor / deform_like, check_aep) and the PSD import fixes."""
import math
import struct

import numpy as np
import pytest
from PIL import Image, ImageDraw

from claude_spine import ae_bridge, ae_templates, fx_splat, psd as psd_mod, qa, runtime, sphere
from claude_spine.ir import MeshAttachment, RegionAttachment, Slot, new_skeleton
from claude_spine.mesh import rig_mesh
from claude_spine.project import Project
from claude_spine.weights import decode_weighted

from conftest import needs_node


def _ball_art(d: int = 200) -> Image.Image:
    """A candy ball: diagonal stripes, darker rim, a white glint."""
    y, x = np.mgrid[0:d, 0:d].astype(float)
    r = np.hypot(x - d / 2, y - d / 2) / (d / 2)
    band = ((x + y) / 28).astype(int) % 3
    pal = np.array([[240, 40, 140], [255, 230, 200], [250, 170, 30]], float)
    rgb = pal[band] * np.clip(1.15 - 0.45 * r ** 3, 0, 1)[..., None]
    g = np.hypot(x - d * 0.33, y - d * 0.3) < d * 0.06
    rgb[g] = 255
    a = np.clip((1 - r) * d / 2, 0, 1) * 255
    return Image.fromarray(np.dstack([rgb, a]).clip(0, 255).astype(np.uint8), "RGBA")


@pytest.fixture
def ball(tmp_path):
    d = tmp_path / "ball"
    (d / "images").mkdir(parents=True)
    _ball_art().save(d / "images" / "shell.png")
    Image.new("RGBA", (50, 40), (250, 90, 160, 255)).save(d / "images" / "cap.png")
    Image.new("RGBA", (70, 14), (255, 240, 230, 255)).save(d / "images" / "wick.png")
    sk = new_skeleton(width=260, height=260)
    sk.add_bone_world("ball", "root", 0, 0)
    sk.add_bone_world("cap", "ball", 40, 80, 90)
    sk.add_bone_world("wick", "cap", 40, 110, 0)
    for name, bone, x, y, w, h in (("shell", "ball", 0, 0, 200, 200), ("cap", "cap", 40, 95, 50, 40),
                                   ("wick", "wick", 75, 110, 70, 14)):
        sk.slots.append(Slot(name=name, bone=bone, attachment=name))
        wb = sk.world()[bone]
        lx, ly = wb.to_local(x, y)
        sk.set_attachment(name, name, RegionAttachment(x=round(lx, 2), y=round(ly, 2), rotation=-wb.rotation,
                                                       width=w, height=h))
    p = Project(d / "ball.json", sk)
    p.save()
    return p


# ------------------------------------------------------------------ sphere_spin
def test_render_turn_stays_round_and_starts_on_the_art():
    art = _ball_art(160)
    frames, span, info = sphere.render_turn(art, 80, 80, 80, frames=8, size=96, pad=4)
    assert len(frames) == 8 and span == pytest.approx(168)
    a0 = np.asarray(frames[0])[..., 3]
    for f in frames[1:]:
        assert np.abs(np.asarray(f)[..., 3].astype(int) - a0).max() <= 1      # a ball: the outline never changes
    c0 = np.asarray(frames[0])[..., :3].astype(int)
    assert np.abs(np.asarray(frames[2])[..., :3].astype(int) - c0).mean() > 8  # but the stripes travel round
    assert 60 <= info["period_deg"] <= 150


def test_sphere_spin_keys_a_real_turn(ball):
    res = sphere.sphere_spin(ball, ["shell"], "spin", start=0.2, duration=1.0, riders=["cap"], flip=["wick"],
                             glow=0.6, frames=12, size=128)
    sk = ball.data
    assert res["frames"] == 12 and (ball.images_dir / "spin" / "spin_11.png").exists()
    a = sk.animations["spin"]
    seq = a.attachments["default"]["spin body"]["fx"]["sequence"]
    assert seq[0].mode == "hold" and seq[0].index == 0 and seq[-1].index == 0      # one whole turn, back on frame 0
    assert len({k.index for k in seq}) == 12
    assert [(k.time, k.name) for k in a.slots["shell"]["attachment"]] == [(0.2, None), (1.2, "shell")]
    behind = [d for d in a.drawOrder if d.offsets]
    assert behind, "the cap must pass behind the ball"
    i_body = [s.name for s in sk.slots].index("spin body")
    moved = {o.slot: o.offset for o in behind[0].offsets}
    assert moved["spin body"] > 0 and i_body + moved["spin body"] > [s.name for s in sk.slots].index("wick") - 2
    assert a.drawOrder[-1].offsets is None                                         # back in front by the end
    cap_t = a.bones["cap"]["translate"]
    assert min(k.x for k in cap_t) < -60 and max(k.x for k in cap_t) > 0         # it swings round the side
    wick_s = a.bones["wick"]["scale"]
    assert min(getattr(k, "x", 1) for k in wick_s) < 0                            # the side wick mirrors past 90
    assert qa.validate(sk)["ok"]


def test_sphere_spin_reuses_frames_and_merges(ball):
    sphere.sphere_spin(ball, ["shell"], "a", 0, 0.5, frames=8, size=96)
    n = len(list((ball.images_dir / "spin").glob("*.png")))
    sk = ball.data
    sk.animations["b"] = sk.animations.get("b") or type(sk.animations["a"])()
    res = sphere.sphere_spin(ball, ["shell"], "b", 1.0, 0.5)
    assert res["reused"] and len(list((ball.images_dir / "spin").glob("*.png"))) == n
    with pytest.raises(ValueError, match="whole number"):
        sphere.sphere_spin(ball, ["shell"], "c", 0, 1, turns=0)


@needs_node
def test_sphere_spin_plays_in_spine_core(ball):
    sphere.sphere_spin(ball, ["shell"], "spin", 0, 0.6, riders=["cap"], flip=["wick"], frames=8, size=96)
    ball.save()
    assert runtime.load_check(ball)["ok"]


# ------------------------------------------------------------------ liquid_splat + shake
@pytest.fixture
def splash(ball):
    """Five painted blobs round the ball + a droplet, as a PSD import would leave them (regions on root)."""
    sk = ball.data
    rng = np.random.default_rng(2)
    names = []
    for i in range(5):
        ang = i * 2 * math.pi / 5
        w, h = 90, 50
        im = Image.new("RGBA", (w, h))
        ImageDraw.Draw(im).ellipse([2, 2, w - 3, h - 3], fill=tuple(int(c) for c in rng.integers(60, 255, 3)) + (255,))
        n = f"splash{i}"
        im.save(ball.images_dir / f"{n}.png")
        sk.slots.append(Slot(name=n, bone="root", attachment=n))
        sk.set_attachment(n, n, RegionAttachment(x=round(120 * math.cos(ang), 2), y=round(120 * math.sin(ang), 2),
                                                 width=w, height=h))
        names.append(n)
    Image.new("RGBA", (12, 18), (255, 60, 150, 255)).save(ball.images_dir / "drop.png")
    sk.slots.append(Slot(name="drop", bone="root", attachment="drop"))
    sk.set_attachment("drop", "drop", RegionAttachment(x=150, y=-40, width=12, height=18))
    ball.save()
    return names + ["drop"]


def test_liquid_splat_builds_a_radial_kit_and_keys_the_beats(ball, splash):
    sk = ball.data
    res = fx_splat.liquid_splat(ball, splash, "boom", at=0.5, center=[0, 0], drips=6, rays=8,
                                implode_bone="ball", implode_hide=["shell", "cap", "wick"])
    assert res["built"] and res["pieces"] == 6 and res["drips"] == 6 and res["rays"] == 8
    w = sk.world()
    for n in splash:
        b = w[sk.slot(n).bone]
        assert sk.slot(n).bone == f"splat {n}" and sk.slot(n).attachment is None       # hidden until the burst
        assert math.isclose(b.rotation % 360, math.degrees(math.atan2(b.y, b.x)) % 360, abs_tol=2)   # x = radial
    a = sk.animations["boom"]
    tr = a.bones["splat splash0"]["translate"]
    assert tr[0].x < 0 < tr[-1].x                                     # from the middle out past its painted spot
    sc = a.bones["splat splash0"]["scale"]
    assert sc[-1].x < 0.2 and sc[-1].y < 0.1                          # thinned away, not faded
    assert "rgba" not in a.slots["splash0"]
    assert a.bones["ball"]["scale"][-1].x == pytest.approx(0.03)      # imploded
    assert [k.name for k in a.slots["shell"]["attachment"]][-1] is None
    assert "fx" in [k.name for k in a.slots["splat blur"]["attachment"]]
    drip = a.bones["splat drip1"]["translate"]
    assert drip[-1].y < drip[len(drip) // 2].y                        # drips fall
    assert any(e.name == "sfx_explode" for e in a.events)
    assert set(res["ae_hint"]) == {"lens_flare", "shockwave", "bloom"}
    assert qa.validate(sk)["ok"]


def test_liquid_splat_reuses_and_clones_the_kit(ball, splash):
    fx_splat.liquid_splat(ball, splash, "a", at=0.3, center=[0, 0], drips=4, rays=4)
    res = fx_splat.liquid_splat(ball, splash, "b", at=1.0, prefix="c1 ", offset=(0, -500))
    sk = ball.data
    assert not res["built"]
    w = sk.world()
    assert w["c1 splat"].y == pytest.approx(w["splat"].y - 500)
    assert sk.has_slot("c1 splash3") and sk.has_slot("c1 splat drip4")
    assert sk.attachment("c1 splash3", "fx").path == "splash3"        # shares the artist's image
    assert "c1 splat splash3" in sk.animations["b"].bones
    assert qa.validate(sk)["ok"]


@needs_node
def test_liquid_splat_plays_in_spine_core(ball, splash):
    fx_splat.liquid_splat(ball, splash, "boom", at=0.4, center=[0, 0], drips=4, rays=4, implode_bone="ball")
    ball.save()
    assert runtime.load_check(ball)["ok"]


def test_shake_grows_and_returns_to_rest(ball):
    res = fx_splat.shake(ball, "rumble", "ball", 0.2, 1.0, amplitude=30, rotation=12)
    tr = ball.data.animations["rumble"].bones["ball"]["translate"]
    assert res["jumps"] >= 10
    mags = [math.hypot(k.x, k.y) for k in tr]
    assert mags[0] == 0 and mags[-1] == 0 and max(mags[-5:]) > max(mags[1:5])


# ------------------------------------------------------------------ After Effects helpers
def test_new_templates_and_safe_wrapper(tmp_path):
    t = ae_templates.list_templates()
    assert {"surface_sweep", "lens_flare"} <= set(t)
    r = ae_templates.build_script("lens_flare", {"save_as": str(tmp_path / "x.aep"), "comp": "fl"}, tmp_path)
    src = open(r["script"], encoding="utf-8").read()
    assert "CLAUDE_ERR lens_flare" in src and "app.open(__orig)" in src
    assert src.index("var __r = (function") < src.index("app.project.save(") < src.index("app.open(__orig)")
    assert '"Lens Type"' in src                                     # by display name, not a version-dependent index


def test_check_aep_reads_names_and_errors(tmp_path):
    def chunk(s):
        b = s.encode("utf-8")
        return b"Utf8" + struct.pack(">I", len(b)) + b + (b"\0" if len(b) % 2 else b"")
    f = tmp_path / "p.aep"
    f.write_bytes(b"RIFX\0\0\0\0Egg!" + chunk("cb_flare_v3") + chunk("ADBE Glo2") +
                  chunk("CLAUDE_ERR lens_flare: Error: boom @12"))
    r = ae_bridge.check_aep(f, ["cb_flare_v3", "missing"])
    assert r["found"] == {"cb_flare_v3": True, "missing": False}
    assert r["errors"] == ["CLAUDE_ERR lens_flare: Error: boom @12"]


def _light_frames(d, n=4, size=(40, 40)):
    d.mkdir()
    for i in range(n):
        rgb = np.full((size[1], size[0], 3), 0.6, np.float32)
        Image.fromarray(np.round(rgb * 255).astype(np.uint8)).save(d / f"f_{i:05d}.png")
    return d


def test_feather_and_anchor(ball, tmp_path):
    d = _light_frames(tmp_path / "fr")
    res = ae_bridge.fx_to_spine(ball, "fl", frames_dir=str(d), fps=30, mode="additive", feather=0.2,
                                anchor=[0.25, 0.25], scale=2.0)
    px = np.asarray(ball.image("ae/fl_00"))[..., 3]
    assert px[0].max() == 0 and px[20, 20] > 100                  # edges faded out, middle kept
    att = ball.data.attachment(res["slot"], "fx")
    assert (att.x, att.y) == (pytest.approx(20), pytest.approx(-20))   # (0.25, 0.25) of a 40 px comp at scale 2


def test_deform_like_copies_the_arts_weights(ball, tmp_path):
    sk = ball.data
    sk.add_bone_world("bulge", "ball", 0, 0)
    rig_mesh(ball, "shell", bones=["ball", "bulge"])
    d = _light_frames(tmp_path / "fr2", size=(60, 60))
    res = ae_bridge.fx_to_spine(ball, "sweep", frames_dir=str(d), fps=30, mode="additive", scale=3.0,
                                deform_like=["shell"], parent="ball")
    att = sk.attachment(res["slot"], "fx")
    assert isinstance(att, MeshAttachment) and att.sequence.count == 4
    used = {bi for inf in decode_weighted(att.vertices, len(att.uvs) // 2) for bi, *_ in inf}
    assert used <= {sk.bone_index("ball"), sk.bone_index("bulge")} and len(used) == 2
    assert qa.validate(sk)["ok"]


# ------------------------------------------------------------------ PSD import fixes
def test_psd_names_lose_control_characters():
    assert psd_mod._clean("\x7fsplash-top left") == ("splash-top left", [])


def test_psd_faint_stray_alpha_does_not_widen_a_layer(tmp_path):
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer
    psd = PSDImage.new("RGBA", (300, 200))
    a = np.zeros((200, 300, 4), np.uint8)
    a[..., 3] = 3                                                  # a soft brush's faint haze over the whole canvas
    a[50:90, 100:160] = [255, 0, 0, 255]
    psd.append(PixelLayer.frompil(Image.fromarray(a, "RGBA"), psd, name="shell", top=0, left=0))
    f = tmp_path / "s.psd"
    psd.save(f)
    out = psd_mod.import_psd(str(f), str(tmp_path / "o"))
    p = Project.open(out["project"])
    assert p.image("shell").size == (60, 40)
    att = p.data.attachment("shell")
    assert (att.x, att.y) == (pytest.approx(130 - 150), pytest.approx(100 - 70))
