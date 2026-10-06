---
name: clip-breakdown
description: Watch a video clip the user sends (a slot game, a game UI, a trailer, a motion reference) and break its animation down like a lead animator would - a timed beat sheet of every event, what moves and how (properties, timing in frames, easing, anticipation / overshoot / settle, loops), layering and blend modes, cause-and-effect chains, measured positions and sizes, and which tool each part needs (Spine natively, an After Effects flipbook, or new art). Use whenever the user attaches or points to an .mp4 / .mov / .gif and asks to observe it, break it down, analyse the animation, list the effects, time it, or asks "how is this done" or "is this possible". Read-only on the clip; it produces a breakdown, it does not build the effects (for that, follow with the clip-to-spine skill).
---

# Clip breakdown

Turn a clip into a breakdown an animator could rebuild from: every event on a timeline, how each one moves, and how it
was most likely made. Look before you describe, and measure before you state a number.

## Tools

`scripts/cliptools.py` (this skill's folder) does all the looking. macOS, no ffmpeg needed (it compiles a small
AVFoundation frame grabber on first use). Run it with Pillow and numpy:

```bash
~/.local/bin/uv run -q --with pillow --with numpy python ~/.claude/skills/clip-breakdown/scripts/cliptools.py <command> ...
```

In zsh, never keep that command in a variable (`$U ...` is not word-split); define a function:
`ct() { ~/.local/bin/uv run -q --with pillow --with numpy python ~/.claude/skills/clip-breakdown/scripts/cliptools.py "$@"; }`

| Command | Use it for |
|---|---|
| `info VIDEO` | duration, size, fps |
| `motion VIDEO OUT.png --fps 12` | FIRST look: change + brightness curves, peaks with thumbnails. Prints `change_peaks` (hits, pops, motion bursts), `flash_peaks`, `cuts` (scene changes), `holds` (still stretches) |
| `sheet VIDEO DIR --n 24 [--start --end --crop]` | contact sheets, 8 frames each, every frame labelled with its time |
| `strip VIDEO OUT.png --start --end --n 12 [--crop]` | consecutive frames at full detail: count frames, see timing, read a fast event |
| `onion VIDEO OUT.png --start --end --n 8 [--crop]` | spacing chart: moving parts tinted blue (early) to red (late) over the still background. Even gaps = linear, gaps shrinking = ease out, growing = ease in, red past the end then back = overshoot. Useless across a full-screen flash: use `strip` there |
| `grid VIDEO OUT.png --t T --units W` | one frame with a pixel grid; with `--units` also the px -> skeleton-unit formula (origin centre, y up) |

`--crop x0,y0,x1,y1` is in FRACTIONS of the frame. Write everything to a work folder (the scratchpad, or next to the
breakdown the user wants), and Read the PNG/JPGs to see them.

## Method (in this order)

1. **Get the shape of the clip.** `info`, then `motion` over the whole clip. The peaks are your candidate beats;
   `holds` are where nothing happens (idle loops, waiting for input); `cuts` split it into scenes. Read the chart.
2. **See all of it.** `sheet` with ~1 frame per 0.6 s (24 for a 15 s clip, more for longer). Name each scene/phase.
3. **Zoom on every beat.** For each peak: `sheet` or `strip` over beat +- 0.5 s, cropped to where it happens. Most
   effects live 0.2-1 s: sample them densely (8-12 frames across the event), never only 1 frame.
4. **Read the motion.** For anything that moves, an `onion` over its move (or a `strip` at full rate): direction,
   spacing (easing), anticipation before, overshoot / settle after, squash and stretch, secondary motion, follow-through.
   Count frames at the clip's fps (`info`): durations go in seconds AND frames.
5. **Measure.** `grid` on a clean frame (no flash, no transition): positions of reels / cells / anchors in px, sizes,
   and in skeleton units if a rebuild is planned. Check the layout (rows x columns) on the grid, not by eye.
6. **Separate the layers.** For every event: what is ART (characters, symbols, UI, text: rigged or drawn, not an
   effect) and what is FX (light, particles, smoke, fire, lightning, trails, screen shake, flashes). Respect what the
   user says to ignore (e.g. "ignore the character animation").
7. **Infer the build** (say "likely" when it is an inference): additive glow (brightens, never darkens: light on dark),
   normal blend (covers: smoke, confetti, coins), flipbook (organic, never repeats a shape within a cycle: fire, smoke,
   lightning, liquid), procedural transform (a sprite scaled / rotated / faded: rings, flares, rays, pops), mesh
   deformation (bending ribbons, cloth), particles (many similar pieces on curves), screen-space (shake, flash, dim,
   colour grade).
8. **Classify the tool for a rebuild:**
   - Spine natively (cheap, recolourable, resizable): glows, rings, rays, flashes, hit bursts, streaks, sweeps, pops,
     squash, coins / confetti on curves, speed lines, shake, dims, number punch-ins.
   - After Effects flipbook into Spine (organic noise): lightning, fire, auras, smoke, explosions, liquids, energy swirls.
   - Art needed: anything drawn (characters, symbols, titles, painted backgrounds, hand-drawn FX frames).
   With the claude-spine MCP available, name the closest existing `fx_recipe` / `ae_template` for each part
   (list them with `fx_recipe` recipe="" and `ae_template` name=""); say which parts have no recipe yet.

## Deliverable

Write `breakdown.md` in the work folder (and give the path), then summarise in chat. Structure:

1. **Clip facts**: length, fps, size, scenes with time ranges.
2. **Beat sheet**: a table, one row per event, in time order:
   `time (s) | frames | event | what moves / changes | easing & timing notes | layer & blend | likely build | rebuild with`.
   Group sub-events under their beat (e.g. 9.43 scatter win: aura on -> bolt 0.08 s later -> flash -> number count).
3. **Cause and effect**: chains like "reel 4 stops -> scatter lands (squash 2 f) -> flash -> crackle loop starts".
4. **Loops**: what loops, period, and whether it is a seamless loop or a restart.
5. **Measurements**: layout grid (px and units), sizes of key elements, colours (hex) of the main glows.
6. **Reusable patterns**: what repeats (e.g. every win = same punch-in curve) - these become one recipe.
7. **Rebuild plan and caveats**: per effect: Spine / AE / art, effort (easy / medium / hard), and the caveats
   (flipbook repeats, memory per atlas page, fixed bolt shapes, additive light washing out on bright backgrounds).

Attach the motion chart and the most telling sheets/strips with the user-visible file tool when available.

## Rules

- Never describe from one frame. Effects are 0.2-1 s long; sample them densely before saying what they do.
- Numbers come from measurement (timestamps from file names, frame counts from fps, positions from the grid).
  If something is a guess, say so.
- Name motion in animator terms: anticipation, overshoot, settle, ease in / out, hold, smear, squash and stretch,
  follow-through, overlapping action, stagger.
- Pick clean frames for measuring (no flash, no transition, no motion blur): a transition frame lies about layout.
- Keep the user's scope: if they said effects only, characters are listed only as "art, not covered".
- Do not reproduce copyrighted art; describe it.
