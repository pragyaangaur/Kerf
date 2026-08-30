"""Deciding whether two meshes are the same solid."""

import unittest

import numpy as np

from conftest import CUBE, part
from kerf.geometry import Mesh, equivalent, geometry_hash


class TestGeometryHash(unittest.TestCase):
    def setUp(self):
        self.mesh = part(CUBE).evaluate(32)

    def test_hash_is_stable(self):
        self.assertEqual(geometry_hash(self.mesh), geometry_hash(self.mesh))

    def test_hash_ignores_triangle_order(self):
        order = np.random.default_rng(0).permutation(len(self.mesh.faces))
        shuffled = Mesh(self.mesh.vertices.copy(), self.mesh.faces[order])
        self.assertEqual(geometry_hash(self.mesh), geometry_hash(shuffled))

    def test_hash_ignores_vertex_renumbering(self):
        order = np.random.default_rng(1).permutation(len(self.mesh.vertices))
        remap = np.empty_like(order)
        remap[order] = np.arange(len(order))
        renumbered = Mesh(self.mesh.vertices[order], remap[self.mesh.faces])
        self.assertEqual(geometry_hash(self.mesh), geometry_hash(renumbered))

    def test_hash_changes_when_the_shape_changes(self):
        moved = Mesh(self.mesh.vertices + np.array([0.0, 0.0, 1.0]), self.mesh.faces)
        self.assertNotEqual(geometry_hash(self.mesh), geometry_hash(moved))

    def test_empty_meshes_share_one_hash(self):
        empty = Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))
        self.assertEqual(geometry_hash(empty), geometry_hash(empty))


class TestTolerance(unittest.TestCase):
    def setUp(self):
        self.mesh = part(CUBE).evaluate(32)
        low, high = self.mesh.bbox()
        self.diagonal = float(np.linalg.norm(high - low))

    def test_float_noise_is_seen_through(self):
        rng = np.random.default_rng(3)
        noise = (rng.random(self.mesh.vertices.shape) - 0.5) * self.diagonal * 1e-7
        noisy = Mesh(self.mesh.vertices + noise, self.mesh.faces.copy())
        same, deviation = equivalent(self.mesh, noisy)
        self.assertTrue(same)
        self.assertLess(deviation, self.diagonal * 1e-5)

    def test_a_real_edit_is_not_seen_through(self):
        shifted = Mesh(self.mesh.vertices + np.array([0.0, 0.0, 0.4]), self.mesh.faces)
        self.assertFalse(equivalent(self.mesh, shifted)[0])

    def test_a_different_triangle_count_cannot_correspond(self):
        other = part(CUBE).evaluate(48)
        same, deviation = equivalent(self.mesh, other)
        self.assertFalse(same)
        self.assertEqual(deviation, float("inf"))

    def test_pairing_survives_coincident_coordinates(self):
        # Lattice built geometry repeats coordinates constantly, and this is
        # the case where pairing vertices by sort order falls apart.
        rng = np.random.default_rng(9)
        noise = (rng.random(self.mesh.vertices.shape) - 0.5) * self.diagonal * 2e-6
        order = rng.permutation(len(self.mesh.faces))
        noisy = Mesh(self.mesh.vertices + noise, self.mesh.faces[order])
        self.assertTrue(equivalent(noisy, self.mesh)[0])


if __name__ == "__main__":
    unittest.main()
