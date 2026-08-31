"""Three way merge of feature trees."""

import unittest

from conftest import CUBE, part
from kerf import merge as merge_module


class TestMerge(unittest.TestCase):
    def test_disjoint_parameter_edits_merge(self):
        base = part(CUBE, {"a": 1, "b": 2})
        ours = part(CUBE, {"a": 5, "b": 2})
        theirs = part(CUBE, {"a": 1, "b": 9})
        merged, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual(conflicts, [])
        self.assertEqual(merged.parameters, {"a": 5, "b": 9})

    def test_same_parameter_edited_both_sides_conflicts(self):
        base, ours, theirs = part(CUBE, {"a": 1}), part(CUBE, {"a": 2}), part(CUBE, {"a": 3})
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual([c.scope for c in conflicts], ["parameter"])

    def test_identical_edits_on_both_sides_are_not_a_conflict(self):
        base, ours, theirs = part(CUBE, {"a": 1}), part(CUBE, {"a": 7}), part(CUBE, {"a": 7})
        merged, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual(conflicts, [])
        self.assertEqual(merged.parameters["a"], 7)

    def test_features_added_on_both_sides_are_kept(self):
        base = part(CUBE)
        ours = part(CUBE + [{"id": "x", "type": "sphere", "radius": 2, "center": [-30, 0, 0]}])
        theirs = part(CUBE + [{"id": "y", "type": "sphere", "radius": 2, "center": [30, 0, 0]}])
        merged, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual(conflicts, [])
        self.assertEqual({f.id for f in merged.features}, {"b", "x", "y"})

    def test_delete_versus_modify_conflicts(self):
        base = part(CUBE + [{"id": "x", "type": "sphere", "radius": 2}])
        ours = part(CUBE)
        theirs = part(CUBE + [{"id": "x", "type": "sphere", "radius": 4}])
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertTrue(any(c.scope == "feature" for c in conflicts))

    def test_component_wise_vector_merge(self):
        base = part([{"id": "b", "type": "box", "size": [1, 1, 1], "center": [0, 0, 0]}])
        ours = part([{"id": "b", "type": "box", "size": [1, 1, 1], "center": [5, 0, 0]}])
        theirs = part([{"id": "b", "type": "box", "size": [1, 1, 1], "center": [0, 7, 0]}])
        merged, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual(conflicts, [])
        self.assertEqual(merged.features[0].params["center"], [5, 7, 0])

    def test_interference_between_independently_added_features(self):
        base = part(CUBE)
        ours = part(CUBE + [{"id": "rib", "type": "box", "name": "rib",
                             "size": [4, 20, 20], "center": [0, 0, 14]}])
        theirs = part(CUBE + [{"id": "hole", "type": "cylinder", "op": "subtract",
                               "name": "hole", "radius": 3, "height": 40,
                               "center": [0, 0, 14]}])
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertTrue(any(c.scope == "interference" for c in conflicts),
                        "a cut through a newly added rib must not merge silently")

    def test_interference_check_can_be_skipped(self):
        base = part(CUBE)
        ours = part(CUBE + [{"id": "rib", "type": "box", "size": [4, 20, 20], "center": [0, 0, 14]}])
        theirs = part(CUBE + [{"id": "hole", "type": "cylinder", "op": "subtract",
                               "radius": 3, "height": 40, "center": [0, 0, 14]}])
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs, check_interference=False)
        self.assertEqual(conflicts, [])

    def test_a_merge_that_breaks_an_equation_is_refused(self):
        # One side renames a parameter, the other writes a dimension that
        # reads the old name. Each branch builds. The merge would not.
        base = part(CUBE, {"bolt_pitch": 31})
        ours = part(CUBE, {"hole_pitch": 31})
        theirs = part(CUBE + [{
            "id": "hole", "type": "cylinder", "op": "subtract", "name": "new hole",
            "radius": 2, "height": 40, "center": ["bolt_pitch/2", 0, 0],
        }], {"bolt_pitch": 31})
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual([c.scope for c in conflicts], ["equation"])
        self.assertIn("bolt_pitch", conflicts[0].detail)

    def test_each_branch_builds_on_its_own(self):
        from kerf.parametric import check_equations

        ours = part(CUBE, {"hole_pitch": 31})
        theirs = part(CUBE + [{
            "id": "hole", "type": "cylinder", "op": "subtract",
            "radius": 2, "height": 40, "center": ["bolt_pitch/2", 0, 0],
        }], {"bolt_pitch": 31})
        self.assertEqual(check_equations(ours), [])
        self.assertEqual(check_equations(theirs), [])

    def test_breakage_that_predates_the_merge_is_not_blamed_on_it(self):
        broken = {"id": "h", "type": "cylinder", "op": "subtract",
                  "radius": "missing", "height": 10}
        base = part(CUBE + [broken])
        ours = part(CUBE + [broken], {"a": 1})
        theirs = part(CUBE + [broken], {"b": 2})
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual(conflicts, [])

    def test_the_equation_check_can_be_skipped(self):
        base = part(CUBE, {"bolt_pitch": 31})
        ours = part(CUBE, {"hole_pitch": 31})
        theirs = part(CUBE + [{
            "id": "hole", "type": "cylinder", "op": "subtract",
            "radius": 2, "height": 40, "center": ["bolt_pitch/2", 0, 0],
        }], {"bolt_pitch": 31})
        _, conflicts, _ = merge_module.merge_parts(
            "p", base, ours, theirs, check_equations=False
        )
        self.assertEqual(conflicts, [])

    def test_far_apart_features_do_not_interfere(self):
        base = part(CUBE)
        ours = part(CUBE + [{"id": "left", "type": "sphere", "radius": 2, "center": [-40, 0, 0]}])
        theirs = part(CUBE + [{"id": "right", "type": "sphere", "radius": 2, "center": [40, 0, 0]}])
        _, conflicts, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertEqual(conflicts, [])


class TestFeatureOrder(unittest.TestCase):
    """Reordering used to crash whenever either side had also added a feature.

    The sort key called list.index on the list being sorted, and CPython
    empties a list while it runs the key over it, so the lookup raised.
    """

    @staticmethod
    def tree(ids):
        return part([{"id": name, "type": "box", "size": [1, 1, 1],
                      "center": [index * 10, 0, 0]}
                     for index, name in enumerate(ids)])

    def test_their_order_wins_when_only_they_reordered(self):
        merged, conflicts, _ = merge_module.merge_parts(
            "p", self.tree("ab"), self.tree("ab"), self.tree("ba"),
        )
        self.assertEqual([item.id for item in merged.features], ["b", "a"])
        self.assertEqual(conflicts, [])

    def test_a_reorder_alongside_an_addition_does_not_crash(self):
        merged, _, _ = merge_module.merge_parts(
            "p", self.tree("ab"), self.tree("ab"), self.tree("bac"),
        )
        self.assertEqual([item.id for item in merged.features], ["b", "a", "c"])

    def test_a_feature_only_we_have_keeps_the_place_it_holds(self):
        merged, _, _ = merge_module.merge_parts(
            "p", self.tree("ab"), self.tree("azb"), self.tree("ba"),
        )
        self.assertEqual([item.id for item in merged.features], ["b", "a", "z"])

    def test_both_sides_reordering_is_a_conflict(self):
        _, conflicts, _ = merge_module.merge_parts(
            "p", self.tree("abc"), self.tree("bca"), self.tree("cab"),
        )
        self.assertTrue(any(c.scope == "order" for c in conflicts))


class TestMergedPartOwnsItsFeatures(unittest.TestCase):
    def test_a_feature_taken_from_theirs_is_copied_not_shared(self):
        base = part(CUBE)
        ours = part(CUBE)
        theirs = part(CUBE + [{"id": "new", "type": "sphere", "radius": 2,
                               "center": [40, 0, 0]}])
        merged, _, _ = merge_module.merge_parts("p", base, ours, theirs)
        self.assertIsNot(merged.feature("new"), theirs.feature("new"))
        merged.feature("new").params["radius"] = 99
        self.assertEqual(theirs.feature("new").params["radius"], 2)


if __name__ == "__main__":
    unittest.main()
