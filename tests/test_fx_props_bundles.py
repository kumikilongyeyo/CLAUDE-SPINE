"""Prop bundles: members chained on each other's EVENTS, shared options reach every member that takes them, steps /
skip, magic_vessel loops seamlessly over four idle cycles."""
import pytest

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node
from PIL import Image

BUNDLES = ("bonus_chest_reveal", "collect_into_prop", "pinata_style_break", "magic_vessel")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def ev(p, anim, name):
    return sorted(e.time for e in p.data.animations[anim].events if e.name == name)


def chest(tmp_path):
    p = Project(tmp_path / "c.json", new_skeleton("c", 720, 720))
    p.data.bones += [Bone(name="chest", parent="root"), Bone(name="lid", parent="chest", x=-110, y=80)]
    for n, b in (("body", "chest"), ("top", "lid")):
        p.write_image(n, Image.new("RGBA", (64, 64), (200, 120, 60, 255)))
        p.data.add_slot(Slot(name=n, bone=b, attachment=n))
        p.data.set_attachment(n, n, RegionAttachment(path=n, width=64, height=64))
    return p


@pytest.mark.parametrize("name", BUNDLES)
def test_each_bundle_builds_and_validates(proj, name):
    res = R.apply(proj, name)
    assert res["slots"] and res["end"] > 0 and qa.validate(proj.data)["ok"]
    assert ev(proj, res["animation"], f"fx_{name}_end") == [pytest.approx(res["end"])]
    assert name in R.list_recipes()


def test_chest_reveal_chains_on_events_and_reaches_the_artists_bones(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "bonus_chest_reveal", options={"prop": "chest", "lid": "lid", "pivot": [-110, 80]})
    a = res["animation"]
    assert res["parts"] == ["prop_peek", "prop_shake", "prop_open", "coin_fountain", "prop_upgrade"]
    assert ev(p, a, "fx_prop_shake")[0] > ev(p, a, "prop_peek_shut")[0]
    assert ev(p, a, "fx_prop_open")[0] == pytest.approx(ev(p, a, "prop_shake_release")[0])
    assert ev(p, a, "fx_coin_fountain")[0] == pytest.approx(ev(p, a, "prop_open")[0])
    assert ev(p, a, "fx_prop_upgrade")[0] > ev(p, a, "prop_open_settled")[0]
    an = p.data.animations[a]
    assert "chest" not in an.bones and "lid" not in an.bones, "only carriers are keyed"
    assert any(b.startswith("fx_") for b in an.bones)


def test_collect_counts_one_tick_per_item(proj):
    res = R.apply(proj, "collect_into_prop", options={"steps": {"prop_absorb": {"sources": [[-200, 50], [200, 50], [0, -200], [150, -150], [-150, -150]]}}})
    a = res["animation"]
    hits = ev(proj, a, "prop_absorb_hit")
    assert len(hits) == 5 and len(ev(proj, a, "counter_tick")) == 5
    assert ev(proj, a, "fx_counter_plate")[0] == pytest.approx(hits[0])
    assert ev(proj, a, "fx_prop_overflow")[0] > hits[-1]


def test_pinata_break_hits_three_times_then_shatters(proj):
    res = R.apply(proj, "pinata_style_break")
    a = res["animation"]
    hits = ev(proj, a, "prop_hit")
    assert len(hits) == 3 and ev(proj, a, "prop_crack")[0] > hits[-1]
    assert ev(proj, a, "fx_pinata_hit")[0] == pytest.approx(ev(proj, a, "prop_shatter")[0])


def test_magic_vessel_is_four_idle_cycles_and_skip_and_steps_work(proj, tmp_path):
    res = R.apply(proj, "magic_vessel")
    assert res["end"] == pytest.approx(4 * R.RECIPES["prop_idle"]["duration"], abs=1e-3)
    assert "liquid_slosh" not in res["parts"], "no liquid bone: no slosh"
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 720))
    r2 = R.apply(q, "magic_vessel", options={"skip": ["smoke_wisp"], "steps": {"liquid_bubble": {"size": 30.0}}})
    assert r2["parts"] == ["prop_idle", "liquid_bubble"]
    with pytest.raises(ValueError, match="unknown option"):
        R.apply(q, "magic_vessel", name="x", options={"nope": 1})


@needs_node
@pytest.mark.parametrize("name", BUNDLES)
def test_bundles_play_in_the_runtime(proj, name):
    res = R.apply(proj, name)
    proj.save()
    d = runtime.run(proj, animations=[res["animation"]], fps=10)
    assert not d.get("problems")
