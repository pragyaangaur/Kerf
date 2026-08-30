"""Occupancy grids and the regions found in them."""

import unittest

import numpy as np

from conftest import CUBE, part
from kerf.geometry import common_grid, interior_seeds, label_regions, voxelize


class TestVoxelization(unittest.TestCase):
    def test_filled_volume_matches_the_solid(self):
        mesh = part(CUBE).evaluate(48)
        origin, pitch, dims = common_grid([mesh], 64)
        grid = voxelize(mesh, origin, pitch, dims)
        self.assertAlmostEqual(float(grid.sum()) * pitch ** 3, 8000, delta=8000 * 0.03)

    def test_a_bore_leaves_a_hole_in_the_grid(self):
        mesh = part([
            {"id": "b", "type": "box", "size": [20, 20, 20]},
            {"id": "h", "type": "cylinder", "op": "subtract", "radius": 6, "height": 40},
        ]).evaluate(56)
        origin, pitch, dims = common_grid([mesh], 56)
        grid = voxelize(mesh, origin, pitch, dims)
        centre = tuple(int(i / 2) for i in dims)
        self.assertFalse(grid[centre], "the middle of a through bore must be empty")

    def test_grid_covers_every_mesh(self):
        small = part([{"id": "s", "type": "sphere", "radius": 4}]).evaluate(24)
        large = part([{"id": "s", "type": "sphere", "radius": 12}]).evaluate(24)
        origin, pitch, dims = common_grid([small, large], 32)
        high = origin + np.asarray(dims) * pitch
        self.assertTrue(np.all(origin <= large.bbox()[0]))
        self.assertTrue(np.all(high >= large.bbox()[1]))


class TestRegions(unittest.TestCase):
    def test_separate_blobs_get_separate_labels(self):
        grid = np.zeros((10, 10, 10), dtype=bool)
        grid[1:4, 1:4, 1:4] = True
        grid[6:9, 6:9, 6:9] = True
        _, count = label_regions(grid)
        self.assertEqual(count, 2)

    def test_touching_blobs_become_one_region(self):
        grid = np.zeros((10, 10, 10), dtype=bool)
        grid[1:5, 1:4, 1:4] = True
        grid[4:8, 1:4, 1:4] = True
        _, count = label_regions(grid)
        self.assertEqual(count, 1)

    def test_an_empty_grid_has_no_regions(self):
        _, count = label_regions(np.zeros((5, 5, 5), dtype=bool))
        self.assertEqual(count, 0)


class TestSeeds(unittest.TestCase):
    def test_a_one_cell_shell_has_no_seed(self):
        shell = np.zeros((8, 8, 8), dtype=bool)
        shell[3, :, :] = True
        self.assertFalse(interior_seeds(shell).any())

    def test_a_thick_blob_has_a_seed(self):
        blob = np.zeros((8, 8, 8), dtype=bool)
        blob[2:6, 2:6, 2:6] = True
        self.assertTrue(interior_seeds(blob).any())


if __name__ == "__main__":
    unittest.main()
