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
