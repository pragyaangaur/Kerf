"""Reading and writing the mesh formats."""

import unittest

from conftest import CUBE, part
from kerf import model as model_module
from kerf.formats import obj as obj_format
from kerf.formats import stl as stl_format


class TestFormats(unittest.TestCase):
    def setUp(self):
        self.mesh = part(CUBE).evaluate(24)

    def test_binary_stl_round_trip(self):
        data = stl_format.dump_binary(self.mesh)
        self.assertTrue(stl_format.looks_binary(data))
        back = stl_format.load(data)
        self.assertEqual(len(back.faces), len(self.mesh.faces))
        self.assertAlmostEqual(back.volume(), self.mesh.volume(), delta=1.0)

    def test_ascii_stl_round_trip(self):
        data = stl_format.dump_ascii(self.mesh)
        self.assertFalse(stl_format.looks_binary(data))
        self.assertEqual(len(stl_format.load(data).faces), len(self.mesh.faces))

    def test_binary_stl_with_solid_header_is_detected(self):
        data = bytearray(stl_format.dump_binary(self.mesh, header=b"solid not really ascii"))
        self.assertTrue(stl_format.looks_binary(bytes(data)))
        self.assertEqual(len(stl_format.load(bytes(data)).faces), len(self.mesh.faces))

    def test_obj_round_trip(self):
        back = obj_format.load(obj_format.dump(self.mesh))
        self.assertEqual(len(back.faces), len(self.mesh.faces))

    def test_obj_negative_indices_and_quads(self):
        src = b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf -4 -3 -2 -1\n"
        mesh = obj_format.load(src)
        self.assertEqual(len(mesh.faces), 2)          # quad fanned into two triangles

    def test_truncated_stl_is_reported_not_crashed(self):
        data = stl_format.dump_binary(self.mesh)[:200]
        m = model_module.load("x.stl", data)
        self.assertIsNone(m.mesh)
        self.assertIn("truncated", m.error)


if __name__ == "__main__":
    unittest.main()
