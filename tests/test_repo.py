"""The repository, staging, status, and locks."""

import os
import tempfile
import unittest

import numpy as np

from conftest import CUBE, part
from kerf import diff as diff_module
from kerf import merge as merge_module
from kerf import model as model_module
from kerf.formats import stl as stl_format
from kerf.geometry import Mesh
from kerf.repo import Repo, RepoError


class TestRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.repo = Repo.init(self.root, author="tester")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel: str, data: bytes):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def test_commit_and_history(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        first = self.repo.commit("one")
        self.write("a.kpart", part(CUBE, {"z": 1}).dumps())
        self.repo.add(["a.kpart"])
        second = self.repo.commit("two")
        self.assertEqual([oid for oid, _ in self.repo.history()], [second, first])
        self.assertEqual(self.repo.resolve("HEAD~1"), first)

    def test_empty_commit_is_refused(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        self.repo.commit("one")
        with self.assertRaises(RepoError):
            self.repo.commit("again")

    def test_status_calls_a_reexport_a_reexport(self):
        mesh = part(CUBE).evaluate(28)
        self.write("a.stl", stl_format.dump_binary(mesh, b"one"))
        self.repo.add(["a.stl"])
        self.repo.commit("first")
        rng = np.random.default_rng(11)
        noisy = Mesh(mesh.vertices + (rng.random(mesh.vertices.shape) - 0.5) * 1e-5,
                     mesh.faces[rng.permutation(len(mesh.faces))])
        self.write("a.stl", stl_format.dump_binary(noisy, b"two"))
        _, unstaged = self.repo.status()
        self.assertEqual([(e.path, e.state) for e in unstaged if e.path == "a.stl"],
                         [("a.stl", "reexported")])

    def test_checkout_restores_working_tree(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        first = self.repo.commit("one")
        self.write("b.kpart", part(CUBE).dumps())
        self.repo.add(["b.kpart"])
        self.repo.commit("two")
        self.repo.checkout(first)
        self.assertFalse(os.path.exists(os.path.join(self.root, "b.kpart")))
        self.assertTrue(os.path.exists(os.path.join(self.root, "a.kpart")))

    def test_checkout_refuses_to_discard_work(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        first = self.repo.commit("one")
        self.repo.create_branch("side")
        self.write("a.kpart", part(CUBE, {"q": 2}).dumps())
        with self.assertRaises(RepoError):
            self.repo.checkout("side")
        self.repo.checkout("side", force=True)      # explicit override is allowed

    def test_feature_tree_edit_with_identical_geometry_is_flagged(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        self.repo.commit("one")
        renamed = part([dict(CUBE[0], name="renamed body")]).dumps()
        self.write("a.kpart", renamed)
        _, unstaged = self.repo.status()
        self.assertEqual([e.state for e in unstaged if e.path == "a.kpart"], ["rewritten"])

    def test_locks_block_other_authors(self):
        self.write("a.stl", b"x")
        self.repo.lock("a.stl", "machining this", owner="rui")
        with self.assertRaises(RepoError):
            self.repo.add(["a.stl"])
        self.repo.add(["a.stl"], force=True)          # explicit override still works
        with self.assertRaises(RepoError):
            self.repo.unlock("a.stl")
        self.repo.unlock("a.stl", force=True)
        self.assertEqual(self.repo.locks(), {})

    def test_merge_base_finds_the_fork_point(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        root = self.repo.commit("root")
        self.repo.create_branch("side")
        self.write("a.kpart", part(CUBE, {"m": 1}).dumps())
        self.repo.add(["a.kpart"])
        main_tip = self.repo.commit("main work")
        self.repo.checkout("side")
        self.write("a.kpart", part(CUBE, {"s": 1}).dumps())
        self.repo.add(["a.kpart"])
        side_tip = self.repo.commit("side work")
        self.assertEqual(self.repo.merge_base(main_tip, side_tip), root)

    def test_rename_is_matched_by_geometry(self):
        self.write("old.kpart", part(CUBE).dumps())
        self.repo.add(["old.kpart"])
        first = self.repo.commit("one")
        os.rename(os.path.join(self.root, "old.kpart"), os.path.join(self.root, "new.kpart"))
        self.repo.unstage(["old.kpart"])
        self.repo.add(["new.kpart"])
        second = self.repo.commit("renamed")
        diffs = diff_module.diff_trees(self.repo, self.repo.commit_tree(first),
                                    self.repo.commit_tree(second), volumetric=False)
        renamed = [d for d in diffs if d.status.startswith("renamed")]
        self.assertEqual([(d.path, d.old_path) for d in renamed], [("new.kpart", "old.kpart")])

    def test_opaque_formats_are_tracked_without_geometry(self):
        self.write("x.sldprt", b"\x00binary garbage")
        entry = self.repo.add(["x.sldprt"])[0]
        self.assertEqual(entry.kind, "opaque")
        self.assertEqual(entry.gid, "")
        self.assertEqual(model_module.format_name("x.sldprt"), "SolidWorks part")

    def test_a_name_outside_the_repo_is_not_picked_up(self):
        # The same file name can exist in whatever directory the caller
        # happens to be standing in, and that file is not the tracked one.
        outside = os.path.join(tempfile.gettempdir(), "kerf-outside")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "shared.kpart"), "wb") as handle:
            handle.write(part(CUBE, {"outside": 1}).dumps())
        self.write("shared.kpart", part(CUBE, {"inside": 1}).dumps())
        previous = os.getcwd()
        os.chdir(outside)
        try:
            entry = self.repo.add(["shared.kpart"])[0]
        finally:
            os.chdir(previous)
        self.assertEqual(entry.path, "shared.kpart")

    def test_the_working_tree_can_be_compared_like_a_revision(self):
        self.write("a.kpart", part(CUBE, {"t": 5}).dumps())
        self.repo.add(["a.kpart"])
        self.repo.commit("one")
        self.write("a.kpart", part(CUBE, {"t": 9}).dumps())

        # Nothing was staged, so a comparison against the index has to look at
        # the files on disk or it reports a change that status just listed.
        diffs = diff_module.diff_trees(
            self.repo, self.repo.commit_tree("HEAD"), self.repo.worktree_tree(),
            volumetric=False,
        )
        self.assertEqual([d.path for d in diffs], ["a.kpart"])
        self.assertEqual(diffs[0].parametric.parameters[0].key, "t")

    def test_a_deleted_file_leaves_the_working_tree(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        self.repo.commit("one")
        os.remove(os.path.join(self.root, "a.kpart"))
        self.assertEqual(self.repo.worktree_tree().paths(), [])

    def test_export_writes_every_tracked_file(self):
        self.write("a.kpart", part(CUBE).dumps())
        self.repo.add(["a.kpart"])
        rev = self.repo.commit("one")
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(self.repo.export(rev, dest), 1)
            self.assertTrue(os.path.exists(os.path.join(dest, "a.kpart")))


class TestTreeMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo.init(self.tmp.name, author="tester")

    def tearDown(self):
        self.tmp.cleanup()

    def _commit(self, rel: str, data: bytes, message: str) -> str:
        path = os.path.join(self.tmp.name, rel)
        with open(path, "wb") as fh:
            fh.write(data)
        self.repo.add([rel])
        return self.repo.commit(message)

    def test_binary_edits_on_both_sides_conflict(self):
        mesh = part(CUBE).evaluate(24)
        base = self._commit("a.stl", stl_format.dump_binary(mesh, b"base"), "base")
        self.repo.create_branch("side")
        ours = self._commit("a.stl", stl_format.dump_binary(part([
            {"id": "b", "type": "box", "size": [22, 20, 20]}]).evaluate(24)), "ours")
        self.repo.checkout("side", force=True)
        theirs = self._commit("a.stl", stl_format.dump_binary(part([
            {"id": "b", "type": "box", "size": [20, 24, 20]}]).evaluate(24)), "theirs")
        result = merge_module.merge_trees(self.repo, self.repo.commit_tree(base),
                                       self.repo.commit_tree(ours),
                                       self.repo.commit_tree(theirs))
        self.assertFalse(result.clean)
        self.assertEqual([c.scope for c in result.conflicts], ["file"])

    def test_one_sided_change_takes_the_changed_side(self):
        base = self._commit("a.kpart", part(CUBE).dumps(), "base")
        self.repo.create_branch("side")
        self.repo.checkout("side")
        theirs = self._commit("a.kpart", part(CUBE, {"new": 3}).dumps(), "theirs")
        result = merge_module.merge_trees(self.repo, self.repo.commit_tree(base),
                                       self.repo.commit_tree(base),
                                       self.repo.commit_tree(theirs))
        self.assertTrue(result.clean)
        self.assertEqual([f.status for f in result.files], ["theirs"])


if __name__ == "__main__":
    unittest.main()
