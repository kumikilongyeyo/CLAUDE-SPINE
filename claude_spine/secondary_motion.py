"""Sparse causal secondary motion for editable Spine animation."""
from __future__ import annotations
from .project import Project
from .timeline import FIELDS, DEFAULT, keys

SUPPORTED = ("rotate","translate","translatex","translatey","scale","scalex","scaley","shear","shearx","sheary")

def _scaled_values(k, timeline: str, gain: float) -> list[float]:
    return [float(b) + (float(getattr(k, f)) - float(b)) * gain
            for f, b in zip(FIELDS[timeline], DEFAULT[timeline])]

def solve(project: Project, animation: str, chain: list[str], timelines: list[str] | None = None,
          step_delay: float = 0.035, gain_decay: float = 0.82, settle: float = 0.08,
          ease: str = "sine_out", replace_followers: bool = True) -> dict:
    if len(chain) < 2:
        raise ValueError("chain needs a driver plus at least one follower")
    if step_delay < 0 or settle < 0:
        raise ValueError("step_delay and settle must be >= 0")
    sk = project.data
    for bone in chain:
        sk.bone(bone)
    if animation not in sk.animations:
        raise ValueError(f"animation {animation!r} not found")
    a = sk.animations[animation]
    driver = chain[0]
    source = a.bones.get(driver, {})
    wanted = timelines or [t for t in source if t in SUPPORTED]
    wanted = [t for t in wanted if t in SUPPORTED and t in source]
    if not wanted:
        raise ValueError(f"driver {driver!r} has no supported timelines")

    created = {}
    for depth, follower in enumerate(chain[1:], 1):
        delay = step_delay * depth
        gain = gain_decay ** depth
        dst = a.bones.setdefault(follower, {})
        created[follower] = {}
        for tl in wanted:
            pts = [[float(k.time) + delay, *_scaled_values(k, tl, gain)] for k in source[tl]]
            if settle and pts:
                pts.append([float(pts[-1][0]) + settle, *DEFAULT[tl]])
            generated = keys(pts, tl, ease=ease)
            dst[tl] = generated if replace_followers or tl not in dst else sorted([*dst[tl], *generated], key=lambda k: k.time)
            created[follower][tl] = len(generated)
    return {
        "animation": animation, "driver": driver, "chain": chain,
        "created": created,
        "motion_order": [{"bone": b, "delay": round(step_delay*i,4), "gain": round(gain_decay**i,4)}
                         for i,b in enumerate(chain)],
        "note": "Sparse dependency-driven response; no dense simulation bake.",
    }
