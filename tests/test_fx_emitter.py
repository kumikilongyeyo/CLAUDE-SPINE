"""fx_emitter: Unity-style particles simulated and baked into Spine keys."""
from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_emitter as E, qa, runtime
from claude_spine.ir import new_skeleton
from claude_spine.project import Project
from conftest import needs_node


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _at(keys, t, fields):
    """Linear value of a timeline at t (what the runtime does between linear keys)."""
    ts = [k.time for k in keys]
    vals = [[getattr(k, f) if getattr(k, f, None) is not None else 0.0 for f in fields] for k in keys]
    return [float(np.interp(t, ts, [v[i] for v in vals])) for i in range(len(fields))]


def _shown(keys, t):
    cur = None
    for k in keys:
        if k.time <= t + 1e-6:
            cur = k.name
    return cur


@pytest.mark.parametrize("name", sorted(E.presets()))
def test_every_preset_bakes_valid_and_within_its_cap(proj, name):
    res = E.bake(proj, preset=name, name=name)
    assert qa.validate(proj.data)["ok"]
    spec = E.resolve(name)
    subs = sum(int(s["emitter"].get("max_particles", 40)) if isinstance(s["emitter"], dict) else 40
               for s in spec["sub_emitters"])
    assert res["pool_slots"] <= int(spec["max_particles"]) + subs
    assert res["emitted"] > 0 and res["keys"] > 0 and res["peak_alive"] <= res["pool_slots"]
    if spec["loop"]:
        assert res["duration"] == pytest.approx(spec["duration"])


@pytest.mark.parametrize("name", [n for n, v in sorted(E.presets().items()) if v.get("loop")])
def test_loops_close_exactly(proj, name):
    res = E.bake(proj, preset=name, name=name)
    anim, D = proj.data.animations[res["animation"]], res["duration"]
    crossing = 0
    for slot, tls in anim.slots.items():
        at0, atD = _shown(tls["attachment"], 0.0), _shown(tls["attachment"], D)
        assert at0 == atD, slot                       # shown on both sides of the loop point, or on neither
        if at0:
            crossing += 1
            bone = proj.data.slot(slot).bone
            for tl, f in (("translate", ("x", "y")), ("rotate", ("value",)), ("scale", ("x", "y"))):
                a, b = _at(anim.bones[bone][tl], 0.0, f), _at(anim.bones[bone][tl], D, f)
                assert a == pytest.approx(b, abs=0.05), (slot, tl)
    assert crossing > 0                               # a steady loop always has particles crossing the seam


def test_the_cap_drops_and_reports(proj):
    res = E.bake(proj, emitter={"max_particles": 5, "emission": {"bursts": [{"count": 20}]}})
    assert res["pool_slots"] == 5 and res["dropped"] == 15 and "dropped" in res["warnings"][0]


def test_slots_are_reused_one_particle_after_another(proj):
    res = E.bake(proj, emitter={"lifetime": 0.2, "duration": 2.0, "emission": {"rate": 10, "bursts": []},
                                "max_particles": 10})
    assert res["emitted"] == pytest.approx(20, abs=2) and res["pool_slots"] <= 4 and res["dropped"] == 0


def test_unknown_modules_and_settings_are_refused(proj):
    with pytest.raises(ValueError, match="unknown module"):
        E.bake(proj, emitter={"gravty": 100})
    with pytest.raises(ValueError, match="shape: unknown setting"):
        E.bake(proj, emitter={"shape": {"radious": 5}})
    with pytest.raises(ValueError, match="no emitter preset"):
        E.bake(proj, preset="nope")
    with pytest.raises(ValueError, match="max_particles"):
        E.bake(proj, emitter={"max_particles": 0})


def test_same_seed_same_bake_other_seed_differs(tmp_path):
    def run(seed, tag):
        p = Project(tmp_path / f"{tag}.json", new_skeleton(tag, 720, 720))
        res = E.bake(p, preset="sparks_burst", emitter={"seed": seed})
        bone = p.data.slot(res["slots"][0]).bone
        return [(k.time, k.x, k.y) for k in p.data.animations[res["animation"]].bones[bone]["translate"]]
    assert run(3, "a") == run(3, "b")
    assert run(3, "c") != run(4, "d")


def test_gravity_and_drag_shape_the_motion(proj):
    res = E.bake(proj, emitter={"speed": 400, "gravity": 1000, "drag": 0, "lifetime": 0.8, "rotation": 0,
                                "shape": {"type": "point", "angle": 90, "spread": 0},
                                "emission": {"bursts": [{"count": 1}]}, "alpha_over_lifetime": 1.0})
    bone = proj.data.slot(res["slots"][0]).bone
    ys = [(k.time, k.y) for k in proj.data.animations[res["animation"]].bones[bone]["translate"]]
    top = max(y for _, y in ys)
    assert top == pytest.approx(400 ** 2 / (2 * 1000), rel=0.03)      # v^2 / 2g
    assert ys[-1][1] < 0                                             # and back down past the start


def test_custom_png_and_flipbook_textures(proj, tmp_path):
    pic = tmp_path / "coin.png"
    Image.new("RGBA", (40, 40), (255, 200, 0, 255)).save(pic)
    res = E.bake(proj, preset="coin_fountain", emitter={"texture": str(pic)}, name="coins")
    att = proj.data.attachment(res["slots"][0], "fx")
    assert att.path.startswith("fx/art_") and (proj.images_dir / f"{att.path}.png").exists()
    frames = tmp_path / "flip"
    frames.mkdir()
    for i in range(6):
        Image.new("RGBA", (32, 64), (255, 40 * i, 0, 255)).save(frames / f"f_{i:03d}.png")
    res = E.bake(proj, preset="smoke_puffs", emitter={"texture": {"frames": str(frames), "fps": 12,
                                                                  "random_start": True}}, name="flip")
    att = proj.data.attachment(res["slots"][0], "fx")
    assert att.sequence.count == 6 and att.height == pytest.approx(2 * att.width)
    seq = proj.data.animations[res["animation"]].attachments["default"][res["slots"][0]]["fx"]["sequence"]
    assert seq and seq[0].mode == "loop" and seq[0].delay == pytest.approx(1 / 12, abs=1e-4)
    assert qa.validate(proj.data)["ok"]


def test_sub_emitters_get_their_own_pool_at_the_parent_death(proj):
    res = E.bake(proj, preset="firework")
    spec = E.resolve("firework")
    assert res["dropped"] == 0 and res["emitted"] == 1 + 36
    assert res["pool_slots"] > int(spec["max_particles"])          # the children did not squeeze into the parent's


def test_moving_emitter_leaves_a_trail(proj):
    res = E.bake(proj, preset="comet_trail", emitter={"speed": 0, "drag": 0})
    anim = proj.data.animations[res["animation"]]
    firsts = sorted((k[0].time, k[0].x) for k in (anim.bones[proj.data.slot(s).bone]["translate"] for s in res["slots"]))
    assert firsts[-1][1] > firsts[0][1] + 150                      # later births sit further along the path


def test_curves_and_gradients():
    assert E._curve([[0, 0], [0.5, 1], [1, 0]], 0.25) == pytest.approx(0.5)
    assert E._curve({"min": 0.0, "max": [[0, 2], [1, 2]]}, 0.3, 0.5) == pytest.approx(1.0)
    assert E._gradient([[0, "000000"], [1, "FFFFFF"]], 0.5) == pytest.approx((0.5, 0.5, 0.5))
    with pytest.raises(ValueError):
        E._start("lots", np.random.default_rng(0))


def test_user_presets_save_and_win(tmp_path, monkeypatch, proj):
    monkeypatch.setenv("CLAUDE_SPINE_PRESETS", str(tmp_path / "mine"))
    path = E.save_preset("blue_sparks", E.resolve("sparks_burst", {"color": "4080FF"}), "my sparks")
    saved = json.loads(open(path).read())
    assert saved["doc"] == "my sparks" and saved["color"] == "4080FF"
    assert E.presets()["blue_sparks"]["_origin"] == "user"
    res = E.bake(proj, preset="blue_sparks")
    assert res["emitted"] == 28


def test_mcp_tool_lists_and_bakes(tmp_path):
    from claude_spine.server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "fx_emitter" in names
    from claude_spine.tools_emitter import fx_emitter
    listing = fx_emitter()
    assert "sparks_burst" in listing["presets"] and "emission" in listing["modules"]
    p = Project(tmp_path / "m.json", new_skeleton("m", 720, 720))
    p.save()
    out = fx_emitter(str(p.path), preset="star_twinkle")
    assert out["loop"] and "validation_errors" not in out


@needs_node
def test_loop_seam_in_the_spine_runtime(proj):
    res = E.bake(proj, preset="embers_rise")
    proj.save()
    d = runtime.run(proj, animations=[res["animation"]], fps=1 / res["duration"], geometry=True)
    fr = d["animations"][res["animation"]]["frames"]
    sig = lambda f: sorted((dr["slot"], tuple(np.round(dr["v"], 0)), tuple(np.round(dr["color"], 2)))  # noqa: E731
                           for dr in f["draws"])
    assert fr[0]["draws"] and sig(fr[0]) == sig(fr[-1])
