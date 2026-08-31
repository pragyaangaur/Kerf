"""Colour and formatting for terminal output.

Colour is switched off when output is piped or when NO_COLOR is set, so the
same commands can be read by a person and by a script. FORCE_COLOR turns it
back on, which is what you want when piping into a pager that understands it.

Padding belongs inside the colour call, never outside it. Escape codes are
characters as far as a format specifier is concerned, so padding a coloured
string pads it to the wrong width and the column stops lining up.
"""

from __future__ import annotations

import datetime
import os
import sys


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


USE_COLOR = _use_color()


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


# Object ids and branch names, which read better in the same warm tone as a
# warning without meaning the same thing.
brass = yellow


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
