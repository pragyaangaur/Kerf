"""Reading and writing the mesh formats."""

import unittest

import numpy as np

from conftest import CUBE, part
from kerf import model as model_module
from kerf.formats import obj as obj_format
from kerf.formats import stl as stl_format
from kerf.geometry import Mesh


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


class TestMalformedFiles(unittest.TestCase):
    """A mesh arrives from another tool, so a broken one has to load quietly.

    Carrying a bad face index into the Mesh meant the file read fine and then
    raised IndexError from inside whichever measurement touched it first.
    """

    def test_a_face_pointing_past_the_vertices_is_dropped(self):
        mesh = obj_format.load(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 99\n")
        self.assertEqual(len(mesh.faces), 0)
        self.assertEqual(mesh.stats()["triangles"], 0)

    def test_obj_index_zero_is_dropped(self):
        mesh = obj_format.load(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 0 1 2\n")
        self.assertEqual(len(mesh.faces), 0)

    def test_obj_negative_indices_still_count_back_from_here(self):
        mesh = obj_format.load(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\n")
        self.assertEqual(len(mesh.faces), 1)

    def test_a_number_that_will_not_parse_does_not_take_the_read_down(self):
        mesh = obj_format.load(b"v a b c\nv 1 0 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\n")
        self.assertEqual(len(mesh.vertices), 3)
        self.assertEqual(mesh.stats()["triangles"], 1)

    def test_a_text_stl_starting_with_whitespace_is_not_read_as_binary(self):
        mesh = Mesh.from_triangles(np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float))
        text = b"   " + stl_format.dump_ascii(mesh) + b"\n" * 200
        self.assertFalse(stl_format.looks_binary(text))
        self.assertEqual(len(stl_format.load(text).faces), 1)


if __name__ == "__main__":
    unittest.main()
