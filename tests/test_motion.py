import numpy as np
import pytest

from claude_spine import fx, juice, qa
from claude_spine.ir import Key


def _value_at(keys, t):
    ks = sorted(keys, key=lambda k: k.time)
    last = ks[-1]
    return {**(last.model_extra or {})} if t >= last.time else None


@pytest.mark.parametrize("clip", juice.CONTRACT + juice.EXTRAS)
def test_every_juice_clip_validates(symbol, clip):
    juice.apply(symbol, [clip])
    v = qa.validate(symbol.data)
    assert v["ok"], v["errors"]


def test_contract_and_juice_bones(symbol):
    res = juice.apply(symbol)
    assert set(res["clips"]) == set(juice.CONTRACT)
    sk = symbol.data
    for a in juice.CONTRACT:
        assert set(sk.animations[a].bones) <= {"juice_ground", "juice_core"}


def test_one_shots_end_on_setup_pose(symbol):
    juice.apply(symbol, ["land", "win", "scatter_trigger", "flip", "wild_expand"])
    rest = {"translatey": ("value", 0), "translatex": ("value", 0), "rotate": ("value", 0)}
    for an in ["land", "win", "scatter_trigger", "flip", "wild_expand"]:
        for bone, tls in symbol.data.animations[an].bones.items():
            for tl, ks in tls.items():
                last = ks[-1].model_extra
                if tl == "scale":
                    assert last.get("x", 1) == 1 and last.get("y", 1) == 1, (an, bone, tl, last)
                elif tl in rest:
                    assert last.get("value", 0) == 0, (an, bone, tl, last)


def test_loops_are_seamless(symbol):
    juice.apply(symbol, ["idle", "win_loop", "anticipation"])
    for an in ["idle", "win_loop", "anticipation"]:
        for bone, tls in symbol.data.animations[an].bones.items():
            for tl, ks in tls.items():
                a, b = ks[0].model_extra, ks[-1].model_extra
                assert a == b, (an, bone, tl, a, b)


def test_juice_does_not_move_setup(symbol):
    before = juice.setup_bounds(symbol)
    juice.apply(symbol)
    after = juice.setup_bounds(symbol)
    assert np.allclose(before, after, atol=1e-3)


@pytest.mark.parametrize("preset", ["explosion", "shockwave", "coin_burst", "coin_shower", "ripple",
                                    "glow_pulse", "sparkle"])
def test_fx_presets_validate(symbol, preset):
    res = fx.generate(symbol, preset)
    sk = symbol.data
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    assert res["event"] in sk.events
    for s in res["slots"]:
        assert sk.slot(s).attachment is None  # hidden in setup
    assert (symbol.images_dir / "fx").exists()


def test_fx_merges_into_existing_animation(symbol):
    juice.apply(symbol, ["win"])
    n_bones = len(symbol.data.animations["win"].bones)
    fx.generate(symbol, "coin_burst", into="win")
    assert len(symbol.data.animations["win"].bones) > n_bones
    assert "juice_core" in symbol.data.animations["win"].bones


def test_shine_sweep_is_clipped_to_the_part(symbol):
    res = fx.generate(symbol, "shine_sweep", slot="gem")
    sk = symbol.data
    clip = sk.attachment(res["clip_slot"], "clip")
    assert clip.end == res["streak_slot"]
    assert sk.slot_index(res["clip_slot"]) == sk.slot_index("gem") + 1
    assert clip.vertexCount <= 32
    assert qa.validate(sk)["ok"]


def test_ripple_loop_matches_at_ends(symbol):
    fx.generate(symbol, "ripple")
    a = symbol.data.animations["ripple"]
    for bone, tls in a.bones.items():
        ks = tls["scale"]
        assert ks[0].model_extra == ks[-1].model_extra
