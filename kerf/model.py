"""One CAD model, whatever form it arrived in.

Kerf reads two kinds of file. A mesh has geometry and no history, and a part
file has both. A third kind is recognised and versioned without being
understood, because a SolidWorks part is still worth tracking and locking even
when nothing can be said about what is inside it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .formats import obj as obj_format
from .formats import stl as stl_format
from .geometry import Mesh, geometry_hash
from .parametric import Part

MESH_EXTENSIONS = {".stl", ".obj"}
PART_EXTENSIONS = {".kpart", ".kp.json"}
CAD_EXTENSIONS = MESH_EXTENSIONS | PART_EXTENSIONS

# Formats kerf recognises as CAD and cannot open. These are still versioned
# and still guarded by locks. Kerf just cannot say what changed inside them.
OPAQUE_EXTENSIONS = {
    ".sldprt": "SolidWorks part", ".sldasm": "SolidWorks assembly",
    ".step": "STEP", ".stp": "STEP", ".iges": "IGES", ".igs": "IGES",
    ".f3d": "Fusion 360", ".ipt": "Inventor part", ".iam": "Inventor assembly",
    ".catpart": "CATIA part", ".prt": "NX or Creo part", ".3dm": "Rhino",
    ".dwg": "AutoCAD drawing", ".dxf": "DXF", ".scad": "OpenSCAD",
    ".blend": "Blender", ".3mf": "3MF", ".glb": "glTF binary",
}


def extension(path: str) -> str:
    lower = path.lower()
    for compound in (".kp.json",):
        if lower.endswith(compound):
            return compound
    return os.path.splitext(lower)[1]


def classify(path: str) -> str:
    suffix = extension(path)
    if suffix in PART_EXTENSIONS:
        return "parametric"
    if suffix in MESH_EXTENSIONS:
        return "mesh"
    if suffix in OPAQUE_EXTENSIONS:
        return "opaque"
    return "file"


def format_name(path: str) -> str:
    """The name a person would use for this file type."""
    suffix = extension(path)
    if suffix in OPAQUE_EXTENSIONS:
        return OPAQUE_EXTENSIONS[suffix]
    known = {".stl": "STL", ".obj": "OBJ", ".kpart": "Kerf part", ".kp.json": "Kerf part"}
    return known.get(suffix, suffix.lstrip(".").upper() or "file")


@dataclass
class Model:
    path: str
    kind: str                      # mesh, parametric, opaque, or file
    data: bytes
    mesh: Optional[Mesh] = None
    part: Optional[Part] = None
    error: str = ""

    @property
    def is_cad(self) -> bool:
        return self.mesh is not None or self.part is not None

    def geometry_id(self) -> str:
        """The id of the shape.

        A part file hashes the geometry it evaluates to, so a part and an STL
        export of the same solid compare equal.
        """
        if self.mesh is not None and not self.mesh.empty():
            return geometry_hash(self.mesh)
        return ""

    def stats(self) -> dict:
        if self.mesh is None:
            return {}
        stats = self.mesh.stats()
        if self.part is not None:
            stats["features"] = len(self.part.features)
            stats["active_features"] = len(self.part.active_features())
            stats["parameters"] = len(self.part.parameters)
        return stats


def load(path: str, data: bytes, resolution: int = 56) -> Model:
    """Parse bytes into a model.

    This never raises. A file that fails to parse records the reason and stays
    trackable, because a broken part still needs to be committed and inspected.
    """
    kind = classify(path)
    model = Model(path=path, kind=kind, data=data)
    try:
        if kind == "parametric":
            model.part = Part.loads(data)
            model.mesh = model.part.evaluate(resolution)
        elif kind == "mesh":
            reader = stl_format if extension(path) == ".stl" else obj_format
            model.mesh = reader.load(data)
    except Exception as error:                       # noqa: BLE001
        model.error = f"{type(error).__name__}: {error}"
        model.mesh = None
        model.part = None
    return model


def load_file(path: str, resolution: int = 56) -> Model:
    with open(path, "rb") as handle:
        return load(path, handle.read(), resolution)
