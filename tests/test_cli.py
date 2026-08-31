"""The command line surface.

Some of these exist because the rest of the suite never imports the CLI, and
a syntax error there stayed hidden until somebody ran the tool on an older
Python. Importing every module is cheap and catches that class of mistake on
whichever versions the test matrix covers.

The rest run real commands in a temporary repository. Everything a command
raises reaches a person, so what it does with a bad argument is part of the
behaviour and worth pinning down.
"""

import contextlib
import importlib
import io
import os
import pkgutil
import tempfile
import unittest

import kerf
from conftest import CUBE, part


class TestEveryModuleImports(unittest.TestCase):
    def test_the_whole_package_imports(self):
        failed = []
        for module in pkgutil.walk_packages(kerf.__path__, prefix="kerf."):
            if module.name.endswith("__main__"):
                continue                     # importing it would run the CLI
            try:
                importlib.import_module(module.name)
            except Exception as error:       # noqa: BLE001
                failed.append(f"{module.name}: {type(error).__name__}: {error}")
        self.assertEqual(failed, [])


class TestParser(unittest.TestCase):
    def setUp(self):
        from kerf.cli import build_parser

        self.parser = build_parser()

    def test_every_command_is_reachable(self):
        expected = {
            "init", "add", "unstage", "status", "commit", "log", "diff", "show",
            "ls", "cat", "branch", "checkout", "restore", "merge", "equations",
            "check", "sweep", "lock", "unlock", "locks", "report", "view",
            "stats", "config", "export", "demo",
        }
        choices = set(self.parser._subparsers._group_actions[0].choices)
        self.assertEqual(choices, expected)

    def test_every_command_has_a_function_behind_it(self):
        actions = self.parser._subparsers._group_actions[0].choices
        for name, sub in actions.items():
            self.assertTrue(callable(sub.get_default("func")), f"{name} has no handler")

    def test_diff_compares_the_working_tree_unless_told_otherwise(self):
        self.assertFalse(self.parser.parse_args(["diff"]).staged)
        self.assertTrue(self.parser.parse_args(["diff", "--staged"]).staged)

    def test_merge_gates_are_on_by_default(self):
        args = self.parser.parse_args(["merge", "side"])
        self.assertFalse(args.no_interference)
        self.assertFalse(args.no_equation_check)


def run(argv, cwd):
    """Run one command and return its exit code with everything it printed."""
    from kerf.cli import main

    out, err = io.StringIO(), io.StringIO()
    here = os.getcwd()
    os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(argv)
            except SystemExit as exit_code:
                code = exit_code.code or 0
    finally:
        os.chdir(here)
    return code, out.getvalue() + err.getvalue()


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        run(["init", "."], self.root)
        self.write("p.kpart", part(CUBE, {"t": 5}).dumps())
        run(["add", "p.kpart"], self.root)
        run(["commit", "-m", "first"], self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        with open(os.path.join(self.root, name), "wb") as handle:
            handle.write(data)

    def test_a_bad_revision_is_a_message_rather_than_a_traceback(self):
        code, output = run(["show", "HEAD~abc"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("error:", output)
        self.assertNotIn("Traceback", output)

    def test_a_part_that_cannot_be_read_is_reported_by_check(self):
        self.write("broken.kpart", b'{"kerf_part": 1, "parameters": {"a": "b/0"}}')
        run(["add", "broken.kpart"], self.root)
        code, output = run(["check"], self.root)
        self.assertEqual(code, 2)
        self.assertIn("broken.kpart", output)
        self.assertNotIn("Traceback", output)

    def test_a_lattice_size_has_to_be_a_number(self):
        code, output = run(["config", "eval_resolution", "banana"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("whole number", output)
        code, _ = run(["config", "eval_resolution", "48"], self.root)
        self.assertEqual(code, 0)

    def test_merge_refuses_to_write_over_uncommitted_work(self):
        run(["branch", "side"], self.root)
        self.write("p.kpart", part(CUBE, {"t": 9}).dumps())
        run(["add", "p.kpart"], self.root)
        run(["commit", "-m", "second"], self.root)
        run(["checkout", "side"], self.root)

        self.write("p.kpart", part(CUBE, {"t": 3}).dumps())
        code, output = run(["merge", "main"], self.root)
        self.assertEqual(code, 1)
        self.assertIn("p.kpart", output)
        # The local edit is still there, which is the whole point.
        self.assertIn(b'"t": 3', open(os.path.join(self.root, "p.kpart"), "rb").read())

    def test_the_staging_cycle_reports_what_it_did(self):
        self.write("p.kpart", part(CUBE, {"t": 8}).dumps())
        code, output = run(["status"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("p.kpart", output)
        code, output = run(["diff"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("t: 5 -> 8", output)


if __name__ == "__main__":
    unittest.main()
