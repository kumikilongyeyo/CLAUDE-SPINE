# Changelog

## Unreleased

- `ae_fx_to_spine` (25th tool): After Effects → Spine bridge. Renders a saved `.aep` comp headless with `aerender` (never touches the project open in AE), reads AE's premultiplied TIFF alpha, trims empty frames, writes straight-alpha sprites to `images/ae/` and plays them as a Spine sequence at the comp's own speed. `hit_ae` + `hit_at` land an AE moment on a Spine one; `fit_duration` stretches a sequence to a loop length; `max_frames`/`max_size` shrink it. Frames already on disk work too (`frames_dir` + `fps`). Reproduces the coin project's hand-made fire flipbook byte for byte. 11 new tests.

## 0.1.0 — 2026-10-05

First release of the restructured fork of egorfedorov/spine-mcp.

- Typed Spine 4.2 IR (Pydantic) with exact runtime defaults and pass-through of unknown fields; bone-index remapping for weighted vertices.
- Contour meshes: padded trace → DP simplify (never clips art) → joint-aware refinement → verified conforming Delaunay with an exact CDT fallback.
- Bone-heat weights (cotangent Laplacian, visibility-aware heat), ≤4 influences, exact normalisation.
- IK, Spine 4.2 physics presets, transform constraints, one-call strand rigs, 2.5D turn rig.
- Symbol animation contract + juice presets on inserted juice bones; FX presets with procedural textures; Spine events for SFX/particles/rollups.
- QA: structural validation, spine-core runtime load + playback check, mobile budget with draw-call estimate, runtime-driven GIF previews.
- MaxRects atlas packer (whitespace strip, PMA, sequence-safe region names).
- 24 MCP tools; 369 tests including mesh fuzzing and a Spine editor round-trip.
