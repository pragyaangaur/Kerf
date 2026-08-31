"""Parameter expressions and the part model."""

import unittest

import numpy as np

from conftest import CUBE, part
from kerf.parametric import (
    ExpressionError,
    Part,
    check_part,
    evaluate_expression,
    expression_dependencies,
)
from kerf.parametric.sdf import feature_bounds, feature_sdf
from kerf.parametric.sweep import default_range


class TestExpressions(unittest.TestCase):
    def test_arithmetic_and_functions(self):
        self.assertAlmostEqual(evaluate_expression("hole_d/2 + 1", {"hole_d": 8}), 5.0)
        self.assertAlmostEqual(evaluate_expression("sqrt(16)", {}), 4.0)
        self.assertAlmostEqual(evaluate_expression("max(2, 3) * pi", {}), 3 * np.pi)

    def test_unknown_name_is_rejected(self):
        with self.assertRaises(ExpressionError):
            evaluate_expression("nope + 1", {})

    def test_arbitrary_code_is_rejected(self):
        for hostile in ("__import__('os').system('echo hi')", "(1).__class__", "[x for x in (1,)]"):
            with self.assertRaises(ExpressionError):
                evaluate_expression(hostile, {})

    def test_dependencies_are_discovered(self):
        self.assertEqual(expression_dependencies("plate_t/2 + sqrt(rise)"), {"plate_t", "rise"})

    def test_parameters_may_reference_each_other(self):
        p = part(CUBE, {"a": 4, "b": "a * 2", "c": "b + 1"})
        self.assertEqual(p.resolved_parameters()["c"], 9)

    def test_circular_parameters_are_reported(self):
        p = part(CUBE, {"a": "b", "b": "a"})
        with self.assertRaises(ExpressionError):
            p.resolved_parameters()


class TestPart(unittest.TestCase):
    def test_round_trip(self):
        p = part(CUBE, {"a": 1})
        self.assertEqual(Part.loads(p.dumps()).dumps(), p.dumps())

    def test_duplicate_feature_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            part([CUBE[0], CUBE[0]])

    def test_suppressed_features_do_not_evaluate(self):
        both = part([CUBE[0], {"id": "s", "type": "sphere", "radius": 30}]).evaluate(32).volume()
        one = part([CUBE[0], {"id": "s", "type": "sphere", "radius": 30,
                              "suppressed": True}]).evaluate(32).volume()
        self.assertLess(one, both)

    def test_parametric_edit_changes_volume_predictably(self):
        thin = part([{"id": "b", "type": "box", "size": [20, 20, "t"]}], {"t": 5}).evaluate(48)
        thick = part([{"id": "b", "type": "box", "size": [20, 20, "t"]}], {"t": 10}).evaluate(48)
        self.assertAlmostEqual(thick.volume() / thin.volume(), 2.0, delta=0.05)


class TestBadArithmeticIsReported(unittest.TestCase):
    """A part file arrives from other people, so nothing here may escape."""

    def test_arithmetic_failures_become_expression_errors(self):
        for text in ("1/0", "1%0", "sqrt(-1)", "1e308*10", "0/0"):
            with self.subTest(expression=text):
                with self.assertRaises(ExpressionError):
                    evaluate_expression(text, {})

    def test_a_huge_exponent_is_refused_rather_than_computed(self):
        with self.assertRaises(ExpressionError):
            evaluate_expression("2**(2**30)", {})

    def test_a_parameter_table_that_divides_by_zero_reports_itself(self):
        broken = part(CUBE, {"a": 1, "b": "a/0"})
        with self.assertRaises(ExpressionError):
            broken.resolved_parameters()
        issues = check_part(broken)
        self.assertTrue(issues)
        self.assertEqual(issues[0].severity, "error")


class TestPartFileValidation(unittest.TestCase):
    def test_an_axis_outside_xyz_is_refused_when_the_file_is_read(self):
        with self.assertRaises(ValueError):
            part([{"id": "c", "type": "cylinder", "axis": "w",
                   "radius": 1, "height": 2}])

    def test_the_document_has_to_have_the_right_shape(self):
        for text in ('[]', '{"kerf_part": 1, "parameters": []}',
                     '{"kerf_part": 1, "features": {}}',
                     '{"kerf_part": 1, "parameters": {"not a name": 1}}'):
            with self.subTest(document=text):
                with self.assertRaises(ValueError):
                    Part.loads(text)


class TestRotatedBounds(unittest.TestCase):
    """The lattice has to hold the rotated shape, not the shape it started as."""

    def test_a_turned_bar_reports_the_box_around_where_it_ended_up(self):
        item = part([{"id": "b", "type": "box", "size": [100, 2, 2],
                      "rotate": [0, 0, 45]}]).features[0]
        low, high = feature_bounds(item, {})
        self.assertAlmostEqual(high[0], 100 / 2 * np.sqrt(2) / 2 + np.sqrt(2) / 2, places=6)
        self.assertAlmostEqual(high[0], high[1], places=9)

    def test_no_solid_falls_outside_the_bounds_that_were_reported(self):
        rng = np.random.default_rng(7)
        for trial in range(24):
            kind = ["box", "cylinder", "sphere", "torus"][trial % 4]
            raw = {"id": "f", "type": kind,
                   "rotate": rng.uniform(-180, 180, 3).tolist(),
                   "center": rng.uniform(-5, 5, 3).tolist()}
            if kind == "box":
                raw["size"] = rng.uniform(2, 20, 3).tolist()
            elif kind == "cylinder":
                raw.update(radius=float(rng.uniform(1, 8)),
                           height=float(rng.uniform(2, 30)), axis="xyz"[trial % 3])
            elif kind == "sphere":
                raw["radius"] = float(rng.uniform(1, 8))
            else:
                raw.update(radius=float(rng.uniform(2, 8)),
                           tube=float(rng.uniform(0.3, 2)))
            item = part([raw]).features[0]
            low, high = feature_bounds(item, {})
            reach = float(np.abs(high - low).max())
            centre = np.asarray(raw["center"])
            axes = [np.linspace(centre[i] - reach, centre[i] + reach, 40) for i in range(3)]
            points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1)
            solid = points[feature_sdf(item, points, {}) < 0]
            if not len(solid):
                continue
            with self.subTest(kind=kind, rotate=raw["rotate"]):
                self.assertTrue(np.all(solid.min(axis=0) >= low - 1e-9))
                self.assertTrue(np.all(solid.max(axis=0) <= high + 1e-9))


class TestSweepRanges(unittest.TestCase):
    def test_a_range_never_runs_backwards_or_crosses_zero(self):
        for value in (10.0, 1.0, 0.25, -10.0, -0.25, 0.0):
            with self.subTest(value=value):
                low, high = default_range(value)
                self.assertLess(low, high)
                self.assertGreater(low * high, 0.0)

    def test_a_negative_parameter_is_swept_on_its_own_side_of_zero(self):
        low, high = default_range(-10.0)
        self.assertLess(high, 0.0)
        self.assertLess(low, high)


if __name__ == "__main__":
    unittest.main()
