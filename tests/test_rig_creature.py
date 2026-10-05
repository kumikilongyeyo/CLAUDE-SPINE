"""rig_creature: every kind builds from its procedural sample, validates, fits the mobile_character budget, keeps the
clip contract (exact loops, one-shots on setup) and plays in spine-core; plus one or more PHYSICS checks per kind read
back from the keys (volume squash, spring overshoot, critically damped lag, closed incommensurate periods, sqrt growth,
hinge overshoot and bounces), the layer conventions, clear errors and the MCP tools."""
import asyncio
import json
import math

import numpy as np
import pytest

from claude_spine import qa, rig_chain as C, rig_creature as R, runtime
from claude_spine.ir import new_skeleton, parse_color
from claude_spine.project import Project
from conftest import needs_node

ONESHOT_EXCEPT = {"fade_out", "grow"}


# ---------------------------------------------------------------- helpers
def vals(k, tl):
    if tl == "rotate":
        return (C.key_val(k, "value", 0.0),)
    if tl in ("scalex", "scaley"):
        return (C.key_val(k, "value", 1.0),)
    if tl in ("translate", "shear"):
        return (C.key_val(k, "x", 0.0), C.key_val(k, "y", 0.0))
    if tl == "scale":
        return (C.key_val(k, "x", 1.0), C.key_val(k, "y", 1.0))
    return (getattr(k, "value", 0.0),)


def keys(sk, anim, bone, tl):
    ks = sk.animations[anim].bones[bone][tl]
    return np.array([k.time for k in ks]), np.array([vals(k, tl) for k in ks])


def assert_loop(sk, anim):
    a = sk.animations[anim]
    for bn, tls in a.bones.items():
        for tl, ks in tls.items():
            if len(ks) > 1:
                assert vals(ks[0], tl) == pytest.approx(vals(ks[-1], tl), abs=1e-3), f"{anim}/{bn}/{tl} does not close"
    for sn, tls in a.slots.items():
        for tl, ks in tls.items():
            if tl == "rgba" and len(ks) > 1:
                assert ks[0].color == ks[-1].color, f"{anim}/{sn} colour does not close"


def assert_rest_at_end(sk, anim):
    a = sk.animations[anim]
    for bn, tls in a.bones.items():
        if bn.startswith("fx_"):
            continue                                  # FX recipe bones: their slots are hidden by then
        for tl, ks in tls.items():
            rest = {"scale": (1.0, 1.0), "translate": (0.0, 0.0), "shear": (0.0, 0.0), "scalex": (1.0,), "scaley": (1.0,)}.get(tl, (0.0,))
            assert vals(ks[-1], tl) == pytest.approx(rest, abs=2e-3), f"{anim}/{bn}/{tl} does not end on setup"
    for c, ks in a.ik.items():
        mix = next(i.mix for i in sk.ik if i.name == c)
        assert C.key_val(ks[-1], "mix", 1.0) == pytest.approx(mix), f"{anim}/{c} ik mix does not end on setup"


def alpha(k):
    return parse_color(k.color)[3]


def run(p, anims, fps=10):
    d = runtime.run(p, animations=anims, fps=fps, geometry=True)
    assert d.get("ok", True) and not d.get("problems"), d.get("problems") or d.get("error")
    return d


@pytest.fixture(scope="module")
def rigs(tmp_path_factory):
    out = {}
    root = tmp_path_factory.mktemp("creatures")
    for k in R.KINDS:
        p = R.make_sample_creature(root / k, k)
        out[k] = (p, R.rig_creature(p, k))
        p.save()
    return out


# ================================================================ every kind: structure, contract, budget, runtime
@pytest.mark.parametrize("kind", R.KINDS)
def test_kind_builds_validates_fits_the_budget_and_keeps_the_clip_contract(rigs, kind):
    p, res = rigs[kind]
    sk = p.data
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    b = qa.budget(sk, "mobile_character")
    assert b["ok"], b["over_budget"]
    assert res["budget"]["ok"] and res["counts"]["bones"] == len(sk.bones)
    assert set(R.CREATURE_CLIPS[kind]) <= set(sk.animations)
    for clip in R.CREATURE_CLIPS[kind]:
        if clip in R.LOOPS:
            assert_loop(sk, clip)
        elif clip not in ONESHOT_EXCEPT:
            assert_rest_at_end(sk, clip)
    for s in sk.slots:
        if s.blend == "additive":
            assert s.attachment is None, f"{s.name}: FX slots are hidden in the setup pose"
    adds = [i for i, s in enumerate(sk.slots) if s.blend == "additive"]
    if adds:
        assert adds == list(range(adds[0], adds[0] + len(adds))), "the additive slots are one run (one batch)"
    named = [e.name for c in R.CREATURE_CLIPS[kind] for e in sk.animations[c].events]
    assert any(n.startswith("sfx_") for n in named)


@needs_node
@pytest.mark.parametrize("kind", R.KINDS)
def test_kind_plays_in_spine_core(rigs, kind):
    p, _ = rigs[kind]
    run(p, list(R.CREATURE_CLIPS[kind]))


# ================================================================ conventions and errors
def test_listing_names_every_kind_with_its_layers_clips_and_options():
    lst = R.rig_creature(Project("x.json", new_skeleton()), "")["kinds"]
    assert set(lst) == set(R.KINDS)
    for k, v in lst.items():
        assert v["layers"] and v["clips"] == list(R.CREATURE_CLIPS[k]) and v["options"]
        assert any("REQUIRED" in d for d in v["layers"].values())


@pytest.mark.parametrize("kind", R.KINDS)
def test_missing_required_layers_is_a_clear_error(tmp_path, kind):
    p = Project(tmp_path / "e.json", new_skeleton())
    with pytest.raises(ValueError, match="missing required layer"):
        R.rig_creature(p, kind)


def test_bad_options_and_arguments(tmp_path):
    def fresh(k):
        return R.make_sample_creature(tmp_path / f"{k}{np.random.randint(1e9)}", k)
    with pytest.raises(ValueError, match="unknown creature kind"):
        R.rig_creature(fresh("slime"), "kraken")
    with pytest.raises(ValueError, match="unknown option"):
        R.rig_creature(fresh("slime"), "slime", options={"wobbliness": 2})
    with pytest.raises(ValueError, match="squash"):
        R.rig_creature(fresh("slime"), "slime", options={"squash": 0.1})
    with pytest.raises(ValueError, match="law"):
        R.rig_creature(fresh("slime"), "slime", options={"law": "mass"})
    with pytest.raises(ValueError, match="zeta must be >= 1"):
        R.rig_creature(fresh("golem"), "golem", options={"zeta": 0.5})
    with pytest.raises(ValueError, match="no loop"):
        R.rig_creature(fresh("ghost"), "ghost", options={"bob": 1.7, "sway": 2.9, "tolerance": 0.001, "max_loop": 6})
    with pytest.raises(ValueError, match="unknown clip"):
        R.rig_creature(fresh("mimic"), "mimic", clips=["dance"])
    with pytest.raises(ValueError, match="exaggerate"):
        R.rig_creature(fresh("plant"), "plant", exaggerate=0)
    with pytest.raises(ValueError, match="gait is"):
        R.rig_creature(fresh("insect"), "insect", options={"gait": "gallop"})
    p = fresh("slime")
    R.rig_creature(p, "slime")
    with pytest.raises(ValueError, match="already rigged"):
        R.rig_creature(p, "slime")
    with pytest.raises(ValueError, match="unknown creature kind"):
        R.make_sample_creature(tmp_path / "x", "kraken")


def test_optional_parts_are_skipped_not_errors(tmp_path):
    for kind, keep in (("slime", {"body"}), ("golem", {"torso"}), ("ghost", {"body"}), ("mimic", {"base", "lid"}),
                       ("plant", {"trunk"})):
        p = R.make_sample_creature(tmp_path / kind, kind)
        sk = p.data
        sk.slots = [s for s in sk.slots if s.name in keep]
        sk.skin().attachments = {k: v for k, v in sk.skin().attachments.items() if k in keep}
        R.rig_creature(p, kind)
        assert qa.validate(sk)["ok"], (kind, qa.validate(sk)["errors"])
        assert set(R.CREATURE_CLIPS[kind]) <= set(sk.animations)


def test_clips_subset(tmp_path):
    p = R.make_sample_creature(tmp_path / "s", "slime")
    res = R.rig_creature(p, "slime", clips=["idle", "hop"])
    assert set(res["clips"]) == {"idle", "hop"} and set(p.data.animations) == {"idle", "hop"}


# ================================================================ 1. slime
def test_slime_squash_keeps_the_volume_and_the_hop_is_ballistic(rigs):
    p, res = rigs["slime"]
    sk = p.data
    hop = res["bones"]["hop"]
    assert 6 <= len(res["bones"]["outline"]) <= 8 and len(res["physics"]) == len(res["bones"]["outline"])
    t, s = keys(sk, "hop", hop, "scale")
    assert np.allclose(s[:, 0] ** 2 * s[:, 1], 1.0, atol=2e-3), "sx^2 sy = 1: a 3D blob keeps its volume"
    i = int(np.argmin(np.where(t < 0.3, s[:, 1], 9)))
    assert s[i, 1] == pytest.approx(0.7, abs=1e-3) and s[i, 0] == pytest.approx(0.7 ** -0.5, abs=2e-3), "0.7 -> 1.195"
    hc = res["clips"]["hop"]
    t, y = keys(sk, "hop", hop, "translate")
    H = hc["apex"]
    assert y[:, 1].max() == pytest.approx(H, rel=1e-3), "the parabola's apex is exactly the hop height"
    ta, tl = hc["launch"], hc["land"]
    for q in (0.25, 0.5, 0.75):
        tt = ta + q * (tl - ta)
        assert float(np.interp(tt, t, y[:, 1])) == pytest.approx(4 * H * q * (1 - q), rel=0.02), "y = 4 H q (1 - q)"
    after = t > tl + 0.05
    assert s[after, 1].max() == pytest.approx(hc["splat_peak"], abs=2e-3), "the splat overshoots exactly"
    assert hc["splat_peak"] == pytest.approx(1 + 0.4 * C.spring_overshoot(0.28), abs=1e-4)
    ev = {e.name: e.time for e in sk.animations["hop"].events}
    assert ev["sfx_hop"] == pytest.approx(ta) and ev["sfx_land"] == pytest.approx(tl)
    assert R.RAYLEIGH_3_2 == pytest.approx(1.936, abs=1e-3)


def test_slime_area_law_and_outline_wobble_rings_down(tmp_path):
    p = R.make_sample_creature(tmp_path / "s", "slime")
    res = R.rig_creature(p, "slime", options={"law": "area", "n_outline": 6})
    sk = p.data
    t, s = keys(sk, "hop", res["bones"]["hop"], "scale")
    assert np.allclose(s[:, 0] * s[:, 1], 1.0, atol=2e-3), "area law: sx sy = 1"
    side = res["bones"]["outline"][[k for k in range(6) if abs(math.cos(math.radians(90 + 60 * k))) > 0.8][0]]
    t, tr = keys(sk, "hop", side, "translate")
    tl = res["clips"]["hop"]["land"]
    r = np.hypot(tr[:, 0], tr[:, 1])
    early, late = r[(t > tl) & (t < tl + 0.25)].max(), r[(t > tl + 0.45)].max()
    assert late < 0.35 * early, "the landing wobble is a damped ring"


# ================================================================ 2. golem
def test_golem_parts_lag_through_a_critically_damped_filter(rigs):
    p, res = rigs["golem"]
    sk = p.data
    body, head = res["bones"]["body"], res["bones"]["head"]
    D = sk.animations["idle"].duration()
    tb, rb = keys(sk, "idle", body, "rotate")
    th, rh = keys(sk, "idle", head, "rotate")
    abs_head = rh[:, 0] + np.interp(th, tb, rb[:, 0])

    def phase_amp(t, v):
        A = np.c_[np.sin(2 * math.pi * t / D), np.cos(2 * math.pi * t / D)]
        a, b = np.linalg.lstsq(A, v, rcond=None)[0]
        return math.atan2(b, a), math.hypot(a, b)
    pb, ab = phase_amp(tb, rb[:, 0])
    ph, ah = phase_amp(th, abs_head)
    w0, z, w = 1 / 0.12, 1.0, 2 * math.pi / D
    H = w0 ** 2 / complex(w0 ** 2 - w ** 2, 2 * z * w0 * w)
    assert ah / ab == pytest.approx(abs(H), rel=0.01) and (ph - pb) == pytest.approx(np.angle(H), abs=0.01), \
        "head = body through x'' + 2 z w0 x' + w0^2 x = w0^2 u"
    levels = {d["bone"]: d["level"] for d in res["lagged"]}
    assert levels[res["bones"]["fist_l"]] == 2 and levels[res["bones"]["arm_l"]] == 1, "lag by levels"


def test_lowpass_never_overshoots_and_stomp_shakes_the_screen(rigs):
    for z in (1.0, 1.6):
        y = R.lowpass(np.ones(4000), 1 / 1200, 8.0, z)
        assert np.all(np.diff(y) >= -1e-12) and y.max() <= 1 + 1e-9, "critically / over-damped: monotonic, no overshoot"
    p, res = rigs["golem"]
    sk = p.data
    ev = [e for e in sk.animations["stomp"].events if e.name == "screen_shake"]
    assert len(ev) == 1 and ev[0].time == pytest.approx(res["clips"]["stomp"]["impact"]) and getattr(ev[0], "float") > 0
    assert getattr(ev[0], "int") == 350
    t, y = keys(sk, "stomp", res["bones"]["body"], "translate")
    ts = res["clips"]["stomp"]["impact"]
    assert y[:, 1].min() == pytest.approx(-res["clips"]["stomp"]["compression"], abs=0.05), "compressed at impact"
    assert np.all(y[t > ts, 1] <= 1e-6), "critically damped recovery: it never bounces back up past rest"
    g = res["glows"][0]
    a = sk.animations["stomp"].slots[g]["rgba"]
    ta = np.array([k.time for k in a])
    av = np.array([alpha(k) for k in a])
    assert av[np.argmin(abs(ta - ts) + (ta < ts))] > 0.95 and av[-1] == pytest.approx(0.5, abs=0.01), "seams flash then settle"


# ================================================================ 3. ghost
def test_ghost_periods_are_incommensurate_but_close_exactly(rigs):
    n1, n2, D = R.close_periods(1.7, 2.9)
    assert (n1, n2) == (5, 3) and n1 != n2 and math.gcd(n1, n2) == 1
    assert abs(D / n1 / 1.7 - 1) <= 0.05 and abs(D / n2 / 2.9 - 1) <= 0.05
    p, res = rigs["ghost"]
    sk = p.data
    assert sk.animations["idle"].duration() == pytest.approx(D, abs=1e-3)
    t, tr = keys(sk, "idle", res["bones"]["float"], "translate")

    def cycles(v):
        u = np.interp(np.linspace(0, D, 2048, endpoint=False), t, v)
        return int(np.argmax(np.abs(np.fft.rfft(u - u.mean()))))
    assert cycles(tr[:, 1]) == n1 and cycles(tr[:, 0]) == n2, "bob and sway run at their own whole numbers of cycles"
    a = [alpha(k) for k in sk.animations["idle"].slots["body"]["rgba"]]
    a0 = parse_color(sk.slot("body").color)[3]
    assert a[0] == pytest.approx(a0, abs=0.01) and min(a) == pytest.approx(a0 * (1 - 0.22), abs=0.01), "alpha breathes"
    assert len(res["bones"]["chain"]) == 5 and len(res["bones"]["strands"]) == 4


def test_ghost_fades_hand_over_invisibly(rigs):
    p, _ = rigs["ghost"]
    sk = p.data
    out, inn = sk.animations["fade_out"], sk.animations["fade_in"]
    for s, tls in out.slots.items():
        assert alpha(tls["rgba"][-1]) == 0, f"{s} ends invisible"
        assert alpha(inn.slots[s]["rgba"][0]) == 0, f"{s} starts invisible"
        assert alpha(inn.slots[s]["rgba"][-1]) == pytest.approx(parse_color(sk.slot(s).color)[3], abs=0.01)
    assert_rest_at_end(sk, "fade_out")
    assert [e.name for e in sk.animations["swoop"].events] == ["sfx_swoop"]


# ================================================================ 4. tentacle beast
def test_tentacles_have_their_own_phase_and_reach_ik_on_the_tips(rigs):
    p, res = rigs["tentacle"]
    sk = p.data
    T = res["tentacles"]
    assert len(T) == 5
    for t in T.values():
        ik = next(c for c in sk.ik if c.name == t["reach_ik"])
        assert ik.mix == 0 and ik.bones == t["bones"][-2:], "reach IK on the tip, off in the setup"
    tips = [keys(sk, "idle", t["bones"][-1], "rotate")[1][:, 0] for t in T.values()]
    for a in range(len(tips)):
        for b in range(a + 1, len(tips)):
            n = min(len(tips[a]), len(tips[b]))
            assert np.corrcoef(tips[a][:n], tips[b][:n])[0, 1] < 0.95, "each tentacle its own phase"
    m = T[res["reach_tentacle"]]
    ks = sk.animations["reach"].ik[m["reach_ik"]]
    mixes = [C.key_val(k, "mix", 0.0) for k in ks]
    assert mixes[0] == 0 and mixes[-1] == 0 and max(mixes) == pytest.approx(1.0, abs=1e-3), "the grab blends the IK in"
    names = [e.name for e in sk.animations["reach"].events]
    assert "sfx_reach" in names and "sfx_grab" in names


def test_suckers_swap_with_stretch_and_slam_whips(rigs):
    p, res = rigs["tentacle"]
    sk = p.data
    m = res["reach_tentacle"]
    sw = res["clips"]["reach"]["sucker_swap"]
    for s in res["suckers"][m]:
        ks = sk.animations["reach"].slots[s]["attachment"]
        assert [k.name for k in ks] == ["sucker", "sucker_stretched", "sucker"]
        assert ks[1].time == pytest.approx(sw[0], abs=1e-3)
        assert set(sk.skin().attachments[s]) == {"sucker", "sucker_stretched"}
    assert sk.slot("sucker").attachment is None, "the sucker template is hidden"
    t, sc = keys(sk, "reach", T0 := res["tentacles"][m]["bones"][0], "scale")
    assert sc[:, 0].max() == pytest.approx(res["clips"]["reach"]["stretch"], abs=2e-3) and T0
    imp = res["clips"]["slam"]["impact"]
    ev = [e for e in sk.animations["slam"].events if e.name == "screen_shake"]
    assert ev and ev[0].time == pytest.approx(imp)
    tent = next(iter(res["tentacles"].values()))
    t0, d0 = keys(sk, "slam", tent["drive"], "rotate")
    t1, d1 = keys(sk, "slam", tent["bones"][-1], "rotate")
    assert t1[np.argmax(np.abs(d1[:, 0]))] > t0[np.argmax(np.abs(d0[:, 0]))], "the whip: the tip peaks after the base"


# ================================================================ 5. dragon
def test_dragon_composes_quadruped_serpents_wings_and_fire(rigs):
    p, res = rigs["dragon"]
    sk = p.data
    for b in ("q_body", "ik_front_L", "ik_hind_R", "dragon_head", "dragon_jaw", "dragon_breath"):
        assert sk.has_bone(b), b
    assert len(res["neck"]["bones"]) == 4 and len(res["tail"]["bones"]) == 6 and len(res["wings"]) == 2
    assert sk.bone("head").parent == "dragon_head" and sk.bone("dragon_head").parent == res["neck"]["bones"][-1]
    fire = sk.slot(res["fire"])
    att = sk.skin().attachments[res["fire"]]["fire"]
    assert fire.blend == "additive" and fire.attachment is None and att.sequence.count == 8
    br = sk.animations["breath"]
    t0, t1 = res["clips"]["breath"]["fire"]
    assert [k.name for k in br.slots[res["fire"]]["attachment"]][:2] == [None, "fire"]
    assert br.attachments["default"][res["fire"]]["fire"]["sequence"][0].mode == "loop"
    hint = res["clips"]["breath"]["ae_hint"]
    assert hint["template"] == "fire" and hint["parent"] == res["bones"]["ae"] and hint["start"] == t0
    t, sc = keys(sk, "breath", res["bones"]["breath"], "scale")
    for dt in (0.05, 0.15, 0.3):
        assert float(np.interp(t0 + dt, t, sc[:, 0])) == pytest.approx(math.sqrt(dt / 0.35), abs=0.02), "jet front ~ sqrt(t)"
    steps = [e for e in sk.animations["walk"].events if e.name == "sfx_step"]
    assert len(steps) == 4 and {e.string for e in steps} == {"front_L", "front_R", "hind_L", "hind_R"}
    fly = sk.animations["fly"]
    assert sum(e.name == "sfx_flap" for e in fly.events) == res["clips"]["fly"]["beats"]
    assert any(e.name == "screen_shake" for e in sk.animations["roar"].events)
    assert any(e.name == "fx_fire" for e in br.events)


def test_fire_flipbook_loops_exactly():
    a, b = R.fire_frames(96, 40, 8, seed=3), R.fire_frames(96, 40, 4, seed=3)
    assert np.array_equal(np.asarray(a[0]), np.asarray(b[0])) and np.array_equal(np.asarray(a[2]), np.asarray(b[1])), \
        "frame k is phase k / F of one whole advection cycle: frame F would be frame 0"
    assert not np.array_equal(np.asarray(a[0]), np.asarray(a[1]))


# ================================================================ 6. insect
def test_insect_walks_on_the_tripod_and_flies_on_a_blur_flipbook(rigs):
    p, res = rigs["insect"]
    sk = p.data
    steps = [(round(e.time, 3), e.string) for e in sk.animations["walk"].events if e.name == "sfx_step"]
    t0 = {s: t for t, s in steps if t < res["clips"]["walk"]["period"] - 1e-6}
    assert t0["L1"] == t0["R2"] == t0["L3"] and t0["R1"] == t0["L2"] == t0["R3"] != t0["L1"], "alternating tripod"
    assert len(res["antennae"]) == 2 and len(res["legs"]) == 6
    fly = sk.animations["fly"]
    for s in res["bones"]["wings"]:
        assert fly.slots[s]["attachment"][0].name == "blur"
        att = sk.skin().attachments[s]["blur"]
        assert att.sequence.count == 6 and sk.slot(s).attachment == s, "folded art in setup, the blur in fly"
        seq = fly.attachments["default"][s]["blur"]["sequence"][0]
        assert seq.mode == "loop" and sk.animations["fly"].duration() / (seq.delay * 6) == pytest.approx(
            res["clips"]["fly"]["blur_loops"], abs=1e-3), "the flipbook loops a whole number of times per fly loop"
    frames, S = R.wing_blur_frames(p.image(p.att_image_name("wing_r", "wing_r")), (60, 20), 55, 6, 70, -1)
    assert len(frames) == 6 and frames[0].size == (S, S)


# ================================================================ 7. plant
def test_plant_grows_diffusion_limited(rigs):
    p, res = rigs["plant"]
    sk = p.data
    g = res["clips"]["grow"]
    tb = res["bones"]["trunk"]
    lens = [sk.bone(b).length for b in tb]
    L, T = sum(lens), g["trunk_time"]
    tt = keys(sk, "grow", tb[0], "scale")[0]
    W = np.ones(len(tt))
    front = np.zeros(len(tt))
    for b, l in zip(tb, lens):
        t, sc = keys(sk, "grow", b, "scale")
        W = W * np.interp(tt, t, sc[:, 0])
        front += l * np.clip(W, 0, 1)
    sel = (front > 0.15 * L) & (front < 0.95 * L)
    assert sel.sum() > 5
    assert np.allclose((front[sel] / L) ** 2, tt[sel] / T, atol=0.03), "s = L sqrt(t / T): the tip races, then slows"
    br = g["branches"]
    r = [v["time"] / v["length"] ** 2 for v in br.values()]
    assert np.allclose(r, r[0], rtol=1e-3) and r[0] == pytest.approx(1 / (2 * g["k"]), rel=1e-3), "T = L^2 / (2 k)"
    for v in br.values():
        assert 0 < v["start"] < T, "a branch sprouts when the trunk's front passes its root"
    leaf = next(iter(res["leaves"].values()))
    t, sc = keys(sk, "grow", leaf, "scale")
    assert sc[:, 0].max() == pytest.approx(0.01 + 0.99 * (1 + C.spring_overshoot(0.4)), abs=3e-3), "leaves pop on a spring"
    assert sc[-1, 0] == pytest.approx(1.0) and sc[0, 0] == pytest.approx(0.01)
    for r_ in res["roots"].values():
        ik = next(c for c in sk.ik if c.name == r_["ik"])
        assert sk.bone(ik.target).parent == "plant", "root feet are planted (IK targets on the ground frame)"
    assert len(res["leaves"]) == 8 and len(res["branches"]) == 4


# ================================================================ 8. mimic
def test_mimic_hinge_overshoots_and_bounces_shut(rigs):
    p, res = rigs["mimic"]
    sk = p.data
    lid = res["bones"]["lid"]
    o = res["clips"]["open"]
    t, v = keys(sk, "open", lid, "rotate")
    assert v[:, 0].max() == pytest.approx(105 * (1 + C.spring_overshoot(0.32)), rel=2e-3), "the hinge spring overshoots exactly"
    assert o["overshoot_angle"] == pytest.approx(105 * (1 + C.spring_overshoot(0.32)), abs=1e-2)
    th, e = o["close_from"], 0.3
    for k in (1, 2):
        assert R.lid_bounce(0, 0.2, th, 0.2, e) == th
        start = 0.2 + sum(2 * e ** j * 0.2 for j in range(1, k))
        peak = R.lid_bounce(start + e ** k * 0.2, 0.2, th, 0.2, e)
        assert peak == pytest.approx(th * e ** (2 * k), rel=1e-6), "bounce k rises e^(2k) as high"
    assert np.all(v[t > o["close_hit"], 0] >= -1e-6), "the lid never goes through the rim"
    names = [x.name for x in sk.animations["open"].events]
    assert {"sfx_open", "sfx_close", "fx_shine"} <= set(names)
    for c in ("land", "win"):
        a = sk.animations[c]
        assert "juice_ground" in a.bones and lid in a.bones, f"{c}: the juice_apply contract plus the lid"
    assert any(x.name == "sfx_bite" for x in sk.animations["bite"].events)


# ================================================================ MCP tools
def test_the_mcp_tools(tmp_path):
    from claude_spine import tools_creature  # noqa: F401  registers the tools
    from claude_spine.server import mcp

    def call(tool, **args):
        r = asyncio.run(mcp.call_tool(tool, args))
        content = r[0] if isinstance(r, tuple) else r
        return json.loads(content[0].text)
    kinds = call("rig_creature")["kinds"]
    assert set(kinds) == set(R.KINDS) and "law" in kinds["slime"]["options"]
    s = call("make_creature_sample", out_dir=str(tmp_path / "s"), kind="slime")
    out = call("rig_creature", project=s["project"], kind="slime", options={"n_outline": 6})
    assert "validation_errors" not in out and len(out["bones"]["outline"]) == 6
    assert "hop" in Project.open(s["project"]).data.animations
    m = call("make_creature_sample", out_dir=str(tmp_path / "m"), kind="mimic")
    out = call("rig_creature", project=m["project"], kind="mimic", clips=["idle", "open"])
    assert set(out["clips"]) == {"idle", "open"} and out["budget"]["ok"]
