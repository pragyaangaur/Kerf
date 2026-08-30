"""Measurements taken from a mesh."""

import unittest

import numpy as np

from conftest import CUBE, part


class TestMeasurements(unittest.TestCase):
    def test_sphere_volume_and_area(self):
        mesh = part([{"id": "s", "type": "sphere", "radius": "r"}], {"r": 10}).evaluate(64)
        self.assertAlmostEqual(mesh.volume(), 4 / 3 * np.pi * 1000, delta=30)
        self.assertAlmostEqual(mesh.area(), 4 * np.pi * 100, delta=15)

    def test_boolean_subtract_volume(self):
        mesh = part([
            {"id": "b", "type": "box", "size": [20, 20, 20]},
            {"id": "h", "type": "cylinder", "op": "subtract", "radius": 5, "height": 40},
        ]).evaluate(64)
        self.assertAlmostEqual(mesh.volume(), 8000 - np.pi * 25 * 20, delta=25)

    def test_component_count(self):
        mesh = part([
            {"id": "a", "type": "sphere", "radius": 5, "center": [-20, 0, 0]},
            {"id": "b", "type": "sphere", "radius": 5, "center": [20, 0, 0]},
        ]).evaluate(48)
        self.assertEqual(mesh.stats()["components"], 2)

    def test_empty_mesh_reports_zeroes(self):
        from kerf.geometry import Mesh

        empty = Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))
        self.assertTrue(empty.empty())
        self.assertEqual(empty.volume(), 0.0)
        self.assertEqual(empty.area(), 0.0)
        self.assertEqual(empty.component_count(), 0)
        self.assertFalse(empty.is_watertight())


class TestTessellation(unittest.TestCase):
    def test_meshes_are_watertight_and_face_outward(self):
        mesh = part(CUBE).evaluate(40)
        self.assertTrue(mesh.is_watertight(), "surface nets must close the solid")
        self.assertEqual(mesh.outward_fraction(), 1.0, "a convex solid must face outward")

    def test_outward_winding_gives_positive_signed_volume(self):
        mesh = part(CUBE).evaluate(40)
        corners = mesh.triangles()
        signed = np.einsum(
            "ij,ij->i", corners[:, 0], np.cross(corners[:, 1], corners[:, 2])
        ).sum() / 6
        self.assertGreater(signed, 0)

    def test_a_bored_part_is_still_watertight(self):
        mesh = part([
            {"id": "b", "type": "box", "size": [20, 20, 20]},
            {"id": "h", "type": "cylinder", "op": "subtract", "radius": 5, "height": 40},
        ]).evaluate(56)
        self.assertTrue(mesh.is_watertight())
        # Faces inside the bore correctly point at the axis, so the outward
        # share is below one for any part with a hole through it.
        self.assertLess(mesh.outward_fraction(), 1.0)


if __name__ == "__main__":
    unittest.main()
