"""Straight AE pieces laid on every segment of a polyline: structure, the complementary end fades, and the runtime's
IK-stretched segment bones following the knots (no bending anywhere)."""
import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_polyline, atlas, runtime
from claude_spine.timeline import AnimBuilder
from conftest import needs_node

PAD = 24
LINE = [[-300, 0], [-150, 0], [0, 0], [150, 0], [300, 0]]
VEE = [[-300, 100], [-150, 0], [0, -100], [150, 0], [300, 100]]
PARTS = [{"name": "in", "frames": [0, 2], "mode": "once"}, {"name": "loop", "frames": [3, 8], "mode": "loop"},
         {"name": "out", "frames": [9, 9], "mode": "once"}]


def piece_frames(d, n=10, size=(160, 32)):
    """A straight light piece: a bright line along the middle row, its knots PAD px in from both ends."""
    d.mkdir(parents=True, exist_ok=True)
    y, x = np.mgrid[0:size[1], 0:size[0]]
    for i in range(n):
        a = np.zeros((size[1], size[0], 3), np.float32)
        a[np.abs(y - size[1] // 2) < 3] = [1, 0.4, 0.5]
        a[((x + i * 6) % 40 < 4) & (np.abs(y - size[1] // 2) < 10)] += 0.3
        Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGB").save(d / f"f_{i:05d}.png")
    return d


def build(p, tmp_path, points=LINE, **kw):
    d = piece_frames(tmp_path / "fr")
    layers = [{"name": "aura", "frames_dir": str(d), "fps": 12, "fade": PAD},
              {"name": "core", "frames_dir": str(d), "fps": 12, "fade": 6}]
    return ae_polyline.polyline_fx(p, "pl", points, layers, pad=PAD, parts=PARTS,
                                   head={"frames_dir": str(d), "fps": 12, "size": [32, 32]}, **kw)


def test_end_fades_of_overlapping_pieces_add_back_to_one():
    w, pad, fade = 200, 40, 30
    r = ae_polyline.end_ramp(w, pad, fade)
    # piece A ends at its knot x = w - pad; piece B starts at its knot x = pad: at the shared knot they overlap
    shift = w - 2 * pad
    a = r[shift:]                       # A's columns that lie over B's first w - shift columns
    b = r[:w - shift]
    assert np.allclose(a + b, 1.0, atol=1e-6)
    assert r[0] == 0 and r[w // 2] == 1


def test_structure(symbol, tmp_path):
    res = build(symbol, tmp_path)
    sk = symbol.data
    K = len(LINE) - 1
    assert res["control_bones"] == [f"pl_c{i}" for i in range(K + 1)] and len(res["segment_bones"]) == K
    iks = {c.bones[0]: c for c in sk.ik}
    for i, sb in enumerate(res["segment_bones"]):
        assert sk.bone(sb).parent == res["control_bones"][i]
        assert iks[sb].target == res["control_bones"][i + 1] and iks[sb].stretch and iks[sb].mix == 1
    # one frame set per layer, shared by every segment; tail dim, head full
    for layer in ("aura", "core"):
        paths = {sk.attachment(s, f"{layer}_loop").path for s in res["slots"][layer]}
        assert paths == {f"ae/pl_{layer}_loop_"}
        alphas = [int(sk.slot(s).color[6:8], 16) for s in res["slots"][layer]]
        assert alphas == sorted(alphas) and alphas[-1] == 255 and alphas[0] < 120
    assert [s.name for s in sk.slots].index(res["slots"]["aura"][-1]) < [s.name for s in sk.slots].index(res["slots"]["core"][0])
    assert sk.slot(res["head_slot"]).bone == res["control_bones"][-1]
    assert {a["animation"] for a in res["animations"].values()} == {"pl_in", "pl_loop", "pl_out"}
    # each piece spans its segment exactly: the strip between the knots maps onto the segment length
    att = sk.attachment(res["slots"]["core"][1], "core_loop")
    assert att.x == pytest.approx(75) and att.width == pytest.approx(160 * 150 / (160 - 2 * PAD), rel=1e-3)


def test_bad_input(symbol, tmp_path):
    d = piece_frames(tmp_path / "fr")
    L = [{"name": "core", "frames_dir": str(d), "fps": 12}]
    with pytest.raises(ValueError, match="two"):
        ae_polyline.polyline_fx(symbol, "x", [[0, 0]], L)
    with pytest.raises(ValueError, match="coincide"):
        ae_polyline.polyline_fx(symbol, "x", [[0, 0], [0, 0], [5, 5]], L)
    with pytest.raises(ValueError, match="pad"):
        ae_polyline.polyline_fx(symbol, "x", LINE, L, pad=90)


@needs_node
def test_runtime_pieces_follow_the_knots_with_exact_corners(symbol, tmp_path):
    res = build(symbol, tmp_path)
    sk = symbol.data
    ab = AnimBuilder(sk, "pl_loop", replace=False)
    for i, cb in enumerate(res["control_bones"]):                 # the game moves the knots onto a V
        ab.bone(cb, "translate", [(0.0, VEE[i][0] - LINE[i][0], VEE[i][1] - LINE[i][1])], "linear")
    symbol.save()
    pk = atlas.pack(symbol, tmp_path / "exp", strip=True, pma=True)
    dump = runtime.run(symbol, atlas_path=pk["atlas"], animations=["pl_loop"], fps=10, geometry=True)
    assert dump["ok"], dump
    draws = {d["slot"]: np.asarray(d["v"], float).reshape(-1, 2) for d in dump["animations"]["pl_loop"]["frames"][1]["draws"]}
    for i, s in enumerate(res["slots"]["core"]):
        q = draws[s]                                                # the region's 4 corners
        a, b = np.array(VEE[i], float), np.array(VEE[i + 1], float)
        centre = q.mean(0)
        assert np.hypot(*(centre - (a + b) / 2)) < 1.0              # the piece is centred on its segment
        long_side = max((q[1] - q[0], q[2] - q[1]), key=lambda v: np.hypot(*v))
        seg = b - a
        cosang = abs(np.dot(long_side, seg)) / (np.hypot(*long_side) * np.hypot(*seg))
        assert cosang > 0.999                                       # and lies along it: the corner stays exact
        # the packer trims what the end fades made transparent: the visible piece runs `fade` (6) px past each knot,
        # stretched with the segment (the strip's 112 px between the knots = the segment)
        assert np.hypot(*long_side) == pytest.approx(np.hypot(*seg) * (160 - 2 * PAD + 2 * 6) / (160 - 2 * PAD), rel=0.01)
