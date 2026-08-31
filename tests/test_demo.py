"""The worked example, run the way its own closing note tells you to.

`kerf demo` is the first thing anybody does with kerf, and the README quotes
its output. Every merge it advertises had to be run by hand to know whether
it still did what it says, and two of them had stopped: `kerf merge
cable-tie` only collides after the slots are merged, and the branch the
equation example needs did not exist at all.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from kerf.demo import build_demo
from kerf.parametric import Part, is_buildable
from kerf.repo import Repo

WALKTHROUGH = ["bore-fit", "mount-slots", "cable-tie", "fifth-bolt", "tidy-names"]


class TestDemo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "demo")
        self.repo = build_demo(self.root, quiet=True)

    def tearDown(self):
        self.tmp.cleanup()

    def bracket(self, rev: str) -> Part:
        return Part.loads(
            self.repo.store.get_typed(
                self.repo.commit_tree(rev).entries["parts/bracket.kpart"].oid, "blob"
            )
        )

    def merge(self, branch: str):
        """Merge one branch the way the command does, without the printing.

        A clean merge has to land its files, because the next merge in the
        walkthrough is against the result of this one.
        """
        from kerf import merge as merge_module

        head = self.repo.head_commit()
        other = self.repo.resolve(branch)
        base = self.repo.merge_base(head, other)
        if base == head:
            self.repo.write_ref(self.repo.head_ref(), other)
            self.repo.checkout(other, force=True)
            self.repo.set_head_to_branch("main")
            return None

        result = merge_module.merge_trees(
            self.repo,
            self.repo.commit_tree(base),
            self.repo.commit_tree(head),
            self.repo.commit_tree(other),
        )
        if result.conflicts:
            return result

        index = self.repo.read_index()
        for merged in result.files:
            if merged.status in ("unchanged", "ours") or merged.data is None:
                continue
            full = os.path.join(self.root, merged.path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as handle:
                handle.write(merged.data)
            index[merged.path] = self.repo.stage_entry(merged.path)
        self.repo.write_index(index)
        self.repo.commit(
            f"merge {branch}", parents=[head, other], allow_empty=True
        )
        return result

    def test_every_advertised_branch_exists(self):
        self.assertEqual(
            sorted(self.repo.branches()), sorted(["main"] + WALKTHROUGH)
        )

    def test_every_branch_builds_on_its_own(self):
        for branch in WALKTHROUGH:
            with self.subTest(branch=branch):
                self.assertTrue(is_buildable(self.bracket(branch), resolution=24))

    def test_the_walkthrough_ends_where_it_says_it_will(self):
        # A conflicting merge commits nothing, so the next one in the list
        # starts from the same place. That is what the command does too.
        results = {branch: self.merge(branch) for branch in WALKTHROUGH}

        self.assertIsNone(results["bore-fit"], "bore-fit should fast-forward")
        self.assertEqual(results["mount-slots"].conflicts, [])
        self.assertEqual(results["fifth-bolt"].conflicts, [])

        collision = results["cable-tie"].conflicts
        self.assertTrue(collision, "cable-tie should collide with the merged slots")
        self.assertEqual(collision[0].scope, "interference")
        self.assertIn("cable tie slot", collision[0].describe())

        broken = results["tidy-names"].conflicts
        self.assertTrue(broken, "tidy-names should leave an equation with nothing to read")
        self.assertEqual(broken[0].scope, "equation")
        self.assertIn("bolt_pitch", broken[0].describe())
        self.assertIn("does not define", broken[0].describe())

    def test_a_conflict_says_what_is_wrong_rather_than_printing_dashes(self):
        for branch in ("bore-fit", "mount-slots", "fifth-bolt"):
            self.merge(branch)
        for conflict in self.merge("tidy-names").conflicts:
            with self.subTest(key=conflict.key):
                self.assertNotIn("ours=-", conflict.describe())

    def test_the_re_export_revision_is_recorded_as_no_design_change(self):
        from kerf import diff as diff_module

        diffs = diff_module.diff_trees(
            self.repo, self.repo.commit_tree("main~1"), self.repo.commit_tree("main"),
        )
        housing = [d for d in diffs if d.path.endswith("idler-housing.stl")]
        self.assertEqual(len(housing), 1)
        self.assertEqual(housing[0].status, "reexported")


if __name__ == "__main__":                           # pragma: no cover
    unittest.main()
