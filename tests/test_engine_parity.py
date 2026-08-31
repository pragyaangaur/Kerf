"""The Python engine and the JavaScript engine, asked the same questions.

The two are separate implementations of the same design. The README says
they agree, and until now that was a claim checked by hand, which is the
kind of claim that stops being true without anybody noticing. This asks both
engines the same things and compares the answers.

Node is not a dependency of kerf, so these are skipped when it is missing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

from conftest import part
from kerf.parametric import Part, evaluate_expression, measure_solid
from kerf.parametric.expr import ExpressionError
from kerf.parametric.sdf import feature_bounds
from kerf.parametric.sweep import default_range

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "web", "engine", "probe.mjs")
NODE = shutil.which("node")

# The two engines sample the same field on the same lattice and run the same
# algorithms, so the answers agree to the width of a float. The browser holds
# its field in a Float32Array, which is what sets the margin here. Anything
# larger than this is a difference in method, not in arithmetic.
TOLERANCE = 1e-6


def ask(job: dict) -> dict:
    """Put a question to the JavaScript engine and read the answer back."""
    result = subprocess.run(
        [NODE, PROBE], input=json.dumps(job),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(f"the javascript engine failed:\n{result.stderr}")
    return json.loads(result.stdout)


@unittest.skipIf(NODE is None, "node is not installed")
class TestEngineParity(unittest.TestCase):
    def test_expressions_agree(self):
        cases = [
            ("bolt_d/2", {"bolt_d": 8}),
            ("sqrt(16) + 1", {}),
            ("max(2, 3) * pi", {}),
            ("-plate_t * 2", {"plate_t": 7}),
            ("hypot(3, 4)", {}),
            ("(a + b) / (a - b)", {"a": 10, "b": 4}),
            ("2**10", {}),
            ("round(7.6)", {}),
        ]
        answers = ask({"expressions": cases})["expressions"]
        for (text, params), answer in zip(cases, answers):
            with self.subTest(expression=text):
                self.assertNotIn("error", answer, answer.get("error"))
                self.assertAlmostEqual(
                    evaluate_expression(text, params), answer["value"], places=9
                )

    def test_both_engines_refuse_the_same_expressions(self):
        cases = [("1/0", {}), ("0/0", {}), ("missing + 1", {})]
        answers = ask({"expressions": cases})["expressions"]
        for (text, params), answer in zip(cases, answers):
            with self.subTest(expression=text):
                self.assertIn("error", answer)
                with self.assertRaises(ExpressionError):
                    evaluate_expression(text, params)

    def test_default_sweep_ranges_agree(self):
        values = [10.0, 1.0, 0.5, -10.0, -0.5, 0.0]
        answers = ask({"ranges": values})["ranges"]
        for value, answer in zip(values, answers):
            with self.subTest(value=value):
                low, high = default_range(value)
                self.assertAlmostEqual(low, answer[0], places=9)
                self.assertAlmostEqual(high, answer[1], places=9)
                self.assertLess(low, high)

    def test_feature_bounds_agree_including_rotation(self):
        features = [
            {"type": "box", "size": [60, 46, 7], "center": [0, 0, 3.5]},
            {"type": "box", "size": [100, 2, 2], "rotate": [0, 0, 45]},
            {"type": "box", "size": [10, 20, 30], "rotate": [30, 40, 50]},
            {"type": "cylinder", "radius": 4, "height": 40, "axis": "y"},
            {"type": "cylinder", "radius": 4, "height": 40, "axis": "z",
             "rotate": [90, 0, 0]},
            {"type": "sphere", "radius": 9, "center": [1, 2, 3]},
            {"type": "torus", "radius": 8, "tube": 1.5, "rotate": [0, 90, 0]},
        ]
        answers = ask({"bounds": features})["bounds"]
        for raw, answer in zip(features, answers):
            with self.subTest(feature=raw["type"], rotate=raw.get("rotate")):
                item = part([dict(raw, id="f")]).features[0]
                low, high = feature_bounds(item, {})
                for axis in range(3):
                    self.assertAlmostEqual(low[axis], answer[0][axis], places=6)
                    self.assertAlmostEqual(high[axis], answer[1][axis], places=6)

    def test_the_worked_examples_measure_the_same(self):
        resolution = 32
        names = ["nema17-bracket.kpart", "shaft-spacer.kpart"]
        texts = [
            open(os.path.join(ROOT, "examples", name), encoding="utf-8").read()
            for name in names
        ]
        answers = ask(
            {"parts": [{"text": text, "resolution": resolution} for text in texts]}
        )["parts"]

        for name, text, answer in zip(names, texts, answers):
            with self.subTest(part=name):
                model = Part.loads(text)
                self.assertEqual(model.resolved_parameters(), answer["parameters"])
                volume, bodies = measure_solid(model, resolution)
                self.assertEqual(bodies, answer["bodies"])
                self.assertAlmostEqual(
                    volume, answer["volume"], delta=abs(volume) * TOLERANCE
                )
                mesh = model.evaluate(resolution)
                self.assertEqual(len(mesh.faces), answer["triangles"])
                # Both meshes have to be closed. A tessellator that drops the
                # faces at the edge of its own lattice still looks right from
                # most angles, so this is worth asserting rather than eyeing.
                self.assertTrue(mesh.is_watertight())
                self.assertTrue(answer["watertight"])
                self.assertAlmostEqual(
                    mesh.volume(),
                    answer["meshVolume"],
                    delta=abs(mesh.volume()) * TOLERANCE,
                )


if __name__ == "__main__":                           # pragma: no cover
    unittest.main()
