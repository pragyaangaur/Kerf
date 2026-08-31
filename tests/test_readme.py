"""Claims the README makes that the code can check for itself.

The README quotes a test count and lists every command. Both are the kind of
thing that goes stale quietly: the git history already carries two commits
whose whole job was correcting that number after it drifted. A number nobody
checks is worse than no number, so these check it.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()


def collected_tests() -> int:
    """How many tests there actually are, counted the way pytest counts."""
    import unittest as ut

    loader = ut.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))

    def walk(item):
        if isinstance(item, ut.TestSuite):
            return sum(walk(child) for child in item)
        return 1

    return walk(suite)


class TestReadmeStaysTrue(unittest.TestCase):
    def test_the_quoted_test_count_is_the_real_one(self):
        quoted = re.search(r"There are (\d+) tests covering", README)
        self.assertIsNotNone(quoted, "the README should say how many tests there are")
        self.assertEqual(
            int(quoted.group(1)), collected_tests(),
            "the README quotes a test count that is no longer right; update the "
            "sentence rather than deleting this test",
        )

    def test_every_command_in_the_table_exists(self):
        from kerf.cli import build_parser

        table = re.search(
            r"\| Command \| What it does \|\n\|[^\n]*\|\n((?:\|[^\n]*\|\n)+)", README
        )
        self.assertIsNotNone(table, "the README should carry a command table")

        listed: set[str] = set()
        for row in table.group(1).strip().splitlines():
            first_cell = row.split("|")[1]
            for name in re.findall(r"`([a-z-]+)", first_cell):
                listed.add(name)

        real = set(build_parser()._subparsers._group_actions[0].choices)
        self.assertEqual(
            listed - real, set(), "the README lists commands that do not exist"
        )
        # demo is deliberately absent from the table, since it has its own
        # section further up the page.
        self.assertEqual(
            real - listed - {"demo"}, set(),
            "there are commands the README's table does not mention",
        )


if __name__ == "__main__":                           # pragma: no cover
    unittest.main()
