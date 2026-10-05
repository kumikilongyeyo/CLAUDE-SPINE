from claude_spine import qa
from claude_spine.ir import MeshAttachment, Slot
from claude_spine.mesh import rig_mesh
from claude_spine.timeline import AnimBuilder


def test_clean_projects_validate(character, symbol):
    assert qa.validate(character.data)["ok"]
    assert qa.validate(symbol.data)["ok"]


def test_catches_broken_references(symbol):
    sk = symbol.data
    sk.slots.append(Slot(name="ghost", bone="nope"))
    AnimBuilder(sk, "a").bone("root", "rotate", [(0, 0), (1, 10)])
    sk.animations["a"].bones["missing"] = sk.animations["a"].bones["root"]
    errs = qa.validate(sk)["errors"]
    assert any("missing bone 'nope'" in e for e in errs)
    assert any("missing bone 'missing'" in e for e in errs)


def test_catches_bad_weights_and_uvs(arm):
    rig_mesh(arm, "arm")
    att = arm.data.attachment("arm")
    att.vertices[4] = 0.5  # first influence weight of vertex 0
    att.uvs[0] = 1.2
    errs = qa.validate(arm.data)["errors"]
    assert any("weights sum" in e for e in errs)
    assert any("uvs outside" in e for e in errs)


def test_catches_wrong_curve_length(symbol):
    ab = AnimBuilder(symbol.data, "a").bone("root", "translate", [(0, 0, 0), (1, 5, 5)], "in_out")
    ab.a.bones["root"]["translate"][0].curve = [0, 0, 1, 1]
    assert any("curve has 4" in e for e in qa.validate(symbol.data)["errors"])


def test_budget_counts_blend_breaks(symbol):
    sk = symbol.data
    b0 = qa.budget(sk)["metrics"]["draw_calls"]
    sk.slot("gem").blend = "additive"  # sandwiched between normal parts
    b1 = qa.budget(sk)
    assert b1["metrics"]["draw_calls"] == b0 + 2
    sk.slot("gem").blend = "normal"
    sk.slot("highlight").blend = "additive"  # last in the draw order
    assert qa.budget(sk)["metrics"]["draw_calls"] == b0 + 1


def test_budget_flags_heavy_rigs(character):
    for s in ["arm_l", "arm_r", "body", "face", "cape"]:
        rig_mesh(character, s, detail=3, max_vertices=900)
    res = qa.budget(character.data, "mobile_symbol")
    assert not res["ok"] and "vertices" in res["over_budget"]
    assert res["tips"]
