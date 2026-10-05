"""MCP tools for the face rig: rig_face, face_clip, look_at, lipsync, make_face_sample (engine: rig_face.py).
Imported at the end of server.py so the tools register on the same server."""
from __future__ import annotations

from .server import _open, _saved, mcp
from . import rig_face as face


@mcp.tool()
def make_face_sample(out_dir: str) -> dict:
    """Create the procedural sample face: a mascot head drawn as separate layers named exactly as import_psd names
    a PSD that follows the face convention (face/head, face/eye_L/{white,iris,pupil,highlight,lid_upper,lid_lower},
    face/brow_L, face/nose, face/mouth/{A,E,I,O,U,M,F,L,smile,frown}, face/jaw, face/cheek_L, face/ear_L,
    hair/back, hair/bangs, hair/strand_L ...), all on root. Run rig_face on it."""
    p = face.make_sample_face(out_dir)
    found = face.find_face_parts(p.data)
    return {"project": str(p.path), "slots": [s.name for s in p.data.slots],
            "recognised": {"roles": found["roles"], "mouth": sorted(found["mouth"]), "missing": found["missing"],
                           "unrecognised": found["unrecognised"]}}


@mcp.tool()
def rig_face(project: str = "", parent: str = "", clips: list[str] | None = None, features: dict | None = None,
             turn_range: float = 0, pitch: float = 0.6, talk_text: str = "", seed: int = 7, intensity: float = 1.0,
             idle_duration: float = 4.0, spine: str = "", hair_physics: str = "hair") -> dict:
    """Rig a whole face from named layers in one call, then build its clips.

    Recognises parts by layer name (case-insensitive, _L/_R sides, any group prefix): face/head (REQUIRED; also
    face, skin, base), face/eye_L/{white, iris, pupil, highlight, lid_upper, lid_lower}, face/brow_L, face/nose,
    face/mouth/{A,E,I,O,U,M,F,L} (+ rest, smile, frown) or one plain mouth layer, face/jaw (chin art),
    face/cheek_L, face/ear_L, hair/back, hair/bangs (fringe), hair/strand_* / lock_*. Missing parts are skipped and
    reported. project="" returns the naming convention (FACE_LAYERS) without changing anything.

    Builds: the 2.5D turn (rig_turn) as the base layer; eyes whose iris follows face_look and is CLAMPED inside the
    socket ellipse (one-bone IK with compress inside a (1, ry/rx)-scaled space) with pupil dilation and lid meshes
    that blink to the white's own 70/30 meeting line; 3-bone brows on a mesh; a viseme mouth slot riding a jaw that
    opens by stretching the lower face (scaleX = scaleY^-1/2); cheek bones in the face mesh, stretched by the jaw and
    lifted by face_smile (which also pushes the lower lids: smiling squints); hair strands (chain + mesh + physics)
    and a separate bangs swing bone.

    clips (default all): idle (seamless: breath, Poisson micro-saccades with the head 100 ms behind, Poisson blinks
    80 ms down / 160 ms up), happy, sad, angry, surprised (spring envelopes with exact overshoot, brows a frame
    ahead, surprised anticipates with a 2-frame squash), talk (lipsync of talk_text). Events: sfx_blink, sfx_<clip>,
    sfx_talk, talk_word (string = word), talk_end. parent = the character's head bone (default juice_core or root);
    spine = a body bone that joins look_at two frames after the head. Scales are stored in bone lengths
    (face_rig = face height, turn_base = turn range, face_look_base = full gaze, lid bones = blink travel)."""
    if not project:
        return {"FACE_LAYERS": {k: {"what": v["what"], "aliases": v["aliases"], "required": v.get("required", False)}
                                for k, v in face.FACE_LAYERS.items()},
                "convention": face.face_convention(), "clips": list(face.CLIPS)}
    p = _open(project)
    res = face.rig_face(p, parent or None, features, turn_range or None, pitch,
                        list(face.CLIPS) if clips is None else clips, talk_text or face.TALK_TEXT, seed, intensity,
                        idle_duration, hair_physics, spine=spine or None)
    res.pop("look_levels", None)
    res["eyes"] = {S: {k: v for k, v in e.items() if k != "weights"} for S, e in res["eyes"].items()}
    return _saved(p, res)


@mcp.tool()
def face_clip(project: str, clip: str, duration: float = 0, intensity: float = 1.0, seed: int = 7, text: str = "",
              phonemes: list | None = None, wpm: float = 150, name: str = "", spine: str = "") -> dict:
    """(Re)build one face clip on a rigged face: idle | happy | sad | angry | surprised | talk.
    duration 0 = the clip's default (idle 4 s loop, expressions ~1.8-2 s; talk = the speech + 0.35 s).
    intensity scales amplitudes, seed drives idle's Poisson saccades/blinks, text/phonemes/wpm feed talk,
    name renames the animation (e.g. happy_big)."""
    p = _open(project)
    res = face.add_face_clip(p, clip, duration or None, intensity, seed, text or None, phonemes, wpm, name or None,
                             spine or None)
    res.pop("schedule", None)
    return _saved(p, res)


@mcp.tool()
def look_at(project: str, animation: str, gaze: list[list[float]] | None = None, target: str = "",
            target_range: float = 0, levels: list[dict] | None = None, duration: float = 0, loop: bool = False,
            spine: str = "", counter: bool = True, fps: float = 30) -> dict:
    """Bake a lagged look chain into an animation: eyes -> head -> spine (or any bones: works for bodies).

    gaze [[t, gx, gy], ...]: fixations in normalised gaze units (-1..1, +x = viewer's right, +y = up); saccades are
    instant. Or target = a bone whose translate keys in that animation are the gaze path (divided by target_range,
    default the length of the target's parent bone: face_look_base on a face rig).
    levels [{bone, channel: translate|rotate, range: [x, y] (px, or degrees per unit gaze), weight (share of the
    gaze it takes), lag (dead time s), hz + zeta (damped-spring response), limit (normalised radius for translate,
    degrees for rotate), role: "eyes"}]. Default on a face rig: face_look (eyes, instant), turn_ctrl (0.4 of the
    gaze, 100 ms later, slight overshoot), and spine= (0.15, two frames after the head, via an inserted carrier
    bone so the artist's keys stay). counter=True: the eyes take gaze minus the other levels, so they jump first
    and roll back as the head arrives (vestibulo-ocular reflex). loop=True solves the response periodically."""
    p = _open(project)
    res = face.look_at(p, animation, levels, gaze, target or None, target_range or None, duration or None, loop, fps,
                       counter, spine or None)
    return _saved(p, res)


@mcp.tool()
def lipsync(project: str, text: str = "", phonemes: list | None = None, animation: str = "talk", start: float = 0.0,
            wpm: float = 150, mouth_slot: str = "", jaw_bone: str = "", lead: float = 1 / 30, events: bool = True,
            replace: bool = False, durations: dict | None = None) -> dict:
    """Viseme + jaw keys from text or phonemes into an animation (works on any rig with a mouth slot whose
    attachments are named A E I O U M F L [rest], and/or a jaw bone).

    text: plain English through a tiny grapheme-to-viseme table (digraphs th/sh/ch/ee/oo/ou..., a silent final e
    dropped), timed by wpm (each word 60/wpm s, vowels 1.6x a consonant, , ; . ! ? pause). phonemes: ARPAbet
    (HH AH0 L OW1), viseme letters or rest/sil, optionally [phoneme, seconds]; durations={viseme: s} sets defaults.
    Visemes are stepped attachment keys `lead` s ahead of the sound; the jaw (default face_jaw) eases between
    openness values (A 1, O .8, L .55, E .5, U .4, I .35, F .15, M 0) by scale. A missing viseme falls back to the
    nearest shape. Ends on rest. Events: sfx_talk, talk_word (string = word), talk_end."""
    p = _open(project)
    res = face.lipsync(p, text or None, phonemes, animation, start, wpm, mouth_slot or None, jaw_bone or None, lead,
                       events, replace, durations)
    res.pop("schedule", None)
    return _saved(p, res)
