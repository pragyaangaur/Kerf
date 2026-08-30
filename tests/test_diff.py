"""Comparing two revisions of a model."""

import unittest

import numpy as np

from conftest import CUBE, part
from kerf import diff as diff_module
from kerf import model as model_module
from kerf.formats import stl as stl_format
from kerf.geometry import Mesh
from kerf.parametric import Part


class TestDiff(unittest.TestCase):
    def _models(self, a: Part, b: Part):
        return (model_module.load("a.kpart", a.dumps()), model_module.load("a.kpart", b.dumps()))

    def test_parameter_change_is_named_with_its_impact(self):
        a = part([{"id": "h", "type": "cylinder", "radius": "d/2", "height": 10}], {"d": 8})
        b = part([{"id": "h", "type": "cylinder", "radius": "d/2", "height": 10}], {"d": 10})
        d = diff_module.diff_parts(a, b)
        self.assertEqual(len(d.parameters), 1)
        self.assertEqual(d.parameters[0].key, "d")
        self.assertAlmostEqual(d.parameters[0].pct, 25.0)
        self.assertIn("d", d.impact)

    def test_added_and_removed_features(self):
        a = part(CUBE)
        b = part(CUBE + [{"id": "s", "type": "sphere", "radius": 3, "name": "boss"}])
        forward = diff_module.diff_parts(a, b)
        self.assertEqual([(f.id, f.status) for f in forward.features], [("s", "added")])
        back = diff_module.diff_parts(b, a)
        self.assertEqual([(f.id, f.status) for f in back.features], [("s", "removed")])

    def test_reordering_is_detected(self):
        f1 = {"id": "a", "type": "box", "size": [1, 1, 1]}
        f2 = {"id": "b", "type": "sphere", "radius": 1}
        d = diff_module.diff_parts(part([f1, f2]), part([f2, f1]))
        self.assertTrue(any(f.status == "reordered" for f in d.features))

    def test_vector_fields_diff_per_axis(self):
        a = part([{"id": "b", "type": "box", "size": [10, 10, 10], "center": [0, 0, 0]}])
        b = part([{"id": "b", "type": "box", "size": [10, 10, 10], "center": [0, 5, 0]}])
        d = diff_module.diff_parts(a, b)
        self.assertEqual([c.key for c in d.features[0].changes], ["center.y"])

    def test_volumetric_diff_locates_added_material(self):
        a = part(CUBE).evaluate(48)
        b = part(CUBE + [{"id": "boss", "type": "box", "size": [6, 6, 6],
                          "center": [0, 0, 12]}]).evaluate(48)
        v = diff_module.diff_volumes(a, b, resolution=56)
        self.assertGreater(v.added_volume, 100)
        self.assertLess(v.removed_volume, 5)
        self.assertTrue(v.regions)
        self.assertGreater(v.regions[0].centroid[2], 8)

    def test_reexport_reports_no_design_change(self):
        mesh = part(CUBE).evaluate(32)
        rng = np.random.default_rng(5)
        noisy = Mesh(mesh.vertices + (rng.random(mesh.vertices.shape) - 0.5) * 2e-5,
                     mesh.faces[rng.permutation(len(mesh.faces))])
        old = model_module.load("p.stl", stl_format.dump_binary(mesh, b"first"))
        new = model_module.load("p.stl", stl_format.dump_binary(noisy, b"second"))
        d = diff_module.diff_models("p.stl", old, new)
        self.assertEqual(d.status, "reexported")

    def test_identical_bytes_are_unchanged(self):
        m = model_module.load("p.kpart", part(CUBE).dumps())
        self.assertEqual(diff_module.diff_models("p.kpart", m, m).status, "unchanged")


if __name__ == "__main__":
    unittest.main()
