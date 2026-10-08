// Load a skeleton in the official spine-core 4.2 runtime and dump posed geometry.
//
// Python owns the format; this script is the second opinion. If the runtime
// cannot read a skeleton, no amount of Python-side validation matters, so every
// QA pass ends here. It also gives the previews real constraint solving (IK,
// transform, physics, clipping) without reimplementing the runtime.
//
// usage: node pose.mjs <skeleton.json> <file.atlas> [--anim a,b] [--fps 30]
//                      [--frames N] [--geometry] [--out dump.json]
//
// Without --geometry it only loads, applies every animation at every frame and
// reports problems (NaN vertices, unknown regions, events fired, bounds).
import fs from "node:fs";
import * as spine from "@esotericsoftware/spine-core";

const args = process.argv.slice(2);
const opt = (k, d) => {
  const i = args.indexOf(k);
  return i >= 0 ? args[i + 1] : d;
};
const flag = (k) => args.includes(k);
const VALUED = new Set(["--anim", "--fps", "--frames", "--out"]);
const positional = args.filter((a, i) => !a.startsWith("--") && !VALUED.has(args[i - 1]));
const [jsonPath, atlasPath] = positional;

class FakeTexture extends spine.Texture {
  constructor() { super({ width: 1, height: 1 }); }
  setFilters() {}
  setWraps() {}
  dispose() {}
}

function out(obj) {
  const s = JSON.stringify(obj);
  const o = opt("--out", null);
  if (o) fs.writeFileSync(o, s);
  else process.stdout.write(s);
}

let skeletonData, atlas;
try {
  atlas = new spine.TextureAtlas(fs.readFileSync(atlasPath, "utf8"));
  for (const p of atlas.pages) p.setTexture(new FakeTexture());
  const loader = new spine.AtlasAttachmentLoader(atlas);
  const reader = new spine.SkeletonJson(loader);
  skeletonData = reader.readSkeletonData(JSON.parse(fs.readFileSync(jsonPath, "utf8")));
} catch (e) {
  out({ ok: false, stage: "load", error: String(e && e.message ? e.message : e) });
  process.exit(0);
}

const fps = Number(opt("--fps", "30"));
const maxFrames = Number(opt("--frames", "0"));
const geometry = flag("--geometry");
const wanted = opt("--anim", null);
const anims = skeletonData.animations.filter((a) => !wanted || wanted.split(",").includes(a.name));

const skeleton = new spine.Skeleton(skeletonData);
const clipper = new spine.SkeletonClipping();
const QUAD = [0, 1, 2, 2, 3, 0];
const problems = [];
const pageSizes = Object.fromEntries(atlas.pages.map((p) => [p.name, [p.width, p.height]]));

function frameDraws(t, animName) {
  const draws = [];
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const verts = [];
  for (const slot of skeleton.drawOrder) {
    const att = slot.getAttachment();
    if (!slot.bone.active) { clipper.clipEndWithSlot(slot); continue; }
    if (!att) { clipper.clipEndWithSlot(slot); continue; }
    if (att instanceof spine.ClippingAttachment) {
      clipper.clipStart(slot, att);
      continue;
    }
    let v, uvs, tris, color, region;
    if (att instanceof spine.RegionAttachment) {
      v = new Array(8);
      att.computeWorldVertices(slot, v, 0, 2);
      uvs = Array.from(att.uvs);
      tris = QUAD;
      region = att.region;
      color = att.color;
    } else if (att instanceof spine.MeshAttachment) {
      v = new Array(att.worldVerticesLength);
      att.computeWorldVertices(slot, 0, att.worldVerticesLength, v, 0, 2);
      uvs = Array.from(att.uvs);
      tris = Array.from(att.triangles);
      region = att.region;
      color = att.color;
    } else {
      clipper.clipEndWithSlot(slot);
      continue;
    }
    for (let i = 0; i < v.length; i++) {
      if (!Number.isFinite(v[i])) {
        problems.push({ animation: animName, time: t, slot: slot.data.name, problem: "non-finite vertex" });
        break;
      }
    }
    if (clipper.isClipping()) {
      clipper.clipTrianglesUnpacked(v, tris, tris.length, uvs);
      v = Array.from(clipper.clippedVertices);
      uvs = Array.from(clipper.clippedUVs);
      tris = Array.from(clipper.clippedTriangles);
    }
    for (let i = 0; i < v.length; i += 2) {
      if (v[i] < minX) minX = v[i];
      if (v[i] > maxX) maxX = v[i];
      if (v[i + 1] < minY) minY = v[i + 1];
      if (v[i + 1] > maxY) maxY = v[i + 1];
    }
    const sc = skeleton.color, slc = slot.color;
    const a = sc.a * slc.a * color.a;
    if (geometry && tris.length && a > 0.001) {
      draws.push({
        slot: slot.data.name,
        page: region && region.page ? region.page.name : null,
        region: region && region.name ? region.name : null,
        blend: ["normal", "additive", "multiply", "screen"][slot.data.blendMode],
        color: [sc.r * slc.r * color.r, sc.g * slc.g * color.g, sc.b * slc.b * color.b, a],
        ...(slot.darkColor ? { dark: [slot.darkColor.r, slot.darkColor.g, slot.darkColor.b] } : {}),
        v: v.map((x) => Math.round(x * 100) / 100),
        uv: uvs.map((x) => Math.round(x * 1e5) / 1e5),
        tri: tris,
      });
    }
    verts.push(v.length / 2);
    clipper.clipEndWithSlot(slot);
  }
  clipper.clipEnd();
  return { draws, bounds: [minX, minY, maxX, maxY], vertices: verts.reduce((a, b) => a + b, 0) };
}

const result = {
  ok: true,
  runtime: "spine-core " + (spine.Skeleton.yDown !== undefined ? "4.2" : "?"),
  bones: skeletonData.bones.length,
  slots: skeletonData.slots.length,
  pages: pageSizes,
  setup: null,
  animations: {},
  problems,
};

skeleton.setToSetupPose();
skeleton.updateWorldTransform(spine.Physics.reset);
const setup = frameDraws(0, "<setup>");
result.setup = geometry ? setup : { bounds: setup.bounds, vertices: setup.vertices };

for (const anim of anims) {
  skeleton.setToSetupPose();
  skeleton.updateWorldTransform(spine.Physics.reset);
  const dur = anim.duration;
  let n = Math.max(1, Math.round(dur * fps) + 1);
  if (maxFrames > 0) n = Math.min(n, maxFrames);
  const step = n > 1 ? dur / (n - 1) : 0;
  const frames = [];
  const events = [];
  let last = -1;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, maxVerts = 0;
  for (let i = 0; i < n; i++) {
    const t = i * step;
    const fired = [];
    skeleton.setToSetupPose();
    anim.apply(skeleton, last, t, false, fired, 1, spine.MixBlend.setup, spine.MixDirection.mixIn);
    skeleton.update(i === 0 ? 0 : step);
    skeleton.updateWorldTransform(i === 0 ? spine.Physics.reset : spine.Physics.update);
    for (const e of fired) events.push({ time: Math.round(t * 1000) / 1000, name: e.data.name, at: e.time });
    last = t;
    const f = frameDraws(t, anim.name);
    minX = Math.min(minX, f.bounds[0]); minY = Math.min(minY, f.bounds[1]);
    maxX = Math.max(maxX, f.bounds[2]); maxY = Math.max(maxY, f.bounds[3]);
    maxVerts = Math.max(maxVerts, f.vertices);
    if (geometry) frames.push({ t: Math.round(t * 10000) / 10000, draws: f.draws, bounds: f.bounds });
  }
  result.animations[anim.name] = {
    duration: dur, frames: geometry ? frames : n, events,
    bounds: [minX, minY, maxX, maxY], maxVertices: maxVerts,
  };
}
if (problems.length) result.ok = false;
out(result);
