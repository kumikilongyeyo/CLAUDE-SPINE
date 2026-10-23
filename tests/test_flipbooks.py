"""Ready AE flipbooks (claude_spine/flipbooks.py, fx_flipbook): stored renders dropped on any skeleton."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_templates, flipbooks as F, fx_emitter as E, qa
from claude_spine.ir import new_skeleton
from claude_spine.project import Project


@pytest.fixture
def proj(tmp_path):
    p = Project(tmp_path / "t.json", new_skeleton("t", 720, 720))
    p.save()
    return p


@pytest.fixture
def fake_books(tmp_path, monkeypatch):
    """Two small stored flipbooks in the real format (WebP frames + meta), so tests run without the renders."""
    root = tmp_path / "books"
    monkeypatch.setenv("CLAUDE_SPINE_FLIPBOOKS", str(root))
    for name, mode, parts in (("glow_pulse", "alpha", ["main"]), ("win_aura", "additive", ["in", "loop", "out"])):
        meta = {"name": name, "template": name, "mode": mode, "seq_mode": "once" if name == "glow_pulse" else "loop",
                "fps": 24.0, "seconds": 0.5, "size": [64, 64], "source_size": [256, 256], "tintable": False,
                "default_part": "loop" if "loop" in parts else parts[0], "parts": {}}
        for part in parts:
            d = root / name / part
            d.mkdir(parents=True)
            for i in range(12):
                a = np.zeros((64, 64, 4), np.uint8)
                yy, xx = np.mgrid[:64, :64]
                a[..., :3] = 255
                a[..., 3] = np.uint8(255 * np.clip(1 - np.hypot(xx - 32, yy - 32) / (8 + 2 * i), 0, 1))
                Image.fromarray(a, "RGBA").save(d / f"f_{i:04d}.webp", lossless=True)
            meta["parts"][part] = {"fps": 24.0, "seconds": 0.5, "frames": 12, "size": [64, 64]}
        (root / name / "meta.json").write_text(json.dumps(meta))
    return root


def test_catalog_covers_every_non_particle_template_that_needs_no_art():
    used = {e["template"] for e in F.CATALOG.values()}
    particles = {"burst", "sparkle", "metal_sparks", "splash"}          # fx_emitter presets ae_*
    needs_art = {"heat_shimmer", "relief_shimmer", "surface_sweep", "edge_aura", "saber"}
    path_parts = {"energy_payline"}                                     # ae_polyline_fx builds it per line
    assert used == set(ae_templates.list_templates()) - particles - needs_art - path_parts
    for e in F.CATALOG.values():                                        # variants only set real params
        assert set(e.get("params", {})) <= set(ae_templates.list_templates()[e["template"]]["params"])


def test_listing_and_missing_flipbooks_are_explained(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SPINE_FLIPBOOKS", str(tmp_path / "none"))
    rows = F.listing()
    assert set(rows) == set(F.CATALOG) and not any(r["downloaded"] for r in rows.values())
    with pytest.raises(FileNotFoundError, match="render_all"):
        F.meta("fire")
    with pytest.raises(ValueError, match="no flipbook"):
        F.meta("nope")


def test_drop_a_flipbook_on_a_skeleton_in_comp_units(proj, fake_books):
    from claude_spine.tools_flipbook import fx_flipbook
    out = fx_flipbook(str(proj.path), "glow_pulse", x=10, y=20, scale=1.0)
    assert "validation_errors" not in out and out["flipbook"]["mode"] == "alpha"
    p = Project.open(proj.path)
    att = p.data.attachment(out["slot"], "fx")
    assert att.sequence.count >= 1
    assert att.width == pytest.approx(256, rel=0.02)                   # 64 px stored, 256 px comp: comp units kept
    assert qa.validate(p.data)["ok"]


def test_parts_and_additive_blend(proj, fake_books):
    from claude_spine.tools_flipbook import fx_flipbook
    out = fx_flipbook(str(proj.path), "win_aura", part="in")
    assert out["flipbook"]["part"] == "in"
    p = Project.open(proj.path)
    assert p.data.slot(out["slot"]).blend == "additive"
    with pytest.raises(ValueError, match="parts"):
        fx_flipbook(str(proj.path), "win_aura", part="middle")
    assert "glow_pulse" in fx_flipbook()["flipbooks"]


def test_a_flipbook_as_a_particle_picture(proj, fake_books):
    res = E.bake(proj, preset="smoke_puffs", emitter={"texture": {"frames": "flipbook:glow_pulse", "cycles": 1}})
    att = proj.data.attachment(res["slots"][0], "fx")
    assert att.sequence.count == 12 and qa.validate(proj.data)["ok"]


def test_release_zips_round_trip_and_refuse_odd_paths(fake_books, tmp_path, monkeypatch):
    import io
    import zipfile
    zips = F.pack_release(str(tmp_path / "rel"), str(fake_books))
    assert sorted(p.split("/")[-1] for p in zips) == ["glow_pulse.zip", "win_aura.zip"]
    cache = tmp_path / "cache"
    monkeypatch.setattr(F, "data_dir", lambda: cache)

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    payload = {"u": (tmp_path / "rel" / "glow_pulse.zip").read_bytes()}
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: Resp(payload["u"]))
    F.fetch("glow_pulse")
    assert (cache / "glow_pulse" / "meta.json").exists() and len(F.frames("glow_pulse")) == 12
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.txt", "x")
    payload["u"] = bad.getvalue()
    with pytest.raises(ValueError, match="unexpected file"):
        F.fetch("fire")
