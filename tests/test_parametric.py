"""Parameter expressions and the part model."""

import unittest

import numpy as np

from conftest import CUBE, part
from kerf.parametric import ExpressionError, Part, evaluate_expression, expression_dependencies


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


if __name__ == "__main__":
    unittest.main()
