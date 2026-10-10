"""light_bloom / light_ripple / light_shock: additive prism light that grows small -> large, opacity 0 -> 100% at the
middle of each life -> 0, rings rippling out; the loop is seamless; user art is made additive-safe."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_light_bloom as L, fx_recipes as R, qa
from claude_spine.ir import new_skeleton
from claude_spine.project import Project

TAKES = ("light_bloom", "light_ripple", "light_shock")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 1000, 1000))


def value(keys, t, field="value"):
    """Evaluate a Spine timeline with absolute bezier curves at time t (one value)."""
    idx = {"value": 0, "x": 0, "y": 1}[field]
    if t <= keys[0].time:
        return getattr(keys[0], field)
    for k0, k1 in zip(keys, keys[1:]):
        if k0.time <= t <= k1.time:
            v0, v1 = getattr(k0, field), getattr(k1, field)
            if not k0.curve:
                return v0 + (v1 - v0) * (t - k0.time) / max(1e-9, k1.time - k0.time)
            cx1, cy1, cx2, cy2 = k0.curve[4 * idx: 4 * idx + 4]
            lo, hi = 0.0, 1.0
            for _ in range(60):
                u = (lo + hi) / 2
                x = (1 - u) ** 3 * k0.time + 3 * (1 - u) ** 2 * u * cx1 + 3 * (1 - u) * u * u * cx2 + u ** 3 * k1.time
                lo, hi = (u, hi) if x < t else (lo, u)
            u = (lo + hi) / 2
            return (1 - u) ** 3 * v0 + 3 * (1 - u) ** 2 * u * cy1 + 3 * (1 - u) * u * u * cy2 + u ** 3 * v1
    return getattr(keys[-1], field)


@pytest.mark.parametrize("recipe", TAKES)
def test_additive_small_to_large_peak_in_the_middle(proj, recipe):
    res = R.apply(proj, recipe)
    assert qa.validate(proj.data)["ok"]
    an = proj.data.animations[res["animation"]]
    for s in res["slots"]:
        sl = proj.data.slot(s)
        assert sl.blend == "additive" and sl.color.endswith("00")       # invisible in setup
        a = an.slots[s]["alpha"]
        bone = sl.bone
        sc = an.bones[bone]["scale"]
        if res.get("loop"):
            continue                                                    # the loop is checked below
        vals = [value(a, t) for t in np.linspace(0, res["duration"], 200)]
        assert vals[0] == pytest.approx(0, abs=1e-6) and vals[-1] == pytest.approx(0, abs=1e-3)
        assert max(vals) == pytest.approx(1.0 if "rays2" not in s else 0.7, abs=1e-3)
        # full opacity exactly halfway between the piece's first visible key and its end
        born = max(k.time for k in a if k.time < a[-2].time and k.value == 0)
        assert a[-2].time == pytest.approx((born + a[-1].time) / 2, abs=1e-3)
        s_first, s_last = sc[0].x, sc[-1].x
        assert s_first < 0.2 and s_last > 1.0                         # small -> large


def test_the_rings_travel_past_the_rays(proj):
    res = R.apply(proj, "light_bloom")
    an = proj.data.animations[res["animation"]]
    end = {proj.data.slot(s).bone: an.bones[proj.data.slot(s).bone]["scale"][-1].x for s in res["slots"]}
    rays = [v for b, v in end.items() if b.endswith("_rays")]
    rings = [v for b, v in end.items() if "_ring" in b]
    ring_w = 0.7                                                        # ring diameter / rays diameter
    assert all(v * ring_w > rays[0] * 0.95 for v in rings)              # each ring ends wider than the rays


def test_ripple_loop_is_seamless(proj):
    res = R.apply(proj, "light_ripple", options={"waves": 3})
    D = res["loop"]
    an = proj.data.animations[res["animation"]]
    assert an.duration() == pytest.approx(D)
    for s in res["slots"]:
        b = proj.data.slot(s).bone
        a = an.slots[s]["alpha"]
        assert value(a, 0.0) == pytest.approx(value(a, D), abs=1e-3)
        sc = an.bones[b]["scale"]
        if value(a, 0.0) > 1e-3:                                        # visible across the seam: scale must match
            assert value(sc, 0.0, "x") == pytest.approx(value(sc, D, "x"), abs=1e-3)
    # three waves alive at once, out of step
    tops = []
    for s in res["slots"][:3]:
        a = an.slots[s]["alpha"]
        ts = np.linspace(0, D, 241)
        tops.append(ts[int(np.argmax([value(a, t) for t in ts]))])
    gaps = sorted(tops)
    assert min(np.diff(gaps)) > 0.5


def test_late_pieces_are_held_invisible_from_the_start(proj):
    res = R.apply(proj, "light_shock", start=0.2)
    an = proj.data.animations[res["animation"]]
    late = [s for s in res["slots"] if s.endswith("ring2")][0]
    a = an.slots[late]["alpha"]
    assert a[0].time == pytest.approx(0.2) and a[0].value == 0         # a key at the recipe start, not at the ring's
    assert value(a, 0.35) == pytest.approx(0, abs=1e-6)


def test_split_keeps_the_curve():
    class C:
        t0, k = 0.0, 1.0
    seg = (0.5, [0.1], 2.85, [1.6], L.OUT_SINE)
    whole = L.bezier_keys(C, [seg], ["value"])
    wrapped = L.bezier_keys(C, [seg], ["value"], loop=2.4)
    for t in np.linspace(0.5, 2.85, 25):
        tw = t if t <= 2.4 else t - 2.4
        assert value(wrapped, tw) == pytest.approx(value(whole, t), abs=2e-3)


def _ring_layer(n=400, cx=230.0, cy=210.0, haze=7):
    y, x = np.mgrid[:n, :n].astype(float)
    r = np.hypot(x - cx, y - cy)
    a = 220 * np.exp(-((r - 120) / 25) ** 2)
    a = np.maximum(a, haze)
    im = np.zeros((n, n, 4), np.uint8)
    im[..., :3] = (120, 160, 255)
    im[..., 3] = a.astype(np.uint8)
    return Image.fromarray(im, "RGBA")


def test_ring_centre_finds_an_off_centre_ring():
    al = np.asarray(_ring_layer(), np.float32)[..., 3]
    cx, cy = L.ring_centre(al)
    assert math.hypot(cx - 230, cy - 210) < 2.5


def test_user_art_from_a_psb_is_cleaned_and_shared(proj, tmp_path):
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer
    psd = PSDImage.new("RGB", (400, 400))
    psd.append(PixelLayer.frompil(_ring_layer(), psd, name="Layer 1", top=0, left=0))
    psd.append(PixelLayer.frompil(_ring_layer(cx=200, cy=200, haze=0), psd, name="Layer 2", top=0, left=0))
    path = tmp_path / "light.psb"                                      # a .psb name loads like a .psd
    psd.save(path)
    art = {"rays": f"{path}#Layer 1", "ring": f"{path}#Layer 2"}
    texs = set()
    for rcp in TAKES:
        res = R.apply(proj, rcp, art=art, options={"size": 400, "tex_scale": 1.0})
        texs.add(tuple(sorted(res["art"].values())))
    assert len(texs) == 1                                              # one texture per picture for all three takes
    rays = np.asarray(proj.image(res["art"]["rays"]), np.float32)
    h, w = rays.shape[:2]
    assert h == w
    cx, cy = L.ring_centre(rays[..., 3])
    yy, xx = np.mgrid[:h, :w]
    assert rays[..., 3][np.hypot(xx - cx, yy - cy) > 190].max() < 2   # the 7/255 haze is gone
    assert abs(cx - w / 2) < 3 and abs(cy - h / 2) < 3                 # centred on its own ring
    assert qa.validate(proj.data)["ok"]
    imgs = sorted(p.name for p in (proj.images_dir / "fx").glob("*.png"))
    assert imgs == sorted(n.split("/")[-1] + ".png" for n in res["art"].values())


def test_listed_with_options_and_roles():
    lst = R.list_recipes()
    for rcp in TAKES:
        assert set(lst[rcp]["art_roles"]) == {"rays", "ring"}
        assert {"size", "ring", "peak", "reach", "spin", "wobble", "clean", "tex_scale"} <= set(lst[rcp]["options"])
    assert "waves" in lst["light_ripple"]["options"] and "rings" in lst["light_shock"]["options"]


def test_peak_option_moves_full_opacity(proj):
    res = R.apply(proj, "light_bloom", options={"peak": 0.3, "rings": 0})
    a = proj.data.animations[res["animation"]].slots[res["slots"][0]]["alpha"]
    top = [k for k in a if k.value == pytest.approx(1.0)][0]
    assert top.time == pytest.approx(0.6, abs=1e-3)                    # rays live 0 -> 2.0 s
