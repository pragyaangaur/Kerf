"""The argument parser and the entry point."""

from __future__ import annotations

import argparse
from typing import Optional

from ..repo import RepoError
from . import commands
from .style import die


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kerf",
        description="kerf, version control that understands geometry",
    )
    p.add_argument("--repo", help="path inside the repository (default: cwd)")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, help_text, **kw):
        sp = sub.add_parser(name, help=help_text, description=help_text, **kw)
        sp.set_defaults(func=fn)
        return sp

    sp = add("init", commands.cmd_init, "create a repository")
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--author")

    sp = add("add", commands.cmd_add, "stage parts for the next revision")
    sp.add_argument("paths", nargs="+")
    sp.add_argument("--force", "-f", action="store_true", help="stage even if someone holds a lock")

    sp = add("unstage", commands.cmd_unstage, "remove paths from the staging area")
    sp.add_argument("paths", nargs="+")

    add("status", commands.cmd_status, "what has changed, geometrically")

    sp = add("commit", commands.cmd_commit, "record a revision")
    sp.add_argument("-m", "--message", required=True)
    sp.add_argument("--author")
    sp.add_argument("--allow-empty", action="store_true")

    sp = add("log", commands.cmd_log, "revision history")
    sp.add_argument("rev", nargs="?")
    sp.add_argument("-n", "--limit", type=int, default=20)
    sp.add_argument("--stat", action="store_true", help="summarise each revision's changes")

    sp = add("diff", commands.cmd_diff, "compare two revisions geometrically")
    sp.add_argument("rev_a", nargs="?")
    sp.add_argument("rev_b", nargs="?")
    sp.add_argument("--staged", action="store_true",
                    help="compare HEAD against the staging area instead of the working tree")
    sp.add_argument("--paths", nargs="*", help="limit to these paths")
    sp.add_argument("--resolution", type=int, default=56, help="voxel resolution for the diff")
    sp.add_argument("--fast", action="store_true", help="skip the volumetric pass")
    sp.add_argument("-v", "--verbose", action="store_true")

    sp = add("show", commands.cmd_show, "show one revision")
    sp.add_argument("rev", nargs="?", default="HEAD")
    sp.add_argument("--resolution", type=int, default=56)
    sp.add_argument("--fast", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true")

    sp = add("ls", commands.cmd_ls, "list tracked parts")
    sp.add_argument("rev", nargs="?")

    sp = add("cat", commands.cmd_cat, "print a file from a revision (<rev>:<path>)")
    sp.add_argument("target")
    sp.add_argument("-o", "--out")

    sp = add("branch", commands.cmd_branch, "list or create branches")
    sp.add_argument("name", nargs="?")
    sp.add_argument("start", nargs="?")
    sp.add_argument("-d", "--delete")

    sp = add("checkout", commands.cmd_checkout, "switch revisions")
    sp.add_argument("rev")
    sp.add_argument("-b", "--create", action="store_true", help="create the branch first")
    sp.add_argument("--force", "-f", action="store_true")

    sp = add("restore", commands.cmd_restore, "restore paths from a revision")
    sp.add_argument("rev")
    sp.add_argument("paths", nargs="+")

    sp = add("merge", commands.cmd_merge, "merge a branch, feature by feature")
    sp.add_argument("branch")
    sp.add_argument("-m", "--message")
    sp.add_argument("--no-interference", action="store_true",
                    help="skip the geometric interference check")
    sp.add_argument("--no-equation-check", action="store_true",
                    help="skip the check that the merged part still rebuilds")

    sp = add("equations", commands.cmd_equations, "show the equations that drive a part")
    sp.add_argument("target", help="a part file, or <rev>:<path>")
    sp.add_argument("--explain", help="show everything one parameter reaches")

    sp = add("check", commands.cmd_check, "check that every part still builds")
    sp.add_argument("rev", nargs="?")
    sp.add_argument("--sweep", action="store_true",
                    help="also drive each parameter across its range")
    sp.add_argument("--steps", type=int, default=7)
    sp.add_argument("--spread", type=float, default=0.6)
    sp.add_argument("--resolution", type=int, default=24)

    sp = add("sweep", commands.cmd_sweep, "drive one parameter and see where the part breaks")
    sp.add_argument("target", help="a part file, or <rev>:<path>")
    sp.add_argument("parameter")
    sp.add_argument("--from", dest="start", type=float)
    sp.add_argument("--to", dest="stop", type=float)
    sp.add_argument("--steps", type=int, default=11)
    sp.add_argument("--spread", type=float, default=0.6)
    sp.add_argument("--resolution", type=int, default=28)

    sp = add("lock", commands.cmd_lock, "claim a part nobody can merge for you")
    sp.add_argument("path")
    sp.add_argument("-r", "--reason", default="")

    sp = add("unlock", commands.cmd_unlock, "release a lock")
    sp.add_argument("path")
    sp.add_argument("--force", "-f", action="store_true")

    add("locks", commands.cmd_locks, "who holds what")

    sp = add("report", commands.cmd_report, "write a visual diff report")
    sp.add_argument("rev_a", nargs="?")
    sp.add_argument("rev_b", nargs="?")
    sp.add_argument("--staged", action="store_true",
                    help="compare HEAD against the staging area instead of the working tree")
    sp.add_argument("-o", "--out")
    sp.add_argument("--paths", nargs="*")
    sp.add_argument("--title")
    sp.add_argument("--subtitle")
    sp.add_argument("--resolution", type=int, default=56)

    sp = add("view", commands.cmd_view, "render one model to an HTML page")
    sp.add_argument("target", help="a file path, or <rev>:<path>")
    sp.add_argument("-o", "--out")
    sp.add_argument("--resolution", type=int, default=56)

    add("stats", commands.cmd_stats, "repository size and shape")

    sp = add("config", commands.cmd_config, "read or write repository config")
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")

    sp = add("export", commands.cmd_export, "write a revision to a directory")
    sp.add_argument("rev")
    sp.add_argument("dest")

    sp = add("demo", commands.cmd_demo, "build a worked example repository")
    sp.add_argument("path", nargs="?", default="demo-repo")
    sp.add_argument("--quiet", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except RepoError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
