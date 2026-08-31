"""Syntax that only a newer Python than kerf supports.

pyproject says Python 3.10 and up. Nothing in the test suite notices when a
module uses syntax older versions cannot parse, because the tests run on
whatever interpreter is to hand and a module nothing imports is never parsed
at all.

Compiling every module catches it, which is why CI does that, but only on the
versions CI runs. This catches the one class of mistake that is easy to make
and invisible on a modern interpreter: PEP 701 f-strings, which arrived in
3.12 and let a replacement field reuse the quote around it or hold a
backslash. Both are a syntax error on 3.10 and 3.11.

ast.parse(feature_version=(3, 10)) does not help here. That flag gates a few
grammar features and does not put the old f-string tokeniser back, so a file
using PEP 701 parses cleanly under it and then fails on the real interpreter.

The scan itself only runs on 3.12 and later, because reading the inside of an
f-string needs the tokeniser that shipped with PEP 701. That is not a gap.
Older interpreters refuse the file outright, so on the versions where this
matters most the interpreter is the check, and this exists to catch the
mistake on the machine somebody is actually writing the code on.
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import sys
import token
import tokenize
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRIPLES = ('"""', "'''")

# The oldest version pyproject promises to run on. PEP 701 landed in 3.12.
OLDEST = (3, 10)

# Before 3.12 the tokeniser hands back a whole f-string as one STRING token,
# so there is nothing to look inside.
HAS_FSTRING_TOKENS = sys.version_info >= (3, 12)


def sources() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for folder in ("kerf", "tests"):
        found.extend(sorted((ROOT / folder).rglob("*.py")))
    return found


def _quote_of(literal: str) -> str:
    """The delimiter a string or f-string token opens with."""
    body = literal.lstrip("fFrRbBuU")
    return body[:3] if body[:3] in TRIPLES else body[:1]


def _closes_one(quote: str, open_quotes: list[str]) -> bool:
    """Would this delimiter end an f-string we are currently inside?

    A single quote inside a triple quoted f-string is harmless. A single quote
    inside a single quoted one ends it, which is the case PEP 701 made legal
    and older versions do not.
    """
    return any(quote.startswith(outer) for outer in open_quotes)


def pep701_uses(path: pathlib.Path) -> list[tuple[int, str]]:
    """Places in one file that need Python 3.12 to parse."""
    found: list[tuple[int, str]] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(path.read_text()).readline))
    except (tokenize.TokenError, SyntaxError) as error:   # pragma: no cover
        return [(0, f"cannot be tokenised: {error}")]

    open_quotes: list[str] = []
    for item in tokens:
        name = token.tok_name[item.type]
        if name == "FSTRING_START":
            quote = _quote_of(item.string)
            if _closes_one(quote, open_quotes):
                found.append((item.start[0], "an f-string reuses a quote of the one around it"))
            open_quotes.append(quote)
            continue
        if name == "FSTRING_END":
            if open_quotes:
                open_quotes.pop()
            continue
        if not open_quotes:
            continue
        # Everything from here down is inside a replacement field.
        if name == "STRING" and _closes_one(_quote_of(item.string), open_quotes):
            found.append((item.start[0], "a string inside an f-string reuses its quote"))
        if name != "FSTRING_MIDDLE" and "\\" in item.string:
            found.append((item.start[0], "a backslash inside an f-string replacement field"))
    return found


@unittest.skipUnless(
    HAS_FSTRING_TOKENS,
    "this scan needs the 3.12 tokeniser; on older versions the interpreter "
    "refuses the file itself, which is a better check than this one",
)
class TestOlderPythonCanParseEverything(unittest.TestCase):
    def test_no_module_needs_a_newer_f_string_than_we_support(self):
        offences = []
        for path in sources():
            for line, why in pep701_uses(path):
                offences.append(f"{path.relative_to(ROOT)}:{line}  {why}")
        self.assertEqual(
            offences, [],
            "these need Python 3.12, and pyproject promises "
            f"{OLDEST[0]}.{OLDEST[1]}",
        )

    def test_the_check_finds_what_it_is_looking_for(self):
        """A test that never fails is worth nothing, so prove this one can."""
        sample = ROOT / "tests" / "_pep701_sample.txt"
        sample.write_text('x = f"{ f\'{"inner":>4}\' }"\n')
        try:
            self.assertTrue(pep701_uses(sample))
        finally:
            os.remove(sample)


class TestSupportedVersions(unittest.TestCase):
    def test_the_promised_version_matches_what_ci_runs(self):
        pyproject = (ROOT / "pyproject.toml").read_text()
        declared = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', pyproject)
        self.assertIsNotNone(declared, "pyproject should pin a minimum Python")
        self.assertEqual(
            (int(declared.group(1)), int(declared.group(2))), OLDEST,
        )

        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text()
        versions = re.findall(r'"(\d+\.\d+)"', workflow)
        oldest = f"{OLDEST[0]}.{OLDEST[1]}"
        self.assertIn(
            oldest, versions,
            "the oldest supported Python has to be in the test matrix, "
            "because nothing else will notice when it stops working",
        )


if __name__ == "__main__":                           # pragma: no cover
    unittest.main()
