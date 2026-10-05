"""A working project on disk: ``<name>.json`` (Spine 4.2 skeleton) next to an
``images/`` folder of part PNGs. Every MCP tool opens one of these, edits the
skeleton through the IR and saves it back.

``skeleton.images`` is always written as ``./images/`` (relative). An absolute
path there makes the project open only on the machine that wrote it: the Spine
editor stores it and a "fresh unzip" test passes as long as the old folder
still exists, so the bug hides until someone else opens the file.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from .ir import SkeletonData


class Project:
    def __init__(self, json_path: str | Path, data: SkeletonData | None = None):
        self.path = Path(json_path).expanduser().resolve()
        self.data = data if data is not None else SkeletonData.load(self.path)
        self._cache: dict[str, Image.Image] = {}

    @classmethod
    def open(cls, json_path: str | Path) -> "Project":
        return cls(json_path)

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def images_dir(self) -> Path:
        rel = self.data.skeleton.images or "./images/"
        p = Path(rel)
        return p if p.is_absolute() else (self.root / p).resolve()

    def save(self) -> Path:
        if not self.data.skeleton.images or Path(self.data.skeleton.images).is_absolute():
            try:
                rel = self.images_dir.relative_to(self.root)
                self.data.skeleton.images = f"./{rel.as_posix()}/"
            except ValueError:
                self.data.skeleton.images = "./images/"
        return self.data.save(self.path)

    def image_path(self, att_path: str) -> Path:
        for ext in (".png", ".webp", ".jpg"):
            p = self.images_dir / f"{att_path}{ext}"
            if p.exists():
                return p
        raise FileNotFoundError(f"image for {att_path!r} not found under {self.images_dir}")

    def image(self, att_path: str) -> Image.Image:
        if att_path not in self._cache:
            self._cache[att_path] = Image.open(self.image_path(att_path)).convert("RGBA")
        return self._cache[att_path]

    def write_image(self, att_path: str, im: Image.Image) -> Path:
        p = self.images_dir / f"{att_path}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p)
        self._cache[att_path] = im
        return p

    def att_image_name(self, slot: str, att_name: str) -> str:
        att = self.data.attachment(slot, att_name)
        path = getattr(att, "path", None) or att_name
        seq = getattr(att, "sequence", None)
        if seq is not None:
            path = f"{path}{str(seq.start + seq.setup).zfill(seq.digits)}"
        return path
