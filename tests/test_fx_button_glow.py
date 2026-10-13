"""Round spin-button light (fx_button_glow): hover_pulse, press_flash, bloom_collar, anamorphic_streak, rainbow_halo,
glitter_halo and the spin_button_glow bundle. Measured timings stay put at default params, colours come from params,
the stop modes behave, the squash goes through a carrier, and everything plays in the spine-core runtime."""
import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_button_glow as G, fx_recipes as R, qa, runtime
from claude_spine.ir import Bone, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node

NAMES = ["hover_pulse", "press_flash", "bloom_collar", "anamorphic_streak", "rainbow_halo", "glitter_halo"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 680, 404))


def _alpha_at(keys, t):
    ts = [k.time for k in keys]
    al = [int(k.color[6:8], 16) / 255 for k in keys]
    return float(np.interp(t, ts, al))


def _slot_keys(proj, anim, slot):
    return proj.data.animations[anim].slots[slot]["rgba"]


def test_registered_without_collisions():
    from claude_spine import ae_templates
    for n in NAMES:
        assert n in R.RECIPES and R.RECIPES[n]["roles"]
        assert n not in ae_templates.list_templates()
    assert "spin_button_glow" in R.BUNDLES and "spin_button_glow" in R.list_recipes()


@pytest.mark.parametrize("name", NAMES + ["spin_button_glow"])
@pytest.mark.parametrize("stop", ["fade", "quick"])
def test_each_applies_validates_and_plays(proj, name, stop):
    opts = {} if name in ("hover_pulse", "glitter_halo") else {"stop": stop}
    res = R.apply(proj, name, x=-19.5, y=-29.5, options=opts)
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]
    assert res["slots"]
    if runtime.available():
        proj.save()
        dump = runtime.run(proj, animations=[res["animation"]], fps=15, geometry=True)
        assert dump.get("ok", True) and not dump.get("problems")
        assert any(f["draws"] for f in dump["animations"][res["animation"]]["frames"])


@needs_node
@pytest.mark.parametrize("name", NAMES)
def test_colour_param_changes_the_drawn_colour(tmp_path, name):
    cols = []
    for col in ("FF0000", "00FF00"):
        p = Project(tmp_path / f"{name}_{col}.json", new_skeleton("t", 680, 404))
        res = R.apply(p, name, color=col)
        p.save()
        dump = runtime.run(p, animations=[res["animation"]], fps=10, geometry=True)
        f = max(dump["animations"][res["animation"]]["frames"], key=lambda f: sum(d["color"][3] for d in f["draws"]))
        lit = [d["color"] for d in f["draws"] if d["color"][3] > 0.01]
        cols.append(np.mean([c[:3] for c in lit], 0))
    if name == "rainbow_halo":      # a tint on a coloured picture: still follows the parameter
        assert cols[0][0] > cols[0][1] and cols[1][1] > cols[1][0]
    else:
        assert cols[0][0] > cols[1][0] and cols[1][1] > cols[0][1]


def test_measured_timing_at_default_params(proj):
    """The gold family snaps in over frames 1..5 after the flash and the spectrum ring reaches r 183 at f+5."""
    res = R.apply(proj, "bloom_collar", start=1.0)
    light = res["slots_by_part"]["collar"]
    k = _slot_keys(proj, res["animation"], light)
    F = 1 / 30
    assert _alpha_at(k, 1.0) == 0 and 0.2 < _alpha_at(k, 1 + 5 * F) / 0.26 < 1.05
    assert _alpha_at(k, 1 + 2 * F) == pytest.approx(0.3 * 0.26, abs=0.01)
    res2 = R.apply(proj, "rainbow_halo", start=1.0)
    sc = proj.data.animations[res2["animation"]].bones[next(b for b in proj.data.animations[res2["animation"]].bones)]["scale"]
    at5 = next(kk for kk in sc if abs(kk.time - (1 + 5 * F)) < 1e-3)
    assert at5.x * 183 == pytest.approx(183, abs=0.5)
    assert sc[-1].x * 183 == pytest.approx(196, abs=0.5)


def test_stop_modes(proj):
    a = R.apply(proj, "anamorphic_streak", name="a", options={"stop": "fade"})
    b = R.apply(proj, "anamorphic_streak", name="b", options={"stop": "quick"})
    c_ = R.apply(proj, "anamorphic_streak", name="c", options={"stop": "hold"})
    assert a["duration"] == pytest.approx(G.HOLD + 17 / 30, abs=1e-3)
    assert b["duration"] == pytest.approx(G.HOLD + G.L3, abs=1e-3)
    assert c_["duration"] == pytest.approx(G.HOLD, abs=1e-3)
    q = R.apply(proj, "bloom_collar", name="q", options={"stop": "quick"})
    assert "afterglow" in q["slots_by_part"]
    with pytest.raises(ValueError, match="stop"):
        R.apply(proj, "rainbow_halo", options={"stop": "later"})


def test_wash_is_normal_blend_and_optional(proj):
    res = R.apply(proj, "bloom_collar", name="w")
    blends = {s.name: s.blend for s in proj.data.slots}
    assert blends[res["slots_by_part"]["wash"]] == "normal"
    assert all(blends[s] == "additive" for k, s in res["slots_by_part"].items() if k != "wash")
    res2 = R.apply(proj, "anamorphic_streak", name="nw", options={"wash": False})
    assert "wash" not in res2["slots_by_part"] and all(proj.data.slot(s).blend == "additive" for s in res2["slots"])


def test_press_squashes_your_button_through_a_carrier(proj):
    proj.data.bones.append(Bone(name="btn", parent="root", x=-19.5, y=-29.5))
    proj.data.add_slot(Slot(name="btn_art", bone="btn"))
    res = R.apply(proj, "press_flash", x=-19.5, y=-29.5, options={"button": "btn"})
    assert res["carrier"] and proj.data.bone("btn").parent == res["button_bone"]
    sc = proj.data.animations[res["animation"]].bones[res["button_bone"]]["scale"]
    lo = min(k.y if k.y is not None else 1 for k in sc)
    assert lo == pytest.approx(0.903, abs=0.002) and sc[-1].x == pytest.approx(1.0)
    # the flash ring stays on the rim (not on the squashed bone); the face glow squashes with the button
    parts = res["slots_by_part"]
    assert proj.data.slot(parts["rim_hot"]).bone == res["group_bone"]
    assert proj.data.slot(parts["face"]).bone == res["button_bone"]
    assert qa.validate(proj.data)["ok"]


def test_disc_art_role_rides_the_squash(proj, tmp_path):
    f = tmp_path / "disc.png"
    Image.new("RGBA", (64, 64), (40, 120, 220, 255)).save(f)
    res = R.apply(proj, "press_flash", art={"disc": str(f)})
    s = proj.data.slot(res["slots_by_part"]["disc"])
    assert s.blend == "normal" and s.bone == res["button_bone"] and "disc" in res["art"]
    att = proj.data.attachment(s.name, "fx")
    assert att.width == pytest.approx(176)


def test_hover_pulse_loops_exactly(proj):
    res = R.apply(proj, "hover_pulse")
    an = proj.data.animations[res["animation"]]
    for slot, tl in an.slots.items():
        ks = tl["rgba"]
        if slot != res["slots_by_part"]["pulse"]:
            assert ks[0].color == ks[-1].color, slot
    pulse = an.slots[res["slots_by_part"]["pulse"]]["rgba"]
    assert int(pulse[-1].color[6:8], 16) == 0 and int(pulse[0].color[6:8], 16) > 100   # born bright at the rim, gone at the end
    sc = an.bones[next(iter(an.bones))]["scale"]
    assert sc[0].x * 60 == pytest.approx(84, abs=0.1) and sc[-1].x * 60 == pytest.approx(114, abs=0.1)


def test_radius_scales_every_part(tmp_path):
    w = []
    for r in (88.0, 44.0):
        p = Project(tmp_path / f"r{r}.json", new_skeleton("t", 680, 404))
        res = R.apply(p, "rainbow_halo", options={"radius": r})
        w.append(p.data.attachment(res["slots"][0], "fx").width)
    assert w[1] == pytest.approx(w[0] / 2)


def test_bundle_orders_and_times_its_members(proj):
    res = R.apply(proj, "spin_button_glow", start=0.5, options={"hold": 1.0, "stop": "quick"})
    assert res["parts"] == ["bloom_collar", "anamorphic_streak", "rainbow_halo", "glitter_halo", "press_flash"]
    order = [s.name for s in proj.data.slots]
    press = [s for s in res["slots"] if s.startswith("fx_press_flash")]
    bloom = [s for s in res["slots"] if s.startswith("fx_bloom_collar")]
    assert min(order.index(s) for s in press) > max(order.index(s) for s in bloom), "the press light is in front"
    assert res["flash_at"] == pytest.approx(0.5 + 2 / 30) and res["stop_at"] == pytest.approx(0.5 + 2 / 30 + 1.0)
    with pytest.raises(ValueError, match="unknown option"):
        R.apply(proj, "spin_button_glow", options={"colour": "red"})


def test_pictures_are_procedural_and_sized():
    for name, fn in G.PICS.items():
        im = fn()
        assert im.mode == "RGBA" and max(im.size) == G.SIZE[name]
        a = np.asarray(im)[..., 3]
        assert a.max() > 100 and a[0, 0] == 0, name                 # lit somewhere, transparent corner
    sp = np.asarray(G.tex_spectrum(), float)
    lit = sp[..., 3] > 60
    assert all(np.std(sp[lit][:, ch]) > 40 for ch in range(3)), "a spectrum: every channel varies across the ring"
