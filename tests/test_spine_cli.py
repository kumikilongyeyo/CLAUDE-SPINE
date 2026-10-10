"""Round-trip through the real Spine editor, when it is installed."""
import json

from claude_spine import juice, rig, spine_cli
from claude_spine.mesh import rig_mesh
from conftest import needs_spine


@needs_spine
def test_editor_imports_without_repairs_and_keeps_meshes(character, tmp_path):
    p = character
    rig_mesh(p, "arm_l", bones=["arm_l1", "arm_l2"])
    rig.add_ik(p.data, ["arm_l1", "arm_l2"])
    rig.rig_strand(p, "lock_l", n_bones=3)
    rig.turn_rig(p, "head", "face", {"nose": 1.2})
    juice.apply(p)
    p.save()
    res = spine_cli.make_project(str(p.path), str(tmp_path / "hero.spine"))
    assert res["ok"] and not res["repairs"], res["log"]
    exp = spine_cli.export_project(str(tmp_path / "hero.spine"), str(tmp_path / "rt"))
    assert exp["ok"]
    a = json.loads(p.path.read_text())
    b = json.loads((tmp_path / "rt" / "hero.json").read_text())
    ma = {(s, n): v for s, d in a["skins"][0]["attachments"].items() for n, v in d.items()}
    mb = {(s, n): v for s, d in b["skins"][0]["attachments"].items() for n, v in d.items()}
    for k, v in ma.items():
        if v.get("type") == "mesh":
            w = mb[k]
            assert len(v["triangles"]) == len(w["triangles"])
            assert max(abs(x - y) for x, y in zip(v["uvs"], w["uvs"])) < 1e-4
            assert max(abs(x - y) for x, y in zip(v["vertices"], w["vertices"])) < 0.02
    assert len(a["physics"]) == len(b["physics"])


@needs_spine
def test_rebuilding_an_editable_project_replaces_it(character, tmp_path):
    out = tmp_path / "hero.spine"
    for _ in range(2):                      # the second import used to add "hero2" next to the stale "hero"
        res = spine_cli.make_project(str(character.path), str(out))
        assert res["ok"] and "renamed" not in res["log"].lower(), res["log"]
    exp = spine_cli.export_project(str(out), str(tmp_path / "rt"))
    assert exp["ok"] and sorted(f.name for f in (tmp_path / "rt").glob("*.json")) == ["hero.json"]
    assert not list(tmp_path.glob("*.importing.spine"))
