import math

import numpy as np
import pytest
from PIL import Image, ImageDraw

from claude_spine.geometry import build_mesh_geom, polygon_mask, triangulation_ok, art_mask


def shape(kind, size=(300, 200)):
    im = Image.new("L", size, 0)
    d = ImageDraw.Draw(im)
    if kind == "rect":
        d.rectangle([20, 30, 280, 170], fill=255)
    elif kind == "full":  # full-bleed: art touches every edge
        d.rectangle([0, 0, size[0] - 1, size[1] - 1], fill=255)
    elif kind == "L":
        d.polygon([(20, 20), (80, 20), (80, 140), (280, 140), (280, 190), (20, 190)], fill=255)
    elif kind == "ring":
        d.ellipse([40, 10, 230, 190], fill=255)
        d.ellipse([100, 70, 150, 120], fill=0)
    elif kind == "islands":
        d.ellipse([10, 10, 90, 90], fill=255)
        d.ellipse([180, 100, 280, 190], fill=255)
    elif kind == "star":
        pts = [(150 + (90 if i % 2 == 0 else 30) * math.cos(i * math.pi / 6),
                100 + (90 if i % 2 == 0 else 30) * math.sin(i * math.pi / 6)) for i in range(12)]
        d.polygon(pts, fill=255)
    elif kind == "hand":
        d.rectangle([60, 110, 240, 190], fill=255)
        for i in range(5):
            d.rounded_rectangle([65 + i * 36, 15 + (i % 2) * 15, 85 + i * 36, 130], radius=9, fill=255)
    return np.array(im)


@pytest.mark.parametrize("kind", ["rect", "full", "L", "ring", "islands", "star", "hand"])
def test_mesh_is_valid_and_covers_all_art(kind):
    a = shape(kind)
    g = build_mesh_geom(a)
    ok, why = triangulation_ok(g.points, g.hull, g.triangles)
    assert ok, why
    assert len(g.triangles) == 2 * g.n - g.hull - 2
    assert g.stats["uncovered_px"] == 0
    # inside the image: Spine's editor clamps UVs outside 0..1
    assert g.points[:, 0].min() >= 0 and g.points[:, 0].max() <= a.shape[1]
    assert g.points[:, 1].min() >= 0 and g.points[:, 1].max() <= a.shape[0]


def test_hull_is_tight():
    g = build_mesh_geom(shape("star"))
    assert g.stats["coverage_ratio"] > 0.85  # art area / hull area: no fat convex wrap


def test_joints_attract_vertices():
    a = shape("rect")
    plain = build_mesh_geom(a)
    jointed = build_mesh_geom(a, joints=[(150, 100)])
    def near(g):
        return int((np.hypot(*(g.points - [150, 100]).T) < 30).sum())
    assert near(jointed) > near(plain)


def test_max_vertices_is_respected():
    g = build_mesh_geom(shape("ring"), detail=3, max_vertices=80)
    assert g.n <= 80


def test_empty_image_raises():
    with pytest.raises(ValueError):
        build_mesh_geom(np.zeros((50, 50), np.uint8))
