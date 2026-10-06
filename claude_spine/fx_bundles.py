"""Bundles for ``fx_recipe``: recipes made of recipes.

    sequence    any list of recipes with time offsets into one animation: a win choreography is a JSON list
    win_banner  Big / Mega / Epic win banner from ONE recipe: tier= picks the layers, scales them, and slams the
                game's banner art in on an exact spring (carrier bone, your keys untouched)

A step of a sequence is ``{recipe, start, dx, dy, ...}`` plus any ``fx_recipe`` argument (scale, duration, color,
intensity, seed, count, name, options, art, tier, parent, front_of, behind). Steps share the bundle's x, y, scale,
intensity, tier and animation; ``dx``/``dy`` offset a step from the bundle centre in design units, ``scale`` and
``intensity`` multiply. Draw order chains: each step goes in front of the previous one unless it says otherwise.
The bundle fires ``fx_<name>_end`` at its last key (or at ``length``), which also fixes the clip length.

Registered into fx_recipes.BUNDLES / BUNDLE_INFO at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math

from .fx_recipes import BUNDLE_INFO, BUNDLES, TIERS, Ctx, apply, smooth, times_dense
from .project import Project
from .timeline import AnimBuilder

STEP_KEYS = {"recipe", "start", "dx", "dy", "scale", "duration", "color", "intensity", "seed", "count", "name", "options",
             "art", "tier", "parent", "front_of", "behind", "style", "realism", "style_profile", "relight_slots",
             "relight_color", "relight_strength", "relight_duration"}


def anim_end(project: Project, anim: str) -> float:
    """The time of the last key or event in an animation."""
    a = project.data.animations[anim]
    ts = [0.0]
    for group in (a.bones, a.slots):
        for tl in group.values():
            for ks in tl.values():
                ts += [k.time for k in ks]
    ts += [e.time for e in a.events]
    for skin in a.attachments.values():
        for slot in skin.values():
            for att in slot.values():
                for ks in att.values():
                    ts += [k.time for k in ks]
    return max(ts)


def run_steps(project: Project, steps: list[dict], anim: str, x: float, y: float, scale: float, start: float,
              intensity: float, seed: int, parent: str, front_of: str, behind: str, tier: str,
              style: str = "", realism: float = -1.0, style_profile: dict | None = None,
              relight_slots: list[str] | None = None, relight_color: str = "",
              relight_strength: float = 0.0, relight_duration: float = 0.0) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("a sequence needs options={steps: [{recipe, start, ...}, ...]}")
    parts: list[dict] = []
    last = front_of
    for i, st in enumerate(steps):
        st = dict(st)
        bad = set(st) - STEP_KEYS
        if bad:
            raise ValueError(f"step {i}: unknown key(s) {sorted(bad)}; valid: {sorted(STEP_KEYS)}")
        rec = st.pop("recipe", None)
        if not rec:
            raise ValueError(f"step {i} has no recipe")
        if rec == "sequence":
            raise ValueError(f"step {i}: a sequence cannot contain a sequence; list its steps instead")
        dx, dy = float(st.pop("dx", 0.0)), float(st.pop("dy", 0.0))
        kw = dict(x=x + dx * scale, y=y + dy * scale, scale=scale * float(st.pop("scale", 1.0)),
                  start=start + float(st.pop("start", 0.0)), intensity=intensity * float(st.pop("intensity", 1.0)),
                  seed=int(st.pop("seed", seed + i)), into=anim, parent=st.pop("parent", parent),
                  front_of=st.pop("front_of", last), behind=st.pop("behind", behind if not parts else ""),
                  tier=st.pop("tier", tier), style=st.pop("style", style), realism=float(st.pop("realism", realism)),
                  style_profile=st.pop("style_profile", style_profile or {}))
        # A bundle's reactive light belongs on its hero impact. Steps may override it explicitly; otherwise
        # only the first impact-like member gets the shared target to avoid pulsing on every decorative layer.
        impact_like = rec in {"hit_burst", "explosion", "wild_land", "scatter_trigger", "burst_flare", "shine"}
        if impact_like and relight_slots and "relight_slots" not in st:
            kw.update(relight_slots=relight_slots, relight_color=relight_color, relight_strength=relight_strength,
                      relight_duration=relight_duration)
        kw.update(st)
        res = apply(project, rec, **kw)
        res["step"] = i
        parts.append(res)
        if res.get("slots"):
            last = res["slots"][-1]
    return parts


def _summary(name: str, anim: str, parts: list[dict], project: Project, start: float, length: float) -> dict:
    end = length + start if length else anim_end(project, anim)
    AnimBuilder(project.data, anim, replace=False).event(end, f"fx_{name}_end")
    events = sorted({e.name for e in project.data.animations[anim].events})
    return {"recipe": name, "animation": anim, "parts": [p["recipe"] for p in parts], "steps": len(parts),
            "bones": sum(p.get("bones", 0) for p in parts), "slots": [s for p in parts for s in p.get("slots", [])],
            "events": events, "end": round(end, 4)}


# ------------------------------------------------------------------ sequence
def sequence(project: Project, *, x, y, scale, start, duration, color, intensity, seed, into, parent, front_of, behind,
             count, name, options, art, tier, style="", realism=-1.0, style_profile=None, relight_slots=None,
             relight_color="", relight_strength=0.0, relight_duration=0.0) -> dict:
    """Play a list of recipes with offsets into one animation (a generic magic_reveal)."""
    bad = set(options) - {"steps", "length"}
    if bad:
        raise ValueError(f"unknown option(s) {sorted(bad)} for 'sequence'; valid: ['length', 'steps']")
    if art:
        raise ValueError("a sequence takes art per step: steps=[{recipe, art: {role: spec}}, ...]")
    if duration or color or count:
        raise ValueError("duration / color / count belong to each step of a sequence")
    anim = into or name or "sequence"
    if not into:
        AnimBuilder(project.data, anim, replace=True)
    parts = run_steps(project, options.get("steps"), anim, x, y, scale, start, intensity, seed, parent, front_of, behind, tier,
                      style, realism, style_profile or {}, relight_slots or [], relight_color, relight_strength, relight_duration)
    return _summary(name or "sequence", anim, parts, project, start, float(options.get("length", 0.0)))


# ------------------------------------------------------------------ win_banner
# Each tier: the layers fired at the moment the banner lands (offsets from that moment), and the slam's feel.
BANNER: dict[str, dict] = {
    "big": dict(drop=1.9, t_in=0.16, punch=0.12, steps=[
        dict(recipe="shine", start=0.0, dy=10, options=dict(size=150)),
        dict(recipe="burst_flare", start=0.02, dy=-50),
        dict(recipe="twinkles", start=0.15, duration=2.0, dy=-100),
    ]),
    "mega": dict(drop=2.4, t_in=0.15, punch=0.16, steps=[
        dict(recipe="explosion", start=0.0, dy=-10, options=dict(size=150)),
        dict(recipe="shine", start=0.04, dy=10, options=dict(size=150)),
        dict(recipe="burst_flare", start=0.04, dy=-50),
        dict(recipe="twinkles", start=0.25, duration=2.2, dy=-100),
    ]),
    "epic": dict(drop=3.0, t_in=0.14, punch=0.2, pre=0.36, steps=[
        dict(recipe="lightning_storm", start=-0.34, duration=1.4, dy=40, scale=0.62,
             options=dict(strikes=[[-230, 0.0, 0.25], [230, 0.11, 0.3], [-20, 0.24, 0.2]], width=760, height=620, length=380)),
        dict(recipe="explosion", start=0.0, dy=-10, options=dict(size=150)),
        dict(recipe="shine", start=0.03, dy=10, options=dict(size=150)),
        dict(recipe="burst_flare", start=0.03, dy=-50),
        dict(recipe="rune_ring", start=0.05, dy=-150, scale=0.62),
        dict(recipe="twinkles", start=0.2, duration=2.6, dy=-100),
    ]),
}
BANNER["small"] = dict(BANNER["big"], drop=1.5, t_in=0.18, punch=0.08, steps=BANNER["big"]["steps"][:2])
BANNER["medium"] = BANNER["big"]


def _descendants(project: Project, bone: str) -> set[str]:
    if not project.data.has_bone(bone):
        raise ValueError(f"no bone {bone!r} for the banner")
    out, grow = {bone}, True
    while grow:
        grow = False
        for b in project.data.bones:
            if b.parent in out and b.name not in out:
                out.add(b.name)
                grow = True
    return out


def _slam(punch: float, hz: float = 3.4, zeta: float = 0.32):
    """Unit spring caught at 1 with the slam's speed: 0 at rest, -1 at the deepest squash (see fx_reels._spring)."""
    from .fx_reels import _spring
    return _spring(1.0, hz, zeta)


def win_banner(project: Project, *, x, y, scale, start, duration, color, intensity, seed, into, parent, front_of, behind,
               count, name, options, art, tier, style="", realism=-1.0, style_profile=None, relight_slots=None,
               relight_color="", relight_strength=0.0, relight_duration=0.0) -> dict:
    """Big / Mega / Epic win banner: the banner art slams in from the camera (falls in scale with gravity-like
    acceleration, lands with a volume-preserving squash on an exact spring), and the tier's layers fire on the impact."""
    from .fx_reels import _carrier, _merge_keys
    tier = tier or "big"
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; one of {list(TIERS)}")
    bad = set(options) - {"banner", "skip", "extra", "length", "squash", "shake"}
    if bad:
        raise ValueError(f"unknown option(s) {sorted(bad)} for 'win_banner'; valid: ['banner', 'extra', 'length', 'shake', 'skip', 'squash']")
    if duration or count:
        raise ValueError("win_banner is timed by its tier; retime members with extra steps or a sequence")
    spec = BANNER[tier]
    anim = into or name or f"win_{tier}"
    if not into:
        AnimBuilder(project.data, anim, replace=True)
    pre = spec.get("pre", 0.0)                                      # epic: the strikes come first, then the banner
    t_in, drop, punch = pre + spec["t_in"], spec["drop"], spec["punch"]
    sq = float(options.get("squash", 0.6))
    # the anchor (and the event fx_win_banner) - a Ctx gives the carrier helpers their clock and animation
    c = Ctx(project, "win_banner", x, y, scale, start, 1.0, intensity, seed, anim, parent, front_of, behind, name or "win_banner")
    banner_bone = ""
    if options.get("banner") and not front_of and not behind:
        # the layers go BEHIND the banner art by default: the plate pops in front of the blast, never washed out
        under = _descendants(project, str(options["banner"]))
        firsts = [s.name for s in project.data.slots if s.bone in under]
        behind = firsts[0] if firsts else ""
    if options.get("banner"):
        banner_bone = _carrier(c, str(options["banner"]), "slam")
        k = _slam(punch)
        land = lambda u: k(u - t_in) * (1 - smooth(u, t_in + 0.75, t_in + 1.1)) if u > t_in else 0.0  # noqa: E731
        T = t_in + 1.15

        def scl(u):
            if u < pre:                                             # not in yet
                return (0.0, 0.0)
            if u < t_in:                                            # falling toward the screen: accelerating shrink
                s = drop - (drop - 1) * ((u - pre) / (t_in - pre)) ** 2
                return (s, s)
            v = land(u)                                             # 0 at rest, -1 at the deepest squash
            return (1 - sq * punch * v, 1 + punch * v)              # shorter by punch, wider by squash x punch
        ts = sorted(set(times_dense(0, T, 60)) | {t_in} | ({pre - 0.001, pre} if pre > 0 else set()))
        _merge_keys(c, banner_bone, "scale", ts, scl, "mul")
    skip = set(options.get("skip", []))
    known = {s["recipe"] for s in spec["steps"]}
    if skip - known:
        raise ValueError(f"skip names unknown layer(s) {sorted(skip - known)}; this tier has {sorted(known)}")
    steps = [dict(s, start=s["start"] + t_in) for s in spec["steps"] if s["recipe"] not in skip]
    extra = [dict(s) for s in options.get("extra", [])]
    if any(float(s.get("start", 0.0)) < 0 for s in extra):
        raise ValueError("an extra step starts before the banner; use start >= 0")
    steps += extra
    if options.get("shake"):                                         # the impact shakes the screen (screen_shake, tiered)
        steps.append(dict(recipe="screen_shake", start=t_in, options=dict(shake=str(options["shake"]))))
    if color:
        for s in steps:
            s.setdefault("color", color)
    parts = run_steps(project, steps, anim, x, y, scale, start, intensity, seed + 1, parent, front_of, behind, tier,
                      style, realism, style_profile or {}, relight_slots or [], relight_color, relight_strength, relight_duration)
    out = _summary(name or "win_banner", anim, parts, project, start, float(options.get("length", 0.0)))
    c.ab.event(c.T(0.0), "fx_win_banner")
    c.ab.event(c.T(t_in), "fx_win_banner_land")
    out.update(tier=tier, land_at=round(c.T(t_in), 4), banner_bone=banner_bone, group_bone=c.group,
               events=sorted({e.name for e in project.data.animations[anim].events}))
    return out


# ------------------------------------------------------------------ registry
BUNDLES.update({"sequence": sequence, "win_banner": win_banner})
BUNDLE_INFO.update({
    "sequence": {
        "summary": "Any list of recipes with time offsets, played into one animation: a win choreography is a JSON list. "
                   "Steps share the bundle's x, y, scale, intensity and tier; dx/dy offset a step, scale/intensity multiply, "
                   "draw order chains step after step. Fires fx_<name>_end at the last key (or at length).",
        "kind": "bundle", "anchor": "Bundle centre (steps offset by dx, dy)", "default_duration": 0.0,
        "options": {"steps": {"default": [], "what": "[{recipe, start, dx, dy, scale, duration, color, intensity, seed, count, "
                                                       "name, options, art, tier, parent, front_of, behind}, ...]"},
                    "length": {"default": 0.0, "what": "> 0: clip length (end event) instead of the last key"}},
        "art_note": "art per step: steps=[{recipe, art: {role: spec}}]",
    },
    "win_banner": {
        "summary": "Big / Mega / Epic win banner from one recipe: tier= picks the layers (big: shine + flare + twinkles; mega: "
                   "+ explosion; epic: + three lightning strikes with thunder, rune ring) and scales them. options={banner: bone} slams the game's "
                   "banner art in from the camera through a carrier bone (accelerating fall in scale, volume-preserving squash "
                   "on an exact spring), never touching your keys. Events fx_win_banner, fx_win_banner_land, every layer's own, "
                   "fx_win_banner_end.",
        "kind": "bundle", "anchor": "Banner centre", "default_duration": 0.0,
        "options": {"banner": {"default": "", "what": "bone of the banner art to slam in (a carrier is inserted above it)"},
                    "skip": {"default": [], "what": "layer recipes of the tier to leave out"},
                    "extra": {"default": [], "what": "more sequence steps (start relative to the banner start)"},
                    "shake": {"default": "", "what": "bone to shake on the impact (screen_shake at the tier; e.g. the screen container)"},
                    "squash": {"default": 0.6, "what": "how much the landing squash widens the banner (0 = uniform scale)"},
                    "length": {"default": 0.0, "what": "> 0: clip length instead of the last key"}},
        "tiers": {t: [s["recipe"] for s in BANNER[t]["steps"]] for t in TIERS},
    },
})
