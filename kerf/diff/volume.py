"""Measuring where material appeared and disappeared.

Both revisions are filled onto one shared lattice and subtracted. This works
for any mesh, including an export from a CAD system kerf cannot open, which
is the reason it exists alongside the feature tree comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..geometry import Mesh, common_grid, interior_seeds, label_regions, voxelize


@dataclass
class Region:
    """One connected lump of material that only one revision has."""

    kind: str                # added or removed
    volume: float
    centroid: list[float]
    bbox_min: list[float]
    bbox_max: list[float]
    cells: int


@dataclass
class VolumeDiff:
    resolution: int
    pitch: float
    cell_volume: float
    volume_old: float
    volume_new: float
    added_volume: float = 0.0
    removed_volume: float = 0.0
    common_volume: float = 0.0
    regions: list[Region] = field(default_factory=list)
    translation: Optional[list[float]] = None
    unchanged: bool = False
    noise_volume: float = 0.0
    noise_cells: int = 0

    @property
    def net(self) -> float:
        return self.added_volume - self.removed_volume

    @property
    def changed_fraction(self) -> float:
        base = max(self.volume_old, self.volume_new, 1e-12)
        return (self.added_volume + self.removed_volume) / base


def diff_volumes(
    old: Mesh, new: Mesh, resolution: int = 56, max_regions: int = 8
) -> VolumeDiff:
    """Subtract two solids and describe what is left over."""
    origin, pitch, dims = common_grid([old, new], resolution)
    cell = pitch ** 3
    grid_old = voxelize(old, origin, pitch, dims)
    grid_new = voxelize(new, origin, pitch, dims)

    added = grid_new & ~grid_old
    removed = grid_old & ~grid_new
    shared = grid_old & grid_new

    result = VolumeDiff(
        resolution=resolution,
        pitch=pitch,
        cell_volume=cell,
        volume_old=float(grid_old.sum()) * cell,
        volume_new=float(grid_new.sum()) * cell,
        common_volume=float(shared.sum()) * cell,
    )

    real = {"added": 0.0, "removed": 0.0}
    for kind, grid in (("added", added), ("removed", removed)):
        if not grid.any():
            continue
        seeds = interior_seeds(grid)
        labels, count = label_regions(grid)
        seeded = set(np.unique(labels[seeds]).tolist()) - {0}

        # The cells are sorted by region once, rather than scanning the whole
        # lattice again for every region. Re-tessellation can leave hundreds
        # of one cell regions behind, and that scan was the cost of the diff.
        occupied = np.argwhere(labels)
        order = np.argsort(labels[tuple(occupied.T)], kind="stable")
        occupied = occupied[order]
        starts = np.searchsorted(labels[tuple(occupied.T)], np.arange(1, count + 2))

        for label in range(1, count + 1):
            cells = occupied[starts[label - 1]:starts[label]]
            if not len(cells):
                continue
            volume = len(cells) * cell
            if label not in seeded:
                # Nowhere thicker than one lattice cell. This is what
                # re-tessellation and float noise look like, so it is
                # measured separately and left out of the reported change.
                result.noise_volume += volume
                result.noise_cells += len(cells)
                continue
            real[kind] += volume
            centre = origin + (cells.mean(axis=0) + 0.5) * pitch
            low = origin + cells.min(axis=0) * pitch
            high = origin + (cells.max(axis=0) + 1) * pitch
            result.regions.append(
                Region(kind, volume, centre.tolist(), low.tolist(), high.tolist(), len(cells))
            )

    result.added_volume = real["added"]
    result.removed_volume = real["removed"]
    result.unchanged = not result.regions
    result.regions.sort(key=lambda region: -region.volume)
    result.regions = result.regions[:max_regions]

    # A body that only moved shows a matched pair of added and removed volume
    # with the same total, so report it as a move instead of as a reshape.
    if (
        result.added_volume > 0
        and result.removed_volume > 0
        and abs(result.added_volume - result.removed_volume) / max(result.added_volume, 1e-12) < 0.05
        and abs(result.volume_new - result.volume_old) / max(result.volume_old, 1e-12) < 0.02
    ):
        shift = np.asarray(new.centroid()) - np.asarray(old.centroid())
        if np.linalg.norm(shift) > pitch:
            result.translation = shift.tolist()
    return result
