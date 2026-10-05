import math

import numpy as np

from claude_spine.geometry import build_mesh_geom
from claude_spine.weights import BoneSeg, heat_weights
from PIL import Image, ImageDraw


def arm_mesh():
    im = Image.new("L", (300, 200), 0)
    ImageDraw.Draw(im).rounded_rectangle([10, 80, 290, 130], radius=25, fill=255)
    g = build_mesh_geom(np.array(im), joints=[(150, 105)])
    bones = [BoneSeg("upper", (15, 105), (150, 105)), BoneSeg("fore", (150, 105), (285, 105))]
    return g, bones, heat_weights(g.points, g.triangles, g.hull, bones)


def test_rows_normalised_and_pruned():
    g, _, W = arm_mesh()
    assert np.allclose(W.sum(1), 1)
    nz = W[W > 0]
    assert nz.min() >= 0.05 - 1e-9
    assert ((W > 0).sum(1) <= 4).all()


def test_mid_bone_vertices_belong_to_their_bone():
    """The classic auto-weight failure: inverse distance to joints pulls the
    middle of a long bone toward the next joint."""
    g, _, W = arm_mesh()
    P = g.points
    assert W[np.abs(P[:, 0] - 70) < 15, 0].min() > 0.97
    assert W[np.abs(P[:, 0] - 230) < 15, 1].min() > 0.97


def test_weights_blend_monotonically_across_the_joint():
    g, _, W = arm_mesh()
    P = g.points
    xs = np.arange(100, 205, 15)
    means = [W[np.abs(P[:, 0] - x) < 8, 0].mean() for x in xs]
    assert all(a >= b - 0.02 for a, b in zip(means, means[1:]))
    j = W[np.abs(P[:, 0] - 150) < 8, 0].mean()
    assert 0.2 < j < 0.8  # actually blended at the joint


def test_no_folds_at_45_degree_bend():
    g, _, W = arm_mesh()
    P, T = g.points, g.triangles
    c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
    rel = P - [150, 105]
    rot = np.c_[c * rel[:, 0] - s * rel[:, 1], s * rel[:, 0] + c * rel[:, 1]] + [150, 105]
    Q = W[:, :1] * P + W[:, 1:2] * rot

    def cross(X):
        a, b, cc = X[T[:, 0]], X[T[:, 1]], X[T[:, 2]]
        return (b - a)[:, 0] * (cc - a)[:, 1] - (b - a)[:, 1] * (cc - a)[:, 0]

    assert (np.sign(cross(Q)) == np.sign(cross(P))).all()


def test_heat_does_not_jump_gaps():
    """Two separate fingers: a vertex on finger A must not be weighted to the
    bone inside finger B even though it is close in a straight line."""
    im = Image.new("L", (200, 200), 0)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 150, 180, 195], fill=255)
    d.rectangle([30, 20, 70, 160], fill=255)
    d.rectangle([110, 20, 150, 160], fill=255)
    g = build_mesh_geom(np.array(im))
    bones = [BoneSeg("palm", (30, 172), (170, 172)), BoneSeg("fa", (50, 150), (50, 30)), BoneSeg("fb", (130, 150), (130, 30))]
    W = heat_weights(g.points, g.triangles, g.hull, bones)
    on_a = (g.points[:, 0] < 75) & (g.points[:, 1] < 120)
    assert W[on_a, 2].max() == 0
