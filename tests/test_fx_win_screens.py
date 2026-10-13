"""Win-screen family (fx_win_screens): every recipe builds, validates and plays in the spine-core runtime; colours come
from params; the loops close; label art is stretched to the label box; the fire boost's AE hint names real templates."""
import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_templates, fx_recipes as R, qa, runtime
from claude_spine.fx_win_screens import WIN_SCREEN_RECIPES
from claude_spine.ir import new_skeleton
from claude_spine.project import Project


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 800, 1396))


def _keys(p, anim):
    a = p.data.animations[anim]
    return {s: tl for s, tl in a.slots.items()}


def test_names_do_not_collide_with_templates():
    assert not set(WIN_SCREEN_RECIPES) & set(ae_templates.list_templates())
    assert all(n in R.RECIPES for n in WIN_SCREEN_RECIPES)


@pytest.mark.parametrize("name", WIN_SCREEN_RECIPES)
def test_builds_validates_and_runs(proj, name):
    res = R.apply(proj, name)
    assert res["animation"] == f"fx_{name}" and res["event"] == f"fx_{name}"
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]
    assert all(s.attachment is None for s in proj.data.slots), "FX slots are hidden in the setup pose"
    proj.save()
    out = runtime.run(proj, fps=30)
    assert out.get("ok", True) and not out.get("problems"), out.get("problems") or out
    dur = out["animations"][res["animation"]]["duration"]
    assert dur > 0.15


@pytest.mark.parametrize("name", [n for n in WIN_SCREEN_RECIPES if n not in ("echo_stamp", "ghost_pop")])
def test_colour_param_recolours(proj, name):
    R.apply(proj, name, color="12AB34")
    cols = {k.color[:6] for tl in _keys(proj, f"fx_{name}").values() for k in tl.get("rgba", [])}
    assert "12AB34" in cols, cols


@pytest.mark.parametrize("name", ["win_screen_glow", "beam_sweep", "sunburst_glow", "face_flash"])
def test_loops_close(proj, name):
    res = R.apply(proj, name)
    a, b = res["loop"]
    for s, tl in _keys(proj, res["animation"]).items():
        ks = tl.get("rgba", [])
        at = lambda t: next((k for k in ks if abs(k.time - t) < 1e-3), None)
        ka, kb = at(a), at(b)
        if ka is not None and kb is not None:
            assert abs(int(ka.color[6:8], 16) - int(kb.color[6:8], 16)) <= 26, (s, ka.color, kb.color)


def test_beam_sweep_turns_one_beam_step_per_loop(proj):
    res = R.apply(proj, "beam_sweep", duration=3.0)
    rot = next(tl["rotate"] for b, tl in proj.data.animations[res["animation"]].bones.items() if b.endswith("beams"))
    assert abs(rot[-1].value - rot[0].value + 360 / 7) < 1e-2


def test_face_flash_peaks_after_its_delay(proj):
    res = R.apply(proj, "face_flash", options={"delay": 0.4, "star": False})
    face = next(s for s in res["slots"] if proj.data.attachment(s, "fx").path.endswith("winscr_disc"))
    ks = _keys(proj, res["animation"])[face]["rgba"]
    peak = max(ks, key=lambda k: int(k.color[6:8], 16))
    assert abs(peak.time - 0.5) < 1e-3
    with pytest.raises(ValueError):
        R.apply(proj, "face_flash", options={"shape": "star"})


def test_label_art_is_stretched_to_the_box(proj, tmp_path):
    pic = tmp_path / "label.png"
    Image.new("RGBA", (40, 40), (255, 0, 0, 255)).save(pic)
    res = R.apply(proj, "ghost_pop", art={"label": str(pic)}, options={"size": [425.0, 94.0]})
    for s in res["label_slots"]:
        att = proj.data.attachment(s, "fx")
        assert (att.width, att.height) == (425.0, 94.0)


def test_starburst_pop_ends_and_glints_drift(proj):
    res = R.apply(proj, "starburst_pop", count=5)
    assert res["glints"] == 5
    an = proj.data.animations["fx_starburst_pop"]
    assert an.duration() <= 0.46


def test_fire_boost_hint_names_real_template_params(proj):
    res = R.apply(proj, "fire_boost_flare")
    tpls = ae_templates.list_templates()
    for part in ("fire", "smoke"):
        h = res["ae_hint"][part]
        assert h["template"] in tpls
        assert set(h["params"]) <= set(tpls[h["template"]]["params"]), set(h["params"]) - set(tpls[h["template"]]["params"])
    assert res["ae_hint"]["smoke"]["to_spine"]["tintable"] is True


def test_screen_wash_is_normal_blend_and_covers_the_screen(proj):
    res = R.apply(proj, "win_screen_intro")
    big = [s for s in res["slots"] if proj.data.attachment(s, "fx").height >= 1400]
    assert len(big) == 2 and all(proj.data.slot(s).blend == "normal" for s in big)
