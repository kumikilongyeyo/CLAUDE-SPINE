import json

from claude_spine.ir import Bone, MeshAttachment, RegionAttachment, SkeletonData, Slot, new_skeleton
from claude_spine.mesh import mesh_world_vertices, rig_mesh


def test_defaults_are_dropped_and_types_kept(tmp_path):
    sk = new_skeleton()
    sk.add_bone(Bone(name="a", parent="root", x=5))
    sk.slots.append(Slot(name="s", bone="a", attachment="s"))
    sk.set_attachment("s", "s", RegionAttachment(width=10, height=20))
    sk.set_attachment("s", "m", MeshAttachment(uvs=[0, 0, 1, 0, 0, 1], triangles=[0, 1, 2], vertices=[0, 0, 1, 0, 0, 1], hull=3))
    d = sk.to_dict()
    assert d["bones"][1] == {"name": "a", "parent": "root", "x": 5}
    assert d["slots"][0] == {"name": "s", "bone": "a", "attachment": "s"}
    assert "type" not in d["skins"][0]["attachments"]["s"]["s"]
    assert d["skins"][0]["attachments"]["s"]["m"]["type"] == "mesh"
    p = tmp_path / "x.json"
    sk.save(p)
    assert SkeletonData.load(p).to_dict() == d


def test_unknown_fields_survive(tmp_path):
    raw = {"skeleton": {"spine": "4.2.43", "futureField": 1}, "bones": [{"name": "root", "icon": "star"}],
           "slots": [], "skins": [{"name": "default", "attachments": {}}], "animations": {}}
    p = tmp_path / "x.json"
    p.write_text(json.dumps(raw))
    d = SkeletonData.load(p).to_dict()
    assert d["skeleton"]["futureField"] == 1
    assert d["bones"][0]["icon"] == "star"


def test_spine3_skins_dict_is_upgraded(tmp_path):
    raw = {"skeleton": {}, "bones": [{"name": "root"}], "slots": [], "skins": {"default": {}}}
    p = tmp_path / "x.json"
    p.write_text(json.dumps(raw))
    assert SkeletonData.load(p).skins[0].name == "default"


def test_world_and_local_round_trip():
    sk = new_skeleton()
    sk.add_bone_world("a", "root", 10, 20, 90, 50)
    sk.add_bone_world("b", "a", 10, 70, 135, 30)
    w = sk.world()
    assert abs(w["b"].x - 10) < 1e-6 and abs(w["b"].y - 70) < 1e-6
    assert abs(w["b"].rotation - 135) < 1e-6
    assert abs(w["a"].tail[1] - 70) < 1e-6
    lx, ly = w["b"].to_local(*w["b"].to_world(3, 4))
    assert abs(lx - 3) < 1e-9 and abs(ly - 4) < 1e-9


def test_inserting_a_bone_keeps_weighted_meshes_on_their_bones(arm):
    """Weighted vertices name bones by index; an insertion before them must not
    re-target the mesh (this broke a whole character during development)."""
    rig_mesh(arm, "arm", bones=["upper", "fore"])
    sk = arm.data
    before = mesh_world_vertices(sk, "arm", sk.attachment("arm"))
    sk.add_bone_world("zzz", "root", 0, 0)       # appended after root's subtree
    sk.add_bone_world("early", "root", 5, 5)     # inserted before upper? (after root subtree)
    from claude_spine.rig import insert_parent
    insert_parent(sk, "wrap", "root", ["upper"], 0, 0)  # reorders the whole list
    after = mesh_world_vertices(sk, "arm", sk.attachment("arm"))
    assert abs(before - after).max() < 1e-6
