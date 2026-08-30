"""The object store and the objects it holds."""

import tempfile
import unittest

from kerf.objects import Commit, ObjectStore, Tree, TreeEntry


class TestObjectStore(unittest.TestCase):
    def test_put_get_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(tmp)
            a = store.put("blob", b"hello")
            b = store.put("blob", b"hello")
            self.assertEqual(a, b)
            self.assertEqual(store.get(a), ("blob", b"hello"))

    def test_prefix_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(tmp)
            oid = store.put("blob", b"x")
            self.assertEqual(store.resolve_prefix(oid[:8]), oid)
            self.assertIsNone(store.resolve_prefix("zz"))

    def test_tree_and_commit_round_trip(self):
        tree = Tree({"a.stl": TreeEntry("a.stl", "0" * 64, "1" * 64, "mesh", 12)})
        self.assertEqual(Tree.deserialize(tree.serialize()).entries["a.stl"].gid, "1" * 64)
        commit = Commit("t", ["p"], "me", 5, "subject\n\nbody", {"k": "v"})
        back = Commit.deserialize(commit.serialize())
        self.assertEqual((back.tree, back.parents, back.short(), back.meta),
                         ("t", ["p"], "subject", {"k": "v"}))


if __name__ == "__main__":
    unittest.main()
