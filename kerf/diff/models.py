"""Comparing one file across two revisions.

The comparison runs in stages, cheapest first. The geometry id answers most
cases on its own, because a re-export is the most common thing that happens
to a CAD file and the least interesting. Only when the shapes really differ
does kerf pay for the feature comparison and the voxel pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..geometry import equivalent
from ..model import Model
from .parts import ParametricDiff, diff_parts
from .summary import human_volume, summarize
from .volume import VolumeDiff, diff_volumes

METRIC_KEYS = ["volume", "area", "triangles", "components"]


@dataclass
class MetricChange:
    key: str
    old: float
    new: float

    @property
    def delta(self) -> float:
        return self.new - self.old

    @property
    def pct(self) -> Optional[float]:
        return None if not self.old else (self.new - self.old) / abs(self.old) * 100.0


@dataclass
class ModelDiff:
    path: str
    status: str            # added, removed, modified, reexported, rewritten, unchanged, renamed
    kind: str = "file"
    old_stats: dict = field(default_factory=dict)
    new_stats: dict = field(default_factory=dict)
    metrics: list[MetricChange] = field(default_factory=list)
    parametric: Optional[ParametricDiff] = None
    volume: Optional[VolumeDiff] = None
    old_path: str = ""
    note: str = ""
    size_old: int = 0
    size_new: int = 0

    def headline(self) -> str:
        return summarize(self)


def diff_models(
    path: str,
    old: Optional[Model],
    new: Optional[Model],
    resolution: int = 56,
    volumetric: bool = True,
) -> ModelDiff:
    """Compare one file. Either side may be None for an add or a delete."""
    if old is None and new is None:
        raise ValueError("nothing to diff")
    if old is None:
        return ModelDiff(path, "added", new.kind, {}, new.stats(), size_new=len(new.data))
    if new is None:
        return ModelDiff(path, "removed", old.kind, old.stats(), {}, size_old=len(old.data))

    result = ModelDiff(
        path, "modified", new.kind, old.stats(), new.stats(),
        size_old=len(old.data), size_new=len(new.data),
    )

    if old.data == new.data:
        result.status = "unchanged"
        return result

    old_gid, new_gid = old.geometry_id(), new.geometry_id()
    if old_gid and old_gid == new_gid:
        if old.part is not None and new.part is not None:
            result.status = "rewritten"
            result.note = "the feature tree changed but the resulting solid is identical"
        else:
            result.status = "reexported"
            result.note = "byte level change only, the solid is identical"
    elif old.mesh is not None and new.mesh is not None and old.part is None and new.part is None:
        same, deviation = equivalent(old.mesh, new.mesh)
        if same:
            result.status = "reexported"
            scale = max(
                float(np.linalg.norm(np.asarray(result.new_stats.get("size", [1, 1, 1])))), 1e-9
            )
            result.note = (
                f"the exporter moved every vertex by at most {deviation:.2g} mm "
                f"({deviation / scale * 1e6:.0f} ppm of the part), so there is no design change"
            )

    for key in METRIC_KEYS:
        if key in result.old_stats and key in result.new_stats:
            before, after = result.old_stats[key], result.new_stats[key]
            if isinstance(before, (int, float)) and before != after:
                result.metrics.append(MetricChange(key, float(before), float(after)))

    if old.part is not None and new.part is not None:
        result.parametric = diff_parts(old.part, new.part)

    skip_volume = result.status in ("reexported", "rewritten")
    if volumetric and not skip_volume and old.mesh is not None and new.mesh is not None:
        if not (old.mesh.empty() and new.mesh.empty()):
            result.volume = diff_volumes(old.mesh, new.mesh, resolution)
            volume = result.volume
            tree_changed = result.parametric is not None and not result.parametric.empty()
            if volume.unchanged and result.status == "modified" and not tree_changed:
                detail = ""
                if volume.noise_cells:
                    detail = (
                        f" ({volume.noise_cells} boundary cells differ, "
                        f"{human_volume(volume.noise_volume)}, all thinner than one "
                        f"{volume.pitch:.3g} mm cell)"
                    )
                result.note = result.note or ("no change above the measurement resolution" + detail)
    return result
