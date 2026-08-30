"""Colour and formatting for terminal output.

Colour is switched off when output is piped or when NO_COLOR is set, so the
same commands can be read by a person and by a script.
"""

from __future__ import annotations

import datetime
import sys

USE_COLOR = not bool(__import__("os").environ.get("NO_COLOR")) and sys.stdout.isatty()


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def bold(text: str) -> str:
    return paint(text, "1")


def dim(text: str) -> str:
    return paint(text, "2")


def green(text: str) -> str:
    return paint(text, "32")


def red(text: str) -> str:
    return paint(text, "31")


def yellow(text: str) -> str:
    return paint(text, "33")


def blue(text: str) -> str:
    return paint(text, "36")


def brass(text: str) -> str:
    return paint(text, "33")


STATE_STYLE = {
    "added": (green, "new"),
    "removed": (red, "deleted"),
    "modified": (yellow, "modified"),
    "reexported": (blue, "re-export"),
    "rewritten": (blue, "rewritten"),
    "renamed": (blue, "renamed"),
    "renamed+modified": (yellow, "renamed*"),
    "untracked": (dim, "untracked"),
    "unchanged": (dim, "unchanged"),
}


def fmt_state(state: str) -> str:
    style, label = STATE_STYLE.get(state, (dim, state))
    return style(f"{label:>10}")


def stamp(timestamp: int) -> str:
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def die(message: str) -> None:
    print(red("error: ") + message, file=sys.stderr)
    raise SystemExit(1)
