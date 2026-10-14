"""Bending an AE strip along a Spine path: structure, and the runtime's own path constraint doing the work."""
import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_path, atlas, runtime
from claude_spine.mesh import mesh_world_vertices
from claude_spine.timeline import AnimBuilder
from conftest import needs_node


def strip_frames(d, n=4, size=(256, 64)):
    d.mkdir(parents=True, exist_ok=True)
    y, x = np.mgrid[0:size[1], 0:size[0]]
    for i in range(n):
        a = np.zeros((size[1], size[0], 4), np.float32)
        a[..., 0] = 1
        a[..., 1] = 0.6
        a[..., 3] = ((y > size[1] * 0.7) | (((x + i * 8) % 32 < 6) & (y > size[1] * 0.3))) * 1.0
        Image.fromarray((a * 255).astype(np.uint8), "RGBA").save(d / f"f_{i:05d}.png")
    return d


KNOTS = [[-120, -30], [-30, 40], [60, -20], [130, 30]]


def build(symbol, tmp_path, **kw):
    d = strip_frames(tmp_path / "fr")
    return ae_path.fx_along_path(symbol, "line", KNOTS, frames_dir=str(d), fps=12, bones=6, **kw)


def test_rig_structure(symbol, tmp_path):
    res = build(symbol, tmp_path)
    sk = symbol.data
    assert res["control_bones"] == [f"line_c{i}" for i in range(4)]
    assert len(res["chain_bones"]) == 6
    # chain: each bone is the child of the one before, so the path constraint can chain-scale them
    for a, b in zip(res["chain_bones"], res["chain_bones"][1:]):
        assert sk.bone(b).parent == a
    c = sk.path[0]
    assert (c["spacingMode"], c["rotateMode"], c["positionMode"]) == ("proportional", "chainScale", "percent")
    assert c["bones"] == res["chain_bones"] and c["target"] == res["path_slot"]
    path = sk.attachment(res["path_slot"], "path")
    assert path.vertexCount == 12 and path.constantSpeed and not path.closed
    # every path vertex follows exactly one control bone, handles are offsets in that bone's own space
    v, i, ctrl = path.vertices, 0, []
    while i < len(v):
        assert v[i] == 1
        ctrl.append(sk.bones[int(v[i + 1])].name)
        assert v[i + 4] == 1.0
        i += 5
    assert ctrl == [b for b in res["control_bones"] for _ in range(3)]
    mesh = sk.attachment(res["slot"], "fx")
    cols = 6 * 3                                      # top + bottom rows on the hull, the baseline row inside
    assert mesh.sequence.count == 4 and mesh.hull == 2 * (cols + 1) and len(mesh.uvs) // 2 == 3 * (cols + 1)
    # skin weights per vertex sum to 1 and use at most two chain bones
    vv, i = mesh.vertices, 0
    while i < len(vv):
        n = int(vv[i])
        assert 1 <= n <= 2 and abs(sum(vv[i + 4 + 4 * k] for k in range(n)) - 1) < 1e-4
        i += 1 + 4 * n
    assert i == len(vv)


def test_path_order_and_validation(symbol, tmp_path):
    from claude_spine import qa
    build(symbol, tmp_path)
    symbol.save()
    assert qa.validate(symbol.data)["ok"]


def test_bad_input(symbol, tmp_path):
    d = strip_frames(tmp_path / "fr")
    with pytest.raises(ValueError, match="two"):
        ae_path.fx_along_path(symbol, "x", [[0, 0]], frames_dir=str(d), fps=12)
    with pytest.raises(ValueError, match="baseline"):
        ae_path.fx_along_path(symbol, "x", KNOTS, frames_dir=str(d), fps=12, baseline=1.5)
    with pytest.raises(ValueError, match="length"):
        ae_path.fx_along_path(symbol, "x", [[5, 5], [5, 5]], frames_dir=str(d), fps=12)


def test_weights_blend_between_bone_midpoints():
    assert ae_path._weights(0.0, 4) == [(0, 1.0)] and ae_path._weights(4.0, 4) == [(3, 1.0)]
    w = dict(ae_path._weights(1.0, 4))                       # a joint: half and half
    assert w == {0: pytest.approx(0.5), 1: pytest.approx(0.5)}
    assert ae_path._weights(1.5, 4) == [(1, 1.0)]


def test_bezier_length_matches_a_straight_line():
    pts = np.array([[0.0, 0.0], [100.0, 0.0], [300.0, 0.0]])
    poly, cum = ae_path.bezier_polyline(pts, ae_path.catmull_rom_bezier(pts))
    assert cum[-1] == pytest.approx(300.0, rel=1e-3)
    p, t = ae_path.at_length(poly, cum, np.array([0.0, 150.0, 300.0]))
    assert np.allclose(p[:, 1], 0) and np.allclose(t, [[1, 0]] * 3, atol=1e-3)


@needs_node
def test_runtime_reproduces_the_setup_pose_then_follows_the_control_bones(symbol, tmp_path):
    res = build(symbol, tmp_path, demo_bend=0.0, until=1.0)
    sk = symbol.data
    ab = AnimBuilder(sk, res["animation"], replace=False)
    # at 0.5 s the last knot is dragged far to the right and up: the whole chain must restretch to span it
    ab.bone(res["control_bones"][-1], "translate", [(0.0, 0, 0), (0.5, 220, 120), (1.0, 220, 120)], "linear")
    symbol.save()
    pk = atlas.pack(symbol, tmp_path / "exp", strip=True, pma=True)
    dump = runtime.run(symbol, atlas_path=pk["atlas"], animations=[res["animation"]], fps=10, geometry=True)
    assert dump["ok"], dump
    frames = dump["animations"][res["animation"]]["frames"]

    def fx_verts(f):
        d = [d for d in f["draws"] if d["slot"] == res["slot"]][0]
        return np.asarray(d["v"], float).reshape(-1, 2)

    # t = 0: the constraint puts the chain where the setup pose has it. The runtime measures the bezier's arc
    # length with 8 segments per curve, so stations sit a hair off the exactly-sampled ones (about 1 percent)
    expected = mesh_world_vertices(sk, res["slot"], sk.attachment(res["slot"], "fx"))
    assert np.abs(fx_verts(frames[0]) - expected).max() < 0.015 * res["path_length"]
    # later the strip's far end follows the dragged knot
    cols = 6 * 3 + 1
    end0, end1 = fx_verts(frames[0])[cols - 1], fx_verts(frames[6])[cols - 1]
    knot0 = np.array(KNOTS[-1], float)
    assert np.hypot(*(end1 - end0)) > 100
    assert np.hypot(*(end1 - (knot0 + [220, 120]))) < np.hypot(*(end0 - knot0)) + 100   # up by the baseline offset only


# ------------------------------------------------------------- sharp corners, parts, ends, rig reuse (paylines)
LINE = [[-300, 0], [-150, 0], [0, 0], [150, 0], [300, 0]]          # straight setup; the game bends it


def _flipped(v, tris):
    t = np.asarray(tris).reshape(-1, 3)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    return int((area * np.sign(np.median(area)) < -1e-6).sum())


def test_sharp_handles_follow_the_neighbouring_knots(symbol, tmp_path):
    d = strip_frames(tmp_path / "fr")
    res = ae_path.fx_along_path(symbol, "pl", LINE, corners="sharp", frames_dir=str(d), fps=12)
    sk = symbol.data
    v = sk.attachment(res["path_slot"], "path").vertices
    idx = [sk.bone_index(b) for b in res["control_bones"]]
    # knot 1's in-handle and out-handle: 2/3 on its own bone, 1/3 on the neighbour's, at the bones' origins
    rows, i = [], 0
    while i < len(v):
        n = int(v[i]); rows.append(v[i + 1:i + 1 + 4 * n]); i += 1 + 4 * n
    assert len(rows) == 3 * len(LINE)
    assert rows[3] == [idx[1], 0.0, 0.0, pytest.approx(2 / 3), idx[0], 0.0, 0.0, pytest.approx(1 / 3)]
    assert rows[5] == [idx[1], 0.0, 0.0, pytest.approx(2 / 3), idx[2], 0.0, 0.0, pytest.approx(1 / 3)]
    assert rows[4][0] == idx[1] and rows[4][-1] == 1.0          # the knot itself: one bone


def test_parts_become_animations_on_one_mesh(symbol, tmp_path):
    d = strip_frames(tmp_path / "fr", n=10)
    parts = [{"name": "in", "frames": [0, 2], "mode": "once"}, {"name": "loop", "frames": [3, 8], "mode": "loop",
                                                                  "max_frames": 3}, {"name": "out", "frames": [9, 9]}]
    res = ae_path.fx_along_path(symbol, "pl", LINE, corners="sharp", frames_dir=str(d), fps=12, parts=parts)
    sk = symbol.data
    assert set(res["animations"]) == {"in", "loop", "out"}
    assert {a["animation"] for a in res["animations"].values()} == {"pl_in", "pl_loop", "pl_out"}
    counts = {k: sk.attachment(res["slot"], a["attachment"]).sequence.count for k, a in res["animations"].items()}
    assert counts == {"in": 3, "loop": 3, "out": 1}             # loop: 6 frames budgeted to 3
    assert res["animations"]["loop"]["delay"] == pytest.approx(2 / 12, abs=1e-4)   # every 2nd frame keeps the speed
    with pytest.raises(ValueError, match="outside"):
        ae_path.fx_along_path(symbol, "x", LINE, frames_dir=str(d), fps=12, parts=[{"name": "a", "frames": [5, 40]}])


def test_ends_hang_past_the_end_knots(symbol, tmp_path):
    d = strip_frames(tmp_path / "fr")                            # 256 x 64 strip
    res = ae_path.fx_along_path(symbol, "pl", LINE, corners="sharp", baseline=0.5, ends=32, across_scale=1.0,
                                frames_dir=str(d), fps=12)
    from claude_spine.mesh import mesh_world_vertices
    v = mesh_world_vertices(symbol.data, res["slot"], symbol.data.attachment(res["slot"], "fx"))
    per_px = 600 / (256 - 64)                                    # path length / strip px between the ends
    assert v[:, 0].min() == pytest.approx(-300 - 32 * per_px, abs=0.5)
    assert v[:, 0].max() == pytest.approx(300 + 32 * per_px, abs=0.5)
    assert np.abs(v[:, 1]).max() == pytest.approx(32, abs=0.5)  # across_scale 1: half of 64 px either side


def test_baseline_row_sits_on_the_path_and_a_v_does_not_fold(symbol, tmp_path):
    from claude_spine.mesh import mesh_world_vertices
    d = strip_frames(tmp_path / "fr", size=(512, 160))
    vee = [[-300, 100], [-150, 0], [0, -100], [150, 0], [300, 100]]
    res = ae_path.fx_along_path(symbol, "pl", vee, corners="sharp", baseline=0.5, across_scale=1.0,
                                weight_window=120, frames_dir=str(d), fps=12)
    att = symbol.data.attachment(res["slot"], "fx")
    v = mesh_world_vertices(symbol.data, res["slot"], att)
    hull = att.hull
    mid = v[hull:]                                               # the interior row is the baseline
    poly, cum = ae_path.bezier_polyline(np.array(vee, float), *ae_path.knot_handles(np.array(vee, float), "sharp"))
    dist = [np.hypot(*(poly - q).T).min() for q in mid]
    assert max(dist) < 1.0
    assert _flipped(v, att.triangles) == 0                      # miter-clamped inner side: nothing folds


def test_window_weights_spread_and_sum_to_one():
    w = dict(ae_path.window_weights(300.0, 600.0, 12, 120.0))
    assert len(w) > 2 and sum(w.values()) == pytest.approx(1.0)
    assert max(w, key=w.get) in (5, 6)                           # the bones whose middles are nearest s = 300
    assert ae_path.window_weights(300.0, 600.0, 12, 0.0) == ae_path._weights(6.0, 12)


def test_rig_reuse_adds_only_a_mesh(symbol, tmp_path):
    d = strip_frames(tmp_path / "fr")
    a = ae_path.fx_along_path(symbol, "pl", LINE, corners="sharp", frames_dir=str(d), fps=12, animation="pl")
    n_bones, n_paths = len(symbol.data.bones), len(symbol.data.path)
    b = ae_path.fx_along_path(symbol, "pl_core", LINE, corners="sharp", rig="pl", frames_dir=str(d), fps=12,
                              animation="pl")
    assert len(symbol.data.bones) == n_bones and len(symbol.data.path) == n_paths
    assert b["control_bones"] == a["control_bones"] and b["chain_bones"] == a["chain_bones"] and b["slot"] != a["slot"]
    tl = symbol.data.animations["pl"]                            # the second call merged into the same clip
    assert {a["slot"], b["slot"]} <= set(tl.slots)
    with pytest.raises(ValueError, match="different number of knots"):
        ae_path.fx_along_path(symbol, "x", LINE[:3], rig="pl", frames_dir=str(d), fps=12)


@needs_node
def test_runtime_bends_a_straight_setup_into_sharp_corners(symbol, tmp_path):
    d = strip_frames(tmp_path / "fr")
    res = ae_path.fx_along_path(symbol, "pl", LINE, corners="sharp", baseline=0.5, across_scale=1.0,
                                frames_dir=str(d), fps=12, until=1.0)
    vee = [[-300, 100], [-150, 0], [0, -100], [150, 0], [300, 100]]
    ab = AnimBuilder(symbol.data, res["animation"], replace=False)
    for i, cb in enumerate(res["control_bones"]):                # the game moves the knots onto a V
        ab.bone(cb, "translate", [(0.0, vee[i][0] - LINE[i][0], vee[i][1] - LINE[i][1])], "linear")
    symbol.save()
    pk = atlas.pack(symbol, tmp_path / "exp", strip=True, pma=True)
    dump = runtime.run(symbol, atlas_path=pk["atlas"], animations=[res["animation"]], fps=10, geometry=True)
    assert dump["ok"], dump
    draw = [x for x in dump["animations"][res["animation"]]["frames"][2]["draws"] if x["slot"] == res["slot"]][0]
    v = np.asarray(draw["v"], float).reshape(-1, 2)
    mid = v[symbol.data.attachment(res["slot"], "fx").hull:]
    # the baseline follows the straight segments of the V; at the corner the 2-bone blend cuts about one third of a
    # chain bone (the default ~55 units) off the tip, so the knot itself is reached within ~20 units
    assert np.hypot(*(mid - [0, -100]).T).min() < 22
    seg = mid[(mid[:, 0] > -260) & (mid[:, 0] < -60)]
    assert len(seg) > 4 and np.abs(seg[:, 1] - (-seg[:, 0] * 100 / 150 - 100)).max() < 3   # y = -2/3 x - 100
