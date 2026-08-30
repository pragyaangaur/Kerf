"""The equation graph, model validity, and parameter sweeps."""

import math
import unittest

from conftest import CUBE, part
from kerf.parametric import build_graph, check_equations, check_part, measure_solid
from kerf.parametric.sweep import default_range, sweep_all, sweep_parameter


class TestGraph(unittest.TestCase):
    def setUp(self):
        self.part = part(
            [
                {"id": "plate", "type": "box", "name": "plate",
                 "size": ["width", "depth", "t"], "center": [0, 0, "t/2"]},
                {"id": "hole", "type": "cylinder", "name": "bolt hole", "op": "subtract",
                 "radius": "bolt_d/2", "height": 40, "axis": "z",
                 "center": ["pitch/2", 0, 0]},
            ],
            {"width": 60, "depth": 40, "t": 6, "bolt_d": 3.4, "pitch": "width - 20"},
        )
        self.graph = build_graph(self.part)

    def test_parameters_and_driven_fields_are_found(self):
        self.assertEqual(set(self.graph.parameters), {"width", "depth", "t", "bolt_d", "pitch"})
        names = {ref.name for ref in self.graph.fields}
        self.assertIn("plate.size.x", names)
        self.assertIn("hole.center.x", names)

    def test_an_axis_is_not_read_as_a_parameter(self):
        # "z" in an axis field names a direction, and reading it as an
        # expression would invent a parameter nobody wrote.
        self.assertEqual(self.graph.dangling(), [])
        self.assertNotIn("z", {name for ref in self.graph.fields for name in ref.reads})

    def test_readers_and_downstream(self):
        self.assertIn("pitch", self.graph.readers_of("width"))
        self.assertIn("plate.size.x", self.graph.readers_of("width"))
        self.assertIn("hole.center.x", self.graph.downstream("width"))

    def test_upstream_walks_through_other_parameters(self):
        self.assertEqual(self.graph.upstream("pitch"), {"width"})

    def test_features_reached_through_another_parameter(self):
        # width drives pitch, and pitch places the hole, so width reaches the hole.
        self.assertIn("bolt hole", self.graph.feature_readers_of("width"))

    def test_roots_and_leaves(self):
        self.assertIn("width", self.graph.roots())
        self.assertNotIn("pitch", self.graph.roots())
        self.assertIn("depth", self.graph.leaves() + self.graph.roots())

    def test_order_puts_a_parameter_after_what_it_reads(self):
        order = self.graph.order()
        self.assertLess(order.index("width"), order.index("pitch"))

    def test_dangling_reference_is_reported(self):
        broken = part([{"id": "x", "type": "box", "size": ["a", "gone", 3]}], {"a": 2})
        self.assertEqual(build_graph(broken).dangling(), [("x.size.y", "gone")])

    def test_a_loop_is_reported(self):
        loop = part(CUBE, {"a": "b + 1", "b": "a + 1"})
        cycles = build_graph(loop).cycles()
        self.assertTrue(cycles)
        self.assertEqual(set(cycles[0]), {"a", "b"})


class TestValidity(unittest.TestCase):
    def test_a_healthy_part_has_nothing_to_report(self):
        self.assertEqual(check_part(part(CUBE)), [])

    def test_dangling_reference_is_an_error(self):
        issues = check_part(part([{"id": "x", "type": "box", "size": [1, "gone", 1]}]))
        self.assertEqual([i.severity for i in issues], ["error"])
        self.assertIn("gone", issues[0].message)

    def test_a_loop_is_an_error(self):
        issues = check_part(part(CUBE, {"a": "b", "b": "a"}))
        self.assertTrue(any(i.scope == "equation" for i in issues))

    def test_a_size_of_zero_is_an_error(self):
        issues = check_part(part([{"id": "x", "type": "box", "size": [10, 10, "t"]}], {"t": 0}))
        self.assertTrue(any("above zero" in i.message for i in issues))

    def test_a_part_eaten_by_its_own_cut_is_an_error(self):
        eaten = part([
            {"id": "b", "type": "box", "size": [10, 10, 10]},
            {"id": "c", "type": "sphere", "op": "subtract", "radius": 40},
        ])
        self.assertTrue(any("builds to nothing" in i.message for i in check_part(eaten)))

    def test_a_part_cut_in_two_is_a_warning(self):
        split = part([
            {"id": "b", "type": "box", "size": [40, 10, 10]},
            {"id": "c", "type": "box", "op": "subtract", "size": [12, 30, 30]},
        ])
        issues = check_part(split)
        self.assertEqual([i.severity for i in issues], ["warning"])
        self.assertIn("2 separate bodies", issues[0].message)

    def test_equation_check_alone_does_not_build_geometry(self):
        # A part with a broken equation cannot be evaluated, and the equation
        # check still has to answer rather than raise.
        self.assertTrue(check_equations(part([{"id": "x", "type": "box", "size": ["q", 1, 1]}])))


class TestMeasurement(unittest.TestCase):
    def test_volume_matches_a_known_solid(self):
        volume, bodies = measure_solid(part(CUBE), 32)
        self.assertAlmostEqual(volume, 8000, delta=8000 * 0.01)
        self.assertEqual(bodies, 1)

    def test_volume_converges_rather_than_oscillating(self):
        # Counting whole cells aliases badly on a face that lies along the
        # lattice, so the estimate uses how far the surface cuts each cell.
        sphere = part([{"id": "s", "type": "sphere", "radius": 10}])
        expected = 4 / 3 * math.pi * 1000
        for resolution in (16, 24, 32):
            volume, _ = measure_solid(sphere, resolution)
            self.assertAlmostEqual(volume, expected, delta=expected * 0.02)

    def test_two_bodies_are_counted(self):
        pair = part([
            {"id": "a", "type": "sphere", "radius": 5, "center": [-20, 0, 0]},
            {"id": "b", "type": "sphere", "radius": 5, "center": [20, 0, 0]},
        ])
        self.assertEqual(measure_solid(pair, 24)[1], 2)


class TestSweep(unittest.TestCase):
    def test_a_sound_parameter_holds_across_its_range(self):
        result = sweep_parameter(part([
            {"id": "b", "type": "box", "size": [20, 20, "t"]}], {"t": 6}), "t", 2, 12, 6, 20)
        self.assertTrue(result.robust())
        self.assertEqual(result.working_range(), (2, 12))

    def test_volume_follows_the_parameter(self):
        result = sweep_parameter(part([
            {"id": "b", "type": "box", "size": [20, 20, "t"]}], {"t": 6}), "t", 2, 10, 5, 20)
        volumes = [point.volume for point in result.points]
        self.assertEqual(volumes, sorted(volumes), "a thicker plate cannot hold less material")

    def test_a_failing_value_is_found_and_explained(self):
        # A bore wider than the tube leaves nothing behind.
        tube = part([
            {"id": "body", "type": "cylinder", "radius": 8, "height": 10},
            {"id": "bore", "type": "cylinder", "op": "subtract", "radius": "id/2", "height": 20},
        ], {"id": 8})
        result = sweep_parameter(tube, "id", 4, 24, 6, 20)
        self.assertFalse(result.robust())
        self.assertTrue(result.failures())
        self.assertIn("nothing", result.failures()[-1].reason)

    def test_working_range_stops_at_the_first_failure(self):
        tube = part([
            {"id": "body", "type": "cylinder", "radius": 8, "height": 10},
            {"id": "bore", "type": "cylinder", "op": "subtract", "radius": "id/2", "height": 20},
        ], {"id": 8})
        result = sweep_parameter(tube, "id", 4, 24, 6, 20)
        low, high = result.working_range()
        self.assertLessEqual(low, 8)
        self.assertLess(high, 24)

    def test_a_split_body_is_reported_as_a_warning_not_a_failure(self):
        bar = part([
            {"id": "b", "type": "box", "size": [40, 10, 10]},
            {"id": "c", "type": "box", "op": "subtract", "size": ["w", 30, 30]},
        ], {"w": 4})
        result = sweep_parameter(bar, "w", 2, 14, 5, 20)
        self.assertTrue(result.warnings())
        self.assertIn("separate bodies", result.summary())

    def test_sweeping_an_unknown_parameter_is_refused(self):
        with self.assertRaises(KeyError):
            sweep_parameter(part(CUBE), "nope", 1, 2, 3)

    def test_sweep_all_skips_parameters_written_as_expressions(self):
        # Replacing an expression with a number would delete the relationship
        # its author wrote down, so those parameters are left alone.
        subject = part([{"id": "b", "type": "box", "size": ["w", "w", "half"]}],
                       {"w": 20, "half": "w/2"})
        swept = {result.parameter for result in sweep_all(subject, steps=3, resolution=16)}
        self.assertEqual(swept, {"w"})

    def test_default_range_stays_above_zero(self):
        low, high = default_range(6.0, 1.5)
        self.assertGreater(low, 0)
        self.assertGreater(high, 6.0)


if __name__ == "__main__":
    unittest.main()
