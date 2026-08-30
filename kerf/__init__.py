"""Kerf: version control that understands geometry.

Git tracks bytes. A CAD file is bytes that mean something, and the gap
between those two facts breaks every part of the workflow. Re-exporting an
untouched part looks like a rewrite of the whole file. A two millimetre
parameter edit that removes a boss looks the same as any other edit. Two
people editing one solid cannot be reconciled by a line based merge at all.

Kerf closes that gap by working on the shape instead of the file.
"""

__version__ = "0.1.0"

from .geometry import Mesh, geometry_hash
from .model import Model, load, load_file
from .parametric import Feature, Part
from .repo import Repo, RepoError

__all__ = [
    "Feature",
    "Mesh",
    "Model",
    "Part",
    "Repo",
    "RepoError",
    "__version__",
    "geometry_hash",
    "load",
    "load_file",
]
