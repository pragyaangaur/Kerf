"""The command line surface.

These tests exist because the rest of the suite never imports the CLI, and a
syntax error there stayed hidden until somebody ran the tool on an older
Python. Importing every module is cheap and catches that class of mistake on
whichever versions the test matrix covers.
"""

import importlib
import pkgutil
import unittest

import kerf


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


if __name__ == "__main__":
    unittest.main()
