import math

import numpy as np
import pytest

from claude_spine import rig
from claude_spine.ir import new_skeleton
from claude_spine.mesh import lbs_pose, mesh_world_vertices, rig_mesh
from claude_spine.rig import setup_hull_world


def test_rig_mesh_keeps_setup_pose(arm):
    before = setup_hull_world(arm, "arm")
    res = rig_mesh(arm, "arm")  # auto bones
    assert res["weighted"] and res["bones"] == ["upper", "fore"]
    sk = arm.data
    att = sk.attachment("arm")
    v = mesh_world_vertices(sk, "arm", att)
    lo, hi = before.min(0), before.max(0)
    assert (v >= lo - 0.5).all() and (v <= hi + 0.5).all()
    # setup-pose LBS equals the stored positions
    assert abs(lbs_pose(sk, "arm", att, sk.world()) - v).max() < 1e-6


def test_unweighted_mesh(arm):
    res = rig_mesh(arm, "arm", bones=None)
    assert not res["weighted"]
    att = arm.data.attachment("arm")
    assert len(att.vertices) == len(att.uvs)


def test_ik_auto_bend_direction():
    sk = new_skeleton()
    sk.add_bone_world("a", "root", 0, 0, 0, 50)
    sk.add_bone_world("b", "a", 50, 0, 60, 50)  # bends counter-clockwise
    assert rig.add_ik(sk, ["a", "b"])["bendPositive"] is True
    sk2 = new_skeleton()
    sk2.add_bone_world("a", "root", 0, 0, 0, 50)
    sk2.add_bone_world("b", "a", 50, 0, -60, 50)
    assert rig.add_ik(sk2, ["a", "b"])["bendPositive"] is False


def test_ik_rejects_bad_chains():
    sk = new_skeleton()
    sk.add_bone_world("a", "root", 0, 0, 0, 50)
    sk.add_bone_world("c", "root", 0, 0, 0, 50)
    with pytest.raises(ValueError):
        rig.add_ik(sk, ["a", "c"])


def test_physics_presets_taper():
    sk = new_skeleton()
    bones = rig.add_chain(sk, "h", [[0, 0], [0, -40], [0, -80], [0, -120]])
    names = rig.add_physics(sk, bones, "hair")
    s = [c.strength for c in sk.physics]
    assert len(names) == 3 and s[0] > s[1] > s[2]
    assert all(c.limit < 5000 for c in sk.physics)


def test_chain_reaches_points():
    sk = new_skeleton()
    pts = [[0, 0], [30, 40], [30, 90]]
    rig.add_chain(sk, "c", pts)
    w = sk.world()
    assert np.allclose(w["c1"].tail, pts[1], atol=1e-3)
    assert np.allclose(w["c2"].tail, pts[2], atol=1e-3)


def test_reparent_keeps_art_in_place(character):
    sk = character.data
    before = setup_hull_world(character, "nose")
    sk.add_bone_world("tilted", "head", 30, 300, 33)
    rig.reparent_slot(sk, "nose", "tilted")
    assert abs(setup_hull_world(character, "nose") - before).max() < 1e-3


def test_strand_follows_the_art(character):
    res = rig.rig_strand(character, "lock_l", n_bones=4, physics="hair")
    sk = character.data
    assert len(res["bones"]) == 4 and len(sk.physics) == 4
    hull = setup_hull_world(character, "lock_l")
    from claude_spine.geometry import points_in_polygon
    w = sk.world()
    heads = np.array([w[b].head for b in res["bones"]] + [w[res["bones"][-1]].tail])
    assert points_in_polygon(heads[1:-1], hull).all()  # joints lie inside the lock
    assert heads[0][1] > heads[-1][1]                    # rooted at the top


def test_turn_rig_moves_features_the_right_way(character):
    sk = character.data
    res = rig.turn_rig(character, "head", "face", {"nose": 1.25, "ear_l": -0.35})
    assert res["animation"] == "turn_test"
    # setup pose unchanged
    for tc in sk.transform:
        assert tc.local and tc.relative
    nose_tc = next(t for t in sk.transform if t.bones == [res["features"]["nose"]["bone"]])
    ear_tc = next(t for t in sk.transform if t.bones == [res["features"]["ear_l"]["bone"]])
    assert nose_tc.mixX > 0 > ear_tc.mixX
    # the turn frame is screen-aligned, so translate x on the control is a yaw
    w = sk.world()
    assert abs(w[res["control"]].rotation) < 1e-6
    # face outline pinned (weight 0 on the driven bone), middle travels
    from claude_spine.weights import decode_weighted
    att = sk.attachment("face")
    inf = decode_weighted(att.vertices, len(att.uvs) // 2)
    drv = sk.bone_index(res["face"]["driven_bone"])
    hull_w = [sum(wt for bi, *_, wt in v if bi == drv) for v in inf[: att.hull]]
    mid_w = [sum(wt for bi, *_, wt in v if bi == drv) for v in inf[att.hull:]]
    assert max(hull_w) == 0 and max(mid_w) > 0.6
