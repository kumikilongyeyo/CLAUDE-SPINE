"""Random silhouettes at random densities: every mesh must be a valid
triangulation that covers all the art. This found the collinear-hull flat
triangle bug that fixed shapes never hit."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from claude_spine.geometry import build_mesh_geom, triangulation_ok


def blob(seed):
    rng = np.random.default_rng(seed)
    W, H = int(rng.integers(40, 400)), int(rng.integers(40, 400))
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for _ in range(int(rng.integers(1, 6))):
        x0, y0 = rng.uniform(0, W), rng.uniform(0, H)
        x1, y1 = x0 + rng.uniform(5, W), y0 + rng.uniform(5, H)
        kind = rng.integers(0, 3)
        box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        if kind == 0:
            d.ellipse(box, fill=255)
        elif kind == 1:
            d.rectangle(box, fill=255)
        else:
            n = int(rng.integers(3, 9))
            d.polygon([(rng.uniform(0, W), rng.uniform(0, H)) for _ in range(n)], fill=255)
    return np.array(im), rng


@pytest.mark.parametrize("seed", range(300))
def test_random_blob(seed):
    a, rng = blob(seed)
    if (a > 8).sum() < 30:
        pytest.skip("too little art")
    joints = rng.uniform([0, 0], [a.shape[1], a.shape[0]], (int(rng.integers(0, 3)), 2))
    g = build_mesh_geom(a, joints=joints if len(joints) else None, detail=float(rng.uniform(0.4, 3)),
                        max_vertices=int(rng.integers(40, 700)))
    ok, why = triangulation_ok(g.points, g.hull, g.triangles)
    assert ok, why
    assert g.stats["uncovered_px"] == 0
