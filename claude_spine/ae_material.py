"""Material-aware multi-pass After Effects -> Spine packaging."""
from __future__ import annotations
from pathlib import Path
from . import ae_bridge
from .project import Project

MATERIALS = {
 "fire":{"physics":{"mass":.15,"drag":.35,"velocity":.9,"turbulence":.78,"buoyancy":.88,"dissipation":.72},
         "frequencies":{"macro":"flame silhouette","mid":"curl + turbulent breakup","micro":"embers + heat grain"},
         "passes":["core","body","embers","smoke","interaction_light","distortion"]},
 "smoke":{"physics":{"mass":.25,"drag":.8,"velocity":.32,"turbulence":.66,"buoyancy":.9,"dissipation":.42},
          "frequencies":{"macro":"rolling volume","mid":"curl/advection","micro":"wispy erosion + grain"},
          "passes":["body","wisps","interaction_light"]},
 "electric":{"physics":{"mass":0.0,"drag":0.0,"velocity":1.0,"turbulence":.5,"buoyancy":0.0,"dissipation":.96},
             "frequencies":{"macro":"primary bolt","mid":"branching","micro":"filaments + sparks"},
             "passes":["core","branches","sparks","interaction_light","lens"]},
 "magic":{"physics":{"mass":.08,"drag":.65,"velocity":.48,"turbulence":.7,"buoyancy":.58,"dissipation":.5},
          "frequencies":{"macro":"energy silhouette","mid":"ribbons + turbulence","micro":"filaments + dust"},
          "passes":["core","ribbons","particles_back","particles_front","interaction_light","lens"]},
 "impact":{"physics":{"mass":.7,"drag":.3,"velocity":1.0,"turbulence":.3,"buoyancy":0.0,"dissipation":.82},
           "frequencies":{"macro":"impact silhouette","mid":"debris + smoke breakup","micro":"sparks + grit"},
           "passes":["core","shockwave","debris","smoke","interaction_light","lens"]},
}
ROLE_DEFAULTS = {
 "core":("additive","additive","subject"),"body":("alpha","normal","subject"),
 "ribbons":("additive","additive","subject"),"branches":("additive","additive","front"),
 "embers":("additive","additive","front"),"sparks":("additive","additive","front"),
 "shockwave":("additive","additive","front"),"debris":("alpha","normal","front"),
 "smoke":("alpha","normal","back"),"wisps":("alpha","normal","front"),
 "particles_back":("additive","additive","back"),"particles_front":("additive","additive","front"),
 "interaction_light":("additive","additive","subject"),"lens":("additive","additive","lens"),
 "distortion":("alpha","normal","runtime_only"),
}

def material_plan(material: str, realism: float = .75) -> dict:
    if material not in MATERIALS:
        raise ValueError(f"material is one of {sorted(MATERIALS)}")
    if not 0 <= realism <= 1:
        raise ValueError("realism must be 0..1")
    m = MATERIALS[material]
    passes = []
    for role in m["passes"]:
        mode, blend, depth = ROLE_DEFAULTS[role]
        passes.append({"role":role,"mode":mode,"blend":blend,"depth":depth,"export":depth!="runtime_only"})
    return {"material":material,"realism":realism,"physics_personality":m["physics"],
            "texture_frequency":m["frequencies"],"passes":passes,
            "rule":"Keep macro/mid/micro breakup and interaction light as separate editable passes."}

def import_package(project: Project, name: str, passes: list[dict], fps: float,
                   animation: str = "", start: float = 0.0, x: float = 0.0, y: float = 0.0,
                   scale: float = 1.0, parent: str = "root", subject_slots: list[str] | None = None,
                   max_size: int = 0, max_frames: int = 0) -> dict:
    if fps <= 0:
        raise ValueError("fps must be positive")
    if not passes:
        raise ValueError("passes must not be empty")
    subjects = subject_slots or []
    for s in subjects:
        project.data.slot(s)
    first, last = (subjects[0], subjects[-1]) if subjects else ("","")
    results = []
    anim_name = animation or f"ae_{name}"
    for i, spec in enumerate(passes):
        role = str(spec.get("role", f"pass{i}"))
        frames_dir = str(spec.get("frames_dir",""))
        if not frames_dir or not Path(frames_dir).expanduser().exists():
            raise FileNotFoundError(f"{role}: frames_dir not found: {frames_dir}")
        mode, blend, depth = ROLE_DEFAULTS.get(role, ("alpha","normal","subject"))
        mode = str(spec.get("mode",mode)); blend = str(spec.get("blend",blend)); depth = str(spec.get("depth",depth))
        if depth == "runtime_only":
            results.append({"role":role,"runtime_only":True,"frames_dir":frames_dir})
            continue
        res = ae_bridge.fx_to_spine(
            project, f"{name}_{role}", frames_dir=frames_dir, fps=fps, mode=mode,
            animation=anim_name, start=start, x=x, y=y, scale=scale, max_size=max_size,
            max_frames=max_frames, blend=blend, color=str(spec.get("color","FFFFFFFF")),
            parent=parent, behind=first if depth=="back" else "",
            front_of=last if depth in ("front","lens") else "",
            fade=float(spec.get("fade",0.0)),
            deform_like=subjects if role=="interaction_light" and subjects else None)
        res["role"] = role; res["depth"] = depth
        results.append(res)
    return {"name":name,"animation":anim_name,"passes":results,"subject_slots":subjects,
            "stack":["back","subject","front","lens"],
            "note":"Material passes remain independently editable; subject light can follow the subject mesh."}
