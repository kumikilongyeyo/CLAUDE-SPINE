"""Screen-level atmosphere: weather (rain / snow / embers / petals), god_rays, water_surface, heat_shimmer, fog_roll,
lightning_storm, and their After Effects templates (god_rays, heat_shimmer, fog_roll)."""
import json
import math
import shutil
import subprocess

import numpy as np
import pytest

from claude_spine import ae_templates, fx_ambient as A, fx_recipes as R, qa, runtime
from claude_spine.ir import new_skeleton
from claude_spine.project import Project
from conftest import needs_node

NODE = shutil.which("node")
NAMES = ["weather", "god_rays", "water_surface", "heat_shimmer", "fog_roll", "lightning_storm"]
VARIANTS = [("weather", {"kind": k}) for k in A.KINDS] + [("god_rays", {}), ("water_surface", {}), ("heat_shimmer", {}),
                                                         ("fog_roll", {"kind": "fog"}), ("fog_roll", {"kind": "sand"}),
                                                         ("lightning_storm", {})]
IDS = [f"{n}-{o.get('kind', '')}".rstrip("-") for n, o in VARIANTS]
LOOPS = [v for v in VARIANTS if R.RECIPES[v[0]]["kind"] == "loop"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _v(k, f, rest=0.0):
    v = getattr(k, f, None)
    return rest if v is None else float(v)


def _alpha(k):
    return int(k.color[6:8], 16) / 255


def _tl(proj, res, bone, tl):
    return proj.data.animations[res["animation"]].bones[bone][tl]


def _slot_of(proj, bone):
    return next(s.name for s in proj.data.slots if s.bone == bone)


def _particles(proj, res, layer=None):
    """(bone, slot) of every weather particle, optionally only those under one layer bone."""
    out = []
    for s in res["slots"]:
        b = proj.data.slot(s).bone
        if layer is None or proj.data.bone(b).parent == layer:
            out.append((b, s))
    return out


def _segments(proj, res, bone, slot):
    """(t_mid, vx, vy, alpha_lo) for consecutive translate keys inside one life (both ends visible)."""
    a = proj.data.animations[res["animation"]]
    tr = a.bones[bone]["translate"]
    al = {round(k.time, 4): _alpha(k) for k in a.slots[slot]["rgba"]}
    out = []
    for k0, k1 in zip(tr, tr[1:]):
        dt = k1.time - k0.time
        a0, a1 = al.get(round(k0.time, 4), 0), al.get(round(k1.time, 4), 0)
        if dt > 0.01 and a0 > 0.02 and a1 > 0.02:
            out.append(((k0.time + k1.time) / 2, (_v(k1, "x") - _v(k0, "x")) / dt, (_v(k1, "y") - _v(k0, "y")) / dt, min(a0, a1)))
    return out


# ---------------------------------------------------------------- every recipe
def test_recipes_register_with_roles_and_listing():
    lst = R.list_recipes()
    for n in NAMES:
        assert n in R.RECIPES and R.RECIPES[n]["roles"] and n in lst
        assert lst[n]["art_roles"] == A.ROLES[n]
    assert set(R.RECIPES["lightning_storm"]["tiers"]) == {"small", "big", "mega", "epic"}


@pytest.mark.parametrize("name,opts", VARIANTS, ids=IDS)
def test_each_builds_validates_and_obeys_the_blend_rule(proj, name, opts):
    res = R.apply(proj, name, options=opts or None)
    assert res["animation"] == f"fx_{name}" and res["slots"] and res["event"] == f"fx_{name}"
    normal_ok = R.RECIPES[name].get("normal_blend", False)
    blends = {proj.data.slot(s).blend for s in res["slots"]}
    assert blends <= ({"additive", "normal"} if normal_ok else {"additive"}), blends
    if name == "weather" and opts["kind"] == "petals" or name == "fog_roll":
        assert blends == {"normal"}, "opaque things occlude"
    assert all(s.attachment is None for s in proj.data.slots), "FX slots must be hidden in the setup pose"
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]
    ev = [e.name for e in proj.data.animations[res["animation"]].events]
    assert f"fx_{name}" in ev


@needs_node
@pytest.mark.parametrize("name,opts", VARIANTS, ids=IDS)
def test_each_plays_in_the_spine_core_runtime(proj, name, opts):
    res = R.apply(proj, name, options=opts or None)
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"][res["animation"]]["frames"]


@pytest.mark.parametrize("name,opts", LOOPS, ids=[f"{n}-{o.get('kind', '')}".rstrip("-") for n, o in LOOPS])
def test_loops_close_exactly(proj, name, opts):
    res = R.apply(proj, name, options=opts or None)
    D = res["loop"]
    a = proj.data.animations[res["animation"]]
    n = 0
    for bn, tls in a.bones.items():
        for tl, ks in tls.items():
            assert ks[0].time == 0 and ks[-1].time == pytest.approx(D), (bn, tl)
            for f in ("x", "y", "value"):
                rest = 1.0 if tl == "scale" else 0.0
                v0, v1 = _v(ks[0], f, rest), _v(ks[-1], f, rest)
                assert v0 == pytest.approx(v1, abs=0.02), (bn, tl, f, v0, v1)
            n += 1
    for sn, tls in a.slots.items():
        if "rgba" in tls:
            ks = tls["rgba"]
            assert ks[0].time == 0 and ks[-1].time == pytest.approx(D)
            assert abs(int(ks[0].color[6:8], 16) - int(ks[-1].color[6:8], 16)) <= 1, sn
    assert n > 5


def test_start_and_into_shift_and_merge(proj):
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(proj.data, "game").event(0.0, "spin")
    res = R.apply(proj, "weather", start=1.5, into="game", options={"kind": "snow"})
    a = proj.data.animations["game"]
    assert res["animation"] == "game" and {e.name for e in a.events} >= {"spin", "fx_weather"}
    b, _ = _particles(proj, res)[0]
    ks = a.bones[b]["translate"]
    assert ks[0].time == pytest.approx(1.5) and ks[-1].time == pytest.approx(1.5 + 4.0)


def test_bad_options_are_clear_errors(proj):
    bad = [("weather", {"kind": "hail"}, "kind"), ("weather", {"layers": 0}, "layers"), ("weather", {"gust_cycles": 1.5}, "whole"),
           ("weather", {"depth": 0.5}, "depth"), ("weather", {"blend": "screen"}, "blend"), ("weather", {"width": 0}, "width"),
           ("god_rays", {"flicker": 2.0}, "flicker"), ("god_rays", {"rays": 0}, "rays"),
           ("water_surface", {"lands": [[0, 0]]}, "lands"), ("water_surface", {"lands": [[0, 0, 9.0]]}, "outside"),
           ("water_surface", {"lands": "x"}, "lands"), ("heat_shimmer", {"strands": 0}, "strands"),
           ("heat_shimmer", {"rise": 0}, "rise"), ("fog_roll", {"kind": "smog"}, "kind"), ("fog_roll", {"speed": 0}, "speed"),
           ("lightning_storm", {"min_gap": 3.0}, "min_gap"), ("lightning_storm", {"distance": [5, 1]}, "distance"),
           ("lightning_storm", {"rate": 0}, "rate"), ("weather", {"colour": "red"}, "unknown option")]
    for name, opts, msg in bad:
        with pytest.raises(ValueError, match=msg):
            R.apply(proj, name, options=opts)


# ---------------------------------------------------------------- weather physics
def test_weather_respawns_only_at_alpha_zero(proj):
    for kind in A.KINDS:
        p = Project(proj.path, new_skeleton("t", 720, 720))
        res = R.apply(p, "weather", options={"kind": kind})
        a = p.data.animations[res["animation"]]
        jumps = 0
        for b, s in _particles(p, res):
            tr = a.bones[b]["translate"]
            al = {round(k.time, 4): _alpha(k) for k in a.slots[s]["rgba"]}
            for k0, k1 in zip(tr, tr[1:]):
                if math.hypot(_v(k1, "x") - _v(k0, "x"), _v(k1, "y") - _v(k0, "y")) > 3000 * (k1.time - k0.time) + 40:
                    jumps += 1
                    assert al[round(k0.time, 4)] <= 0.02 and al[round(k1.time, 4)] <= 0.02, (kind, b, k0.time)
        assert jumps > 0, f"{kind}: particles respawn"


def test_rain_falls_at_terminal_velocity_with_parallax(proj):
    res = R.apply(proj, "weather", options={"kind": "rain", "layers": 3, "depth": 2.5, "wind": 0.0, "gust": 0.0})
    vt = A.KINDS["rain"]["vt"]
    lay = res["layers"]
    assert [L["distance"] for L in lay] == [2.5, 1.75, 1.0], "far layer first (drawn behind)"
    assert lay[0]["count"] > lay[-1]["count"], "more volume far away"
    speeds = {}
    for L in lay:
        vy = [sg[2] for b, s in _particles(proj, res, L["bone"]) for sg in _segments(proj, res, b, s)]
        f = 1 / L["distance"]
        assert all(-1.16 * vt * f <= v <= -0.84 * vt * f for v in vy), "steady fall at the (jittered) terminal speed"
        speeds[L["distance"]] = -np.mean(vy)
    assert speeds[2.5] / speeds[1.0] == pytest.approx(1 / 2.5, rel=0.12), "apparent speed ~ 1/distance"
    sizes = {L["distance"]: np.mean([proj.data.skin("default").attachments[s]["fx"].height for _, s in _particles(proj, res, L["bone"])])
             for L in lay}
    assert sizes[2.5] < sizes[1.0] * 0.55, "far streaks are shorter"


def _fit_gust(proj, res, D):
    """Least-squares fit vx(t) = a sin(wt) + b cos(wt) over every in-life segment: amplitude and phase lag."""
    w = 2 * math.pi / D
    rows, ys = [], []
    for b, s in _particles(proj, res):
        for t, vx, _, _ in _segments(proj, res, b, s):
            rows.append([math.sin(w * t), math.cos(w * t)])
            ys.append(vx)
    (a, bb), *_ = np.linalg.lstsq(np.array(rows), np.array(ys), rcond=None)
    return math.hypot(a, bb), -math.atan2(bb, a)        # vx = G' sin(wt - lag)


def test_drag_makes_rain_lag_and_smooth_the_gust_while_snow_rides_it(proj):
    D, G = 4.0, 100.0
    res = R.apply(proj, "weather", options={"kind": "rain", "layers": 1, "wind": 0.0, "gust": G})
    w, tau = 2 * math.pi / D, A.KINDS["rain"]["tau"]
    amp, lag = _fit_gust(proj, res, D)
    assert amp == pytest.approx(G / math.sqrt(1 + (w * tau) ** 2), rel=0.04), "attenuated by 1/sqrt(1 + (w tau)^2)"
    assert lag == pytest.approx(math.atan(w * tau), abs=0.05), "late by atan(w tau)"
    assert res["gust_gain"] == pytest.approx(1 / math.sqrt(1 + (w * tau) ** 2), abs=1e-3)
    assert res["gust_lag"] == pytest.approx(math.atan(w * tau) / w, abs=1e-3)
    p2 = Project(proj.path.with_name("s.json"), new_skeleton("s", 720, 720))
    res2 = R.apply(p2, "weather", options={"kind": "snow", "layers": 1, "wind": 0.0, "gust": G})
    amp2, lag2 = _fit_gust(p2, res2, D)
    assert amp2 > 0.9 * G and lag2 < 0.25, "a flake (tau 0.1 s) follows the gust"
    assert amp2 > 1.4 * amp


def test_rain_streaks_turn_along_the_velocity(proj):
    res = R.apply(proj, "weather", options={"kind": "rain", "layers": 1, "wind": 200.0, "gust": 0.0})
    vt = A.KINDS["rain"]["vt"]
    rots = [_v(k, "value") for b, _ in _particles(proj, res) for k in _tl(proj, res, b, "rotate")]
    lo, hi = math.degrees(math.atan(200 / (1.15 * vt))), math.degrees(math.atan(200 / (0.85 * vt)))
    # wind to the right: the drop moves down-right, so its tail (+y) turns up-left, a CCW (positive) angle atan(vx / vy)
    assert all(lo - 0.05 <= r_ <= hi + 0.05 for r_ in rots)


def test_embers_rise_slow_to_terminal_speed_cool_and_shrink(proj):
    res = R.apply(proj, "weather", options={"kind": "embers", "layers": 1, "wind": 0.0, "gust": 0.0})
    vt, v0 = A.KINDS["embers"]["vt"], A.KINDS["embers"]["v0"]
    a = proj.data.animations[res["animation"]]
    checked = 0
    for b, s in _particles(proj, res):
        segs = _segments(proj, res, b, s)
        if len(segs) < 8:
            continue
        lives, cur = [], [segs[0]]
        for sg in segs[1:]:                                # a respawn leaves a gap in the visible segments
            if sg[0] - cur[-1][0] > 0.1:
                lives.append(cur)
                cur = []
            cur.append(sg)
        lives.append(cur)
        for lf in lives[1:-1]:                             # the first and last are cut by the loop seam
            if len(lf) < 6:
                continue
            assert all(sg[2] > 0 for sg in lf), "embers rise"
            assert lf[0][2] > 1.6 * lf[-1][2], "drag slows the launch kick"
            assert lf[-1][2] == pytest.approx(vt, rel=0.3)
            checked += 1
        cols = a.slots[s]["rgba"]
        g = [int(k.color[2:4], 16) for k in cols if _alpha(k) > 0.05]
        assert max(g) > 200 and min(g) < 120, "cools from yellow-white toward red"
        sc = [_v(k, "x", 1.0) for k in a.bones[b]["scale"]]
        assert min(sc) < 0.6 and max(sc) > 0.95, "burns down"
    assert checked >= 5 and v0 > 1


def test_petals_swing_tilt_and_flip(proj):
    res = R.apply(proj, "weather", options={"kind": "petals"})
    for b, _ in _particles(proj, res)[:8]:
        sx = [_v(k, "x", 1.0) for k in _tl(proj, res, b, "scale")]
        assert min(sx) < -0.5 and max(sx) > 0.5, "flips over (scaleX through 0)"
        assert all(abs(v) >= 0.1 - 1e-6 for v in sx), "edge-on, never a zero-width sliver"
        rot = [_v(k, "value") for k in _tl(proj, res, b, "rotate")]
        assert max(rot) - min(rot) > 20, "tilts with its swing"


# ---------------------------------------------------------------- god_rays
def test_god_rays_fan_sweeps_and_dims_in_sequence(proj):
    res = R.apply(proj, "god_rays", options={"rays": 6, "sweep": 7.0, "flicker": 0.5})
    D = res["loop"]
    a = proj.data.animations[res["animation"]]
    fan = a.bones[res["fan_bone"]]["rotate"]
    vals = [_v(k, "value") for k in fan]
    assert max(vals) == pytest.approx(7.0, abs=0.05) and min(vals) == pytest.approx(-7.0, abs=0.05)
    rays = [s for s in res["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/ambient_godray"]
    assert len(rays) == 6
    phases = []
    for s in rays:
        ks = a.slots[s]["rgba"][:-1]                        # one full loop, uniform samples
        t = np.array([k.time for k in ks])
        al = np.array([_alpha(k) for k in ks])
        phases.append(np.angle(np.sum((al - al.mean()) * np.exp(-2j * math.pi * t / D))))
    # the occluder pattern travels across the fan: each ray's once-per-loop dimming is delayed by 1.3 cycles over the fan
    for i in range(1, 6):
        d = (phases[i] - phases[0] - (-2 * math.pi * 1.3 * i / 5)) % (2 * math.pi)
        assert min(d, 2 * math.pi - d) < 0.12, i


def test_god_ray_texture_widens_and_fades_with_distance():
    a = np.asarray(A.tex_godray())[..., 3].astype(float)
    h = a.shape[0]
    centre = a[:, a.shape[1] // 2]
    near, far = h - 1 - int(0.1 * h), h - 1 - int(0.7 * h)          # the source is the BOTTOM row
    assert centre[near] > 1.5 * centre[far], "extinction along the ray"
    width = lambda row: (a[row] > 0.5 * a[row].max()).sum()  # noqa: E731
    assert width(far) > 2 * width(near), "divergent: wider far from the source"


# ---------------------------------------------------------------- water_surface
def test_water_rings_spread_as_sqrt_t_and_fire_on_every_landing(proj):
    lands = [[-150.0, 0.0, 0.2], [0.0, 0.0, 0.5], [150.0, -20.0, 0.8]]
    res = R.apply(proj, "water_surface", start=0.1, options={"lands": lands, "life": 1.0, "rings": 1})
    a = proj.data.animations[res["animation"]]
    ev = [(e.time, (e.model_extra or {}).get("int", 0)) for e in a.events if e.name == "fx_water_land"]
    assert ev == [(pytest.approx(0.3), 0), (pytest.approx(0.6), 1), (pytest.approx(0.9), 2)]
    ring = next(b for b in a.bones if b.endswith("_ring0_0"))
    ks = a.bones[ring]["scale"]
    t0 = ks[0].time
    r0 = 0.12
    pts = [(k.time - t0, _v(k, "x", 1.0)) for k in ks if k.time - t0 > 0.05]
    for (s1, r1), (s2, r2) in zip(pts, pts[5:]):
        assert ((r2 - r0) / (r1 - r0)) ** 2 == pytest.approx(s2 / s1, rel=0.02), "capillary ring: r ~ sqrt(t)"
    al = [_alpha(k) for k in a.slots[_slot_of(proj, ring)]["rgba"]]
    peak = int(np.argmax(al))
    assert all(x >= y - 1 / 255 for x, y in zip(al[peak:], al[peak + 1:])), "dims as it spreads and damps"
    assert al[-1] == 0
    land0 = proj.data.bone(next(b for b in proj.data.bones if b.name.endswith("_land0")).name)
    assert (land0.x, land0.y, land0.scaleY) == (-150.0, 0.0, 0.4)
    h = res["ae_hint"]
    assert h["template"] == "caustics" and h["behind"] == res["slots"][0] and h["mode"] == "additive"


# ---------------------------------------------------------------- heat_shimmer
def test_heat_shimmer_wave_rises_with_the_plume(proj):
    res = R.apply(proj, "heat_shimmer", options={"rise": 150.0, "height": 240.0, "wobble": 8.0, "strands": 1})
    D = res["loop"]
    lam = res["wavelength"]
    assert (150.0 * D / lam) == pytest.approx(round(150.0 * D / lam)), "whole wave cycles per loop"
    strip = proj.data.bone(res["anchor_bone"])
    assert (strip.x, strip.y) == (0, 120.0), "the strip rises from the anchor (the top of the fire)"
    a = proj.data.animations[res["animation"]]
    nodes = sorted((b for b in a.bones if "_h0_n" in b), key=lambda b: proj.data.bone(b).y)
    H = 240.0
    yy = lambda b: proj.data.bone(b).y + H / 2  # noqa: E731
    amp = lambda y: 8.0 * (0.35 + 0.65 * y / H)  # noqa: E731

    def x_at(b, t):
        ks = a.bones[b]["translate"]
        return float(np.interp(t % D, [k.time for k in ks], [_v(k, "x") for k in ks]))
    lo, hi = nodes[1], nodes[-2]
    dt = (yy(hi) - yy(lo)) / 150.0                         # the crest climbs at the rise speed
    for t in np.linspace(0, D, 9):
        assert x_at(lo, t) / amp(yy(lo)) == pytest.approx(x_at(hi, t + dt) / amp(yy(hi)), abs=0.06)
    assert res["ae_hint"]["template"] == "heat_shimmer" and res["ae_hint"]["parent"] == res["anchor_bone"]


# ---------------------------------------------------------------- fog_roll
def test_fog_shear_runs_the_top_faster_and_rolls_the_puffs(proj):
    res = R.apply(proj, "fog_roll", options={"kind": "fog", "layers": 1, "speed": 80.0, "shear": 0.8})
    a = proj.data.animations[res["animation"]]
    pts = []
    for s in res["slots"]:
        b = proj.data.slot(s).bone
        segs = _segments(proj, res, b, s)
        y = np.mean([_v(k, "y") for k in a.bones[b]["translate"]]) + proj.data.bone(b).y
        pts.append((y, np.median([sg[1] for sg in segs])))
        rot = [_v(k, "value") for k in a.bones[b]["rotate"]]
        assert min(rot) < -1.0, "rightward shear rolls the parcel clockwise"
    pts.sort()
    ys, vs = np.array(pts).T
    assert np.corrcoef(ys, vs)[0, 1] > 0.8, "speed grows with height"
    assert vs.min() >= 80 * 0.6 - 1 and vs.max() <= 80 * 1.4 + 1


def test_sand_grains_hop_in_saltation(proj):
    res = R.apply(proj, "fog_roll", options={"kind": "sand", "grit": 6})
    a = proj.data.animations[res["animation"]]
    grains = [s for s in res["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/ambient_grit"]
    assert len(grains) == 6
    for s in grains:
        b = proj.data.slot(s).bone
        ks = a.bones[b]["translate"]
        y = np.array([_v(k, "y") for k in ks])
        ground = y.min()
        assert np.sum(np.abs(y - ground) < 1.0) >= 4, "lands back on the ground between hops"
        d2 = [y[i - 1] - 2 * y[i] + y[i + 1] for i in range(1, len(y) - 1)
              if all(abs(ks[j].time - ks[i].time - (j - i) * (ks[i + 1].time - ks[i].time)) < 1e-3 for j in (i - 1, i + 1))
              and y[i] - ground > 2 and y[i] >= min(y[i - 1], y[i + 1])]          # skip the V at a landing
        assert d2 and max(d2) < 0.05, "each hop is a parabola (constant downward curvature)"


# ---------------------------------------------------------------- lightning_storm
def test_storm_schedule_is_a_seeded_poisson_process_with_dead_time():
    t = A.schedule(np.random.default_rng(1), 4000.0, 1.0, 0.3, 0.0, 0.0)
    gaps = np.diff(t)
    assert gaps.min() >= 0.3 - 1e-9 and np.mean(gaps) == pytest.approx(1.0, rel=0.05)
    assert np.std(gaps - 0.3) == pytest.approx(0.7, rel=0.08), "exponential beyond the dead time (std = mean)"
    assert t[:5] == A.schedule(np.random.default_rng(1), 4000.0, 1.0, 0.3, 0.0, 0.0)[:5]


def test_thunder_follows_each_strike_by_distance_over_sound_speed(proj):
    res = R.apply(proj, "lightning_storm", seed=3, options={"rate": 1.0, "sound_speed": 2.0, "distance": [1.0, 4.0]}, duration=10.0)
    a = proj.data.animations[res["animation"]]
    strikes = [e for e in a.events if e.name == "fx_lightning_strike"]
    thunder = sorted((e for e in a.events if e.name == "fx_thunder"), key=lambda e: e.time)
    assert len(strikes) == len(thunder) == len(res["strikes"]) >= 3
    for t, d, x, th in zip(res["strikes"], res["distances"], res["xs"], res["thunder"]):
        assert th == pytest.approx(t + d / 2.0, abs=6e-4) and th < 10.0
        e = next(e for e in thunder if abs(e.time - th) < 1e-3)
        ex = e.model_extra
        assert ex["float"] == pytest.approx(d, abs=1e-3) and ex["volume"] == pytest.approx(1.0 / d, abs=2e-3)
        assert ex["balance"] == pytest.approx(x / 380.0, abs=2e-3)
    h = res["ae_hint"]
    assert h["template"] == "lightning" and len(h["strikes"]) == len(res["strikes"])
    for s, t, x in zip(h["strikes"], res["strikes"], res["xs"]):
        assert s["x"] == x and s["hit_at"] == t and s["start"] == pytest.approx(t - s["hit_ae"])
    proj.save()
    loaded = json.loads(proj.path.read_text())
    assert any("balance" in e for e in loaded["animations"][res["animation"]]["events"]), "audio fields reach the JSON"


def test_storm_flash_decays_as_one_over_t(proj):
    res = R.apply(proj, "lightning_storm", seed=5, options={"restrikes": 0, "rate": 0.3})
    a = proj.data.animations[res["animation"]]
    t0 = res["strikes"][0]
    cloud = next(s for s in res["slots"] if s.endswith("cloud0") or "cloud0" in proj.data.slot(s).bone)
    ks = a.slots[cloud]["rgba"]
    al = lambda t: float(np.interp(t, [k.time for k in ks], [_alpha(k) for k in ks]))  # noqa: E731
    for s1, s2 in ((0.03, 0.12), (0.05, 0.25)):
        assert al(t0 + s1) / al(t0 + s2) == pytest.approx((1 + s2 / 0.04) / (1 + s1 / 0.04), rel=0.08), "1/t decay"
    assert al(t0 - 0.03) == 0 and al(t0 + 0.65) == 0
    bolt = next(s for s in res["slots"] if "bolt0" in proj.data.slot(s).bone)
    kb = a.slots[bolt]["rgba"]
    ab = lambda t: float(np.interp(t, [k.time for k in kb], [_alpha(k) for k in kb]))  # noqa: E731
    assert ab(t0 + 0.05) / ab(t0 + 0.13) == pytest.approx(math.exp(0.08 / 0.05), rel=0.12), "the channel cools e^(-t/50 ms)"
    assert 0 < ab(t0 - 0.02) < 0.3, "a faint stepped leader before the stroke"


def test_storm_without_fallback_bolts_keeps_flashes(proj):
    res = R.apply(proj, "lightning_storm", options={"bolt": False})
    paths = {proj.data.skin("default").attachments[s]["fx"].path for s in res["slots"]}
    assert paths == {"fx/glow"} and res["strikes"]


# ---------------------------------------------------------------- After Effects halves
NEW_TEMPLATES = ["god_rays", "heat_shimmer", "fog_roll"]
TEMPLATE_VARIANTS = [("god_rays", {}), ("god_rays", {"mask": "slats"}), ("heat_shimmer", {}), ("heat_shimmer", {"output": "map"}),
                     ("heat_shimmer", {"output": "preview"}), ("heat_shimmer", {"output": "preview", "image": "/x/bg.png"}),
                     ("fog_roll", {}), ("fog_roll", {"kind": "sand", "speed": -200})]


def test_new_templates_have_headers_and_build(tmp_path):
    t = ae_templates.list_templates()
    assert set(NEW_TEMPLATES) <= set(t)
    for n in NEW_TEMPLATES:
        assert t[n]["doc"] and t[n]["params"]["duration"] > 0
        src = open(ae_templates.build_script(n, {"comp": f"x_{n}"}, tmp_path)["script"]).read()
        assert "var P = " in src and "AEFX.done(comp" in src
    gr = open(ae_templates.build_script("god_rays", {}, tmp_path)["script"]).read()
    assert "ADBE Radial Blur" in gr and "Cycle Evolution" in gr and "Math.sin(time * 2 * Math.PI" in gr
    hs = open(ae_templates.build_script("heat_shimmer", {}, tmp_path)["script"]).read()
    assert "AEFX.loopify" in hs and "BlendingMode.DIFFERENCE" in hs and "ADBE Displacement Map" in hs
    fr = open(ae_templates.build_script("fog_roll", {"kind": "sand"}, tmp_path)["script"]).read()
    assert "AEFX.loopify" in fr and "value[0] + time *" in fr and '"kind": "sand"' in fr
    with pytest.raises(ValueError, match="no parameter"):
        ae_templates.build_script("fog_roll", {"colour": "FF0000"}, tmp_path)


@pytest.mark.parametrize("name,opts", VARIANTS, ids=IDS)
def test_every_ae_hint_builds_its_template(proj, tmp_path, name, opts):
    res = R.apply(proj, name, options=opts or None)
    h = res.get("ae_hint")
    if h is None:
        pytest.skip("Spine only")
    assert h["template"] in ae_templates.list_templates() and h["parent"] in {b.name for b in proj.data.bones}
    for prm in h.get("variants") or [h["params"]]:
        ae_templates.build_script(h["template"], prm, tmp_path)
    if name in ("god_rays", "heat_shimmer", "fog_roll", "water_surface"):
        assert h["seq_mode"] == "loop" and "until" in h


MOCK = r"""
const rec = { expressions: [], comps: [] };
const BM = new Set(["NORMAL", "ADD", "MULTIPLY", "SCREEN", "DIFFERENCE", "OVERLAY", "SOFT_LIGHT", "LIGHTEN", "DARKEN"]);
const BlendingMode = new Proxy({}, { get(_, k) { if (!BM.has(k)) throw new Error("no BlendingMode." + String(k)); return k; } });
const TrackMatteType = { LUMA: "LUMA", ALPHA: "ALPHA", LUMA_INVERTED: "LUMA_INVERTED", ALPHA_INVERTED: "ALPHA_INVERTED" };
const PropertyType = { PROPERTY: "P", INDEXED_GROUP: "IG", NAMED_GROUP: "NG" };
function Shape() {} function KeyframeEase() {} function File(p) { this.p = p; } function ImportOptions(f) { this.f = f; }
function FolderItem() { this.name = "ae_fx_templates"; }
function ok(v, what) {
  const bad = (x) => x === undefined || x === null || (typeof x === "number" && !isFinite(x)) || (Array.isArray(x) && x.some(bad));
  if (bad(v)) throw new Error("bad value for " + what + ": " + JSON.stringify(v));
}
class Node {
  constructor(name) { this.name = name; this.matchName = name; this.kids = {}; this.list = []; this.numKeys = 0; this._e = "";
    this.propertyType = "P"; this.index = 1; this.width = 512; this.height = 512; this.enabled = true; this.inverted = false; }
  property(n) { if (!(n in this.kids)) this.kids[n] = new Node(String(n)); return this.kids[n]; }
  addProperty(n) { const c = new Node(n); this.list.push(c); this.kids[n] = c; this.kids[this.list.length] = c; return c; }
  get numProperties() { return this.list.length; }
  setValue(v) { ok(v, this.name); this.value = v; }
  setValueAtTime(t, v) { ok(t, this.name + " time"); this.setValue(v); this.numKeys++; }
  setValuesAtTimes(ts, vs) { if (ts.length !== vs.length) throw new Error("keys"); ts.forEach((t, i) => this.setValueAtTime(t, vs[i])); }
  setTemporalEaseAtKey() {} removeKey() { this.numKeys--; }
  get expression() { return this._e; }
  set expression(e) { if (typeof e !== "string") throw new Error("expression must be a string"); this._e = e; rec.expressions.push(e); }
  get position() { return this.property("ADBE Position"); } get rotation() { return this.property("ADBE Rotate Z"); }
  get opacity() { return this.property("ADBE Opacity"); } get scale() { return this.property("ADBE Scale"); }
  setTrackMatte(m, t) { if (!(m instanceof Node) || !TrackMatteType[t]) throw new Error("track matte"); }
  moveAfter(l) { if (!(l instanceof Node)) throw new Error("moveAfter"); } duplicate() { return new Node(this.name + "_dup"); }
}
class Comp {
  constructor(name, w, h, pa, dur, fps) {
    [w, h, dur, fps].forEach((v) => { if (!(v > 0)) throw new Error("bad comp " + name); });
    Object.assign(this, { name, width: w, height: h, duration: dur, frameRate: fps });
    const self = this;
    this.layers = { addSolid(c, n, w2, h2) { ok(c, "solid colour"); if (!(w2 > 0 && h2 > 0)) throw new Error("solid size"); const l = new Node(n); l.width = w2; l.height = h2; return l; },
                    add(item) { if (!item) throw new Error("add nothing"); const l = new Node(item.name || "footage"); l.width = item.width; l.height = item.height; return l; },
                    addShape() { return new Node("shape"); } };
  }
}
const items = [];
const app = { project: { get numItems() { return items.length; }, item(i) { return items[i - 1]; },
  items: { addFolder(n) { const f = new FolderItem(); items.push(f); return f; },
           addComp(n, w, h, pa, d, f) { const c = new Comp(n, w, h, pa, d, f); items.push(c); rec.comps.push(n); return c; } },
  importFile(o) { return { name: "img", width: 640, height: 480 }; }, save() {} } };
"""


@pytest.mark.skipif(NODE is None, reason="Node not installed")
@pytest.mark.parametrize("name,opts", TEMPLATE_VARIANTS, ids=[f"{n}-{'-'.join(map(str, o.values()))}".rstrip("-") for n, o in TEMPLATE_VARIANTS])
def test_templates_run_against_a_mock_after_effects(tmp_path, name, opts):
    """No After Effects here: run the generated script in Node against a small mock of the AE object model, so every
    call, enum, value and expression the template uses is exercised (and the expressions are compiled and evaluated)."""
    r = ae_templates.build_script(name, opts, tmp_path)
    src = open(r["script"]).read()
    src = src.replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
    D = r["params"]["duration"]
    js = tmp_path / "run.js"
    js.write_text(MOCK + src + f"""
const out = [];
for (const e of rec.expressions) {{
  const f = new Function("time", "value", "return (" + e + ");");
  out.push([e, [0, {D / 2}, {D}].map((t) => f(t, [10, 20]))]);
}}
console.log(JSON.stringify({{ r: JSON.parse(__r), ex: out, comps: rec.comps }}));
""")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o["r"]["comp"] == r["params"].get("comp", o["r"]["comp"]) and o["r"]["frames"] == round(D * r["params"]["fps"])
    for e, vals in o["ex"]:
        flat = [x for v in vals for x in (v if isinstance(v, list) else [v])]
        assert flat and all(isinstance(x, (int, float)) and math.isfinite(x) for x in flat), e
    if name == "god_rays":                                     # these expressions sit in the final D comp: exact loop
        assert o["ex"] and all(v[0] == pytest.approx(v[2], abs=1e-9) for e, v in o["ex"])
        assert o["r"]["mode"] == "additive"
    if name == "heat_shimmer":
        assert o["r"]["mode"] == {"map": "map", "shimmer": "additive", "preview": "alpha"}[r["params"]["output"]]
        assert any(c.endswith("_map") for c in o["comps"]), "the field is loopified into a map comp"
    if name == "fog_roll":
        assert o["r"]["mode"] == "alpha" and any(c.endswith("_luma") for c in o["comps"])
        rising = [e for e, v in o["ex"] if "value[0] + time" in e]
        assert rising and all((v[2][0] - v[0][0]) * (1 if r["params"]["speed"] >= 0 else -1) > 0 for e, v in o["ex"] if e in rising), \
            "advection runs sideways in the flow direction"


@pytest.mark.skipif(NODE is None, reason="Node not installed")
def test_heat_shimmer_rejects_an_unknown_output(tmp_path):
    r = ae_templates.build_script("heat_shimmer", {"output": "glow"}, tmp_path)
    src = open(r["script"]).read().replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
    js = tmp_path / "run.js"
    js.write_text(MOCK + src)
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode != 0 and "output must be" in p.stderr
