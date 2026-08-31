"""The commands behind each subcommand."""

from __future__ import annotations

import os
import sys
import textwrap

from .. import diff as diff_module
from .. import merge as merge_module
from .. import report as report_module
from ..model import format_name
from ..objects import Tree
from ..repo import Repo, RepoError, find_repo
from .style import blue, bold, brass, die, dim, fmt_state, green, red, stamp, yellow
from .style import USE_COLOR


# Settings the rest of kerf reads as a lattice size. Storing text in one of
# these breaks the next command to evaluate a part, a long way from here.
NUMERIC_CONFIG = {"eval_resolution", "diff_resolution"}


def status_word(style, word: str, width: int = 9) -> str:
    """A status word, padded and then coloured, in that order.

    Escape codes are characters as far as a format specifier is concerned, so
    padding a string that has already been coloured pads it to the wrong width
    and the column stops lining up.
    """
    return style(f"{word:>{width}}")


def open_repo(args) -> Repo:
    """Find the repository the command should act on."""
    return Repo(find_repo(getattr(args, "repo", None) or "."))


def cmd_init(args) -> None:
    root = os.path.abspath(args.path)
    os.makedirs(root, exist_ok=True)
    repo = Repo.init(root, args.author)
    print(f"initialised an empty kerf repository in {bold(os.path.join(root, '.kerf'))}")
    print(dim(f"  author: {repo.author}   branch: main"))
    print(dim("  next: kerf add <part> && kerf commit -m \"first revision\""))


def cmd_add(args) -> None:
    repo = open_repo(args)
    try:
        staged = repo.add(args.paths, force=args.force)
    except RepoError as exc:
        die(str(exc))
        return
    for entry in staged:
        note = ""
        if entry.kind in ("mesh", "parametric") and entry.gid:
            note = dim(f"  geometry {entry.gid[:10]}")
        print(f"  {green('staged')} {entry.path}{note}")
    if not staged:
        print(dim("nothing to stage"))


def cmd_unstage(args) -> None:
    repo = open_repo(args)
    repo.unstage(args.paths)
    for p in args.paths:
        print(f"  {yellow('unstaged')} {p}")


def cmd_status(args) -> None:
    repo = open_repo(args)
    branch = repo.current_branch() or f"detached at {(repo.head_commit() or '')[:10]}"
    head = repo.head_commit()
    print(f"on branch {bold(branch)}" + (dim(f"  ({head[:10]})") if head else dim("  (no commits yet)")))

    locks = repo.locks()
    if locks:
        print()
        print(bold("locked parts"))
        for path, info in sorted(locks.items()):
            who = info["owner"]
            mark = green("you") if who == repo.author else red(who)
            reason = f", {info['reason']}" if info.get("reason") else ""
            print(f"  {'🔒' if USE_COLOR else '[L]'} {path} {dim('held by')} {mark}{dim(reason)}")

    staged, unstaged = repo.status()
    if staged:
        print()
        print(bold("staged for the next revision"))
        for entry in staged:
            detail = dim(f"  {entry.detail}") if entry.detail else ""
            print(f"  {fmt_state(entry.state)}  {entry.path}{detail}")
    if unstaged:
        print()
        print(bold("changed in the working tree"))
        for entry in unstaged:
            detail = dim(f"  {entry.detail}") if entry.detail else ""
            print(f"  {fmt_state(entry.state)}  {entry.path}{detail}")
    if not staged and not unstaged:
        print()
        print(dim("working tree clean"))


def cmd_commit(args) -> None:
    repo = open_repo(args)
    try:
        oid = repo.commit(args.message, author=args.author, allow_empty=args.allow_empty)
    except RepoError as exc:
        die(str(exc))
        return
    commit = repo.commit_obj(oid)
    tree = repo.tree_obj(commit.tree)
    print(f"[{repo.current_branch() or 'detached'} {bold(oid[:10])}] {commit.short()}")
    print(dim(f"  {len(tree.entries)} files tracked · {stamp(commit.timestamp)} · {commit.author}"))


def cmd_log(args) -> None:
    repo = open_repo(args)
    start = repo.resolve(args.rev) if args.rev else None
    history = repo.history(start, args.limit)
    if not history:
        print(dim("no commits yet"))
        return
    heads = {}
    for name, oid in repo.branches().items():
        heads.setdefault(oid, []).append(name)
    head = repo.head_commit()
    for oid, commit in history:
        marks = ""
        names = heads.get(oid, [])
        if oid == head:
            names = ["HEAD"] + names
        if names:
            marks = "  " + brass("(" + ", ".join(names) + ")")
        merge = dim(" merge") if len(commit.parents) > 1 else ""
        print(f"{brass(oid[:10])}{marks}{merge}  {bold(commit.short())}")
        print(dim(f"    {commit.author} · {stamp(commit.timestamp)}"))
        if args.stat:
            parent = commit.parents[0] if commit.parents else None
            old_tree = repo.tree_obj(repo.commit_obj(parent).tree) if parent else Tree()
            diffs = diff_module.diff_trees(repo, old_tree, repo.tree_obj(commit.tree),
                                        volumetric=False)
            for d in diffs:
                print(f"    {fmt_state(d.status)}  {d.path}  {dim(d.headline())}")
        rest = commit.message.split("\n", 1)[1].strip() if "\n" in commit.message else ""
        if rest:
            for line in rest.splitlines():
                print(dim(f"    {line}"))


def _resolve_pair(repo: Repo, args) -> tuple[Tree, Tree, str, str]:
    """Work out which two trees to compare.

    With no revisions this compares what is staged against what is on disk,
    which is the change somebody just made and the one they usually want to
    see. Passing --staged compares HEAD against the staging area instead.
    """
    if args.rev_b:
        a, b = repo.resolve(args.rev_a), repo.resolve(args.rev_b)
        return repo.commit_tree(a), repo.commit_tree(b), a[:10], b[:10]
    if args.rev_a:
        a = repo.resolve(args.rev_a)
        return repo.commit_tree(a), repo.worktree_tree(), a[:10], "working tree"
    if getattr(args, "staged", False):
        head = repo.head_commit()
        old = repo.commit_tree(head) if head else Tree()
        return old, Tree(entries=repo.read_index()), (head[:10] if head else "empty"), "index"
    return (
        Tree(entries=repo.read_index()), repo.worktree_tree(), "index", "working tree",
    )


def cmd_diff(args) -> None:
    repo = open_repo(args)
    old, new, label_a, label_b = _resolve_pair(repo, args)
    diffs = diff_module.diff_trees(repo, old, new, resolution=args.resolution,
                                volumetric=not args.fast, paths=args.paths or None)
    changed = [d for d in diffs if d.status != "unchanged"]
    print(f"{bold('comparing')} {brass(label_a)} {dim('→')} {brass(label_b)}")
    if not changed:
        print(dim("  no changes"))
        return
    for d in changed:
        print()
        print(f"{fmt_state(d.status)}  {bold(d.path)}  {dim(format_name(d.path))}")
        if d.old_path:
            print(f"            {dim('was ' + d.old_path)}")
        print(f"            {d.headline()}")
        _print_detail(d, indent=" " * 12, verbose=args.verbose)


def _print_detail(d: diff_module.ModelDiff, indent: str, verbose: bool) -> None:
    for m in d.metrics:
        if m.key in ("volume", "area") or verbose:
            pct = f" ({m.pct:+.1f}%)" if m.pct is not None else ""
            print(f"{indent}{dim(m.key + ':')} {m.old:,.4g} → {m.new:,.4g}{pct}")

    p = d.parametric
    if p and not p.empty():
        for ch in p.parameters:
            impact = p.impact.get(ch.key, [])
            # Say how many were left out. A parameter that drives four holes
            # and one that drives fourteen otherwise print the same line.
            extra = f" +{len(impact) - 3} more" if len(impact) > 3 else ""
            tail = dim(f"   drives {', '.join(impact[:3])}{extra}") if impact else ""
            print(f"{indent}{yellow('param')} {ch.describe()}{tail}")
        for k, v in p.parameters_added.items():
            print(f"{indent}{green('param')} {k} = {v}  {dim('(new)')}")
        for k, v in p.parameters_removed.items():
            print(f"{indent}{red('param')} {k}  {dim('(removed)')}")
        for f in p.features:
            style = {"added": green, "removed": red}.get(f.status, yellow)
            print(f"{indent}{style(f.status)} {bold(f.label or f.id)} {dim(f.feature_type)}")
            for ch in f.changes[: (None if verbose else 4)]:
                print(f"{indent}    {dim(ch.describe())}")
        for _, old_name, new_name in p.renamed:
            print(f"{indent}{blue('renamed')} {old_name} → {new_name}")

    v = d.volume
    if v and not v.unchanged:
        if v.translation:
            mag = sum(t * t for t in v.translation) ** 0.5
            print(f"{indent}{dim('moved:')} {mag:.3g} mm "
                  f"({', '.join(f'{t:+.2f}' for t in v.translation)})")
        for r in v.regions[: (None if verbose else 4)]:
            style = green if r.kind == "added" else red
            centre = ", ".join(f"{x:.1f}" for x in r.centroid)
            print(f"{indent}{style(r.kind):>8} {diff_module.human_volume(r.volume, ascii_only=True)} "
                  f"{dim('at (' + centre + ')')}")
    if d.note:
        print(f"{indent}{dim(d.note)}")


def cmd_show(args) -> None:
    repo = open_repo(args)
    oid = repo.resolve(args.rev)
    commit = repo.commit_obj(oid)
    print(f"{brass('revision')} {bold(oid)}")
    print(f"{dim('author  ')} {commit.author}")
    print(f"{dim('date    ')} {stamp(commit.timestamp)}")
    if commit.parents:
        print(f"{dim('parents ')} {', '.join(p[:10] for p in commit.parents)}")
    for k, v in commit.meta.items():
        print(f"{dim(k.ljust(8))} {v}")
    print()
    for line in commit.message.splitlines():
        print(f"    {line}")
    print()
    parent = commit.parents[0] if commit.parents else None
    old = repo.commit_tree(parent) if parent else Tree()
    diffs = diff_module.diff_trees(repo, old, repo.tree_obj(commit.tree),
                                resolution=args.resolution, volumetric=not args.fast)
    for d in diffs:
        print(f"{fmt_state(d.status)}  {d.path}  {dim(d.headline())}")
        if args.verbose:
            _print_detail(d, indent=" " * 12, verbose=True)


def cmd_ls(args) -> None:
    repo = open_repo(args)
    tree = repo.commit_tree(args.rev) if args.rev else Tree(entries=repo.read_index())
    if not tree.entries:
        print(dim("nothing tracked"))
        return
    width = max(len(p) for p in tree.entries)
    for path in tree.paths():
        entry = tree.entries[path]
        size = f"{entry.size / 1024:.1f} KiB" if entry.size >= 1024 else f"{entry.size} B"
        gid = entry.gid[:10] if entry.gid else dim("—")
        print(f"  {path.ljust(width)}  {dim(entry.kind.ljust(10))} {size:>10}  {dim('geom')} {gid}")


def cmd_cat(args) -> None:
    repo = open_repo(args)
    rev, _, path = args.target.partition(":")
    if not path:
        die("expected <rev>:<path>")
    tree = repo.commit_tree(rev)
    entry = tree.entries.get(path)
    if entry is None:
        die(f"{path} does not exist at {rev}")
        return
    data = repo.store.get_typed(entry.oid, "blob")
    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(data)
        print(f"wrote {len(data)} bytes to {args.out}")
    else:
        sys.stdout.buffer.write(data)


def cmd_branch(args) -> None:
    repo = open_repo(args)
    if args.delete:
        repo.delete_branch(args.delete)
        print(f"deleted branch {args.delete}")
        return
    if args.name:
        oid = repo.create_branch(args.name, repo.resolve(args.start) if args.start else None)
        print(f"created branch {bold(args.name)} at {brass(oid[:10])}")
        return
    current = repo.current_branch()
    for name, oid in sorted(repo.branches().items()):
        mark = green("* ") if name == current else "  "
        commit = repo.commit_obj(oid)
        print(f"{mark}{name.ljust(18)} {brass(oid[:10])}  {dim(commit.short())}")


def cmd_checkout(args) -> None:
    repo = open_repo(args)
    if args.create:
        repo.create_branch(args.rev)
    try:
        oid = repo.checkout(args.rev, force=args.force)
    except RepoError as exc:
        die(str(exc))
        return
    where = repo.current_branch() or f"detached at {oid[:10]}"
    print(f"switched to {bold(where)} {dim(oid[:10])}")


def cmd_restore(args) -> None:
    repo = open_repo(args)
    done = repo.restore(args.rev, args.paths)
    for path in done:
        print(f"  {blue('restored')} {path} {dim('from ' + args.rev)}")


def cmd_merge(args) -> None:
    repo = open_repo(args)
    head = repo.head_commit()
    if head is None:
        die("nothing to merge into")
        return
    other = repo.resolve(args.branch)

    if other in repo.ancestors(head):
        print(dim(f"{args.branch} is already merged"))
        return

    # A merge writes over the working tree, both when it fast-forwards and
    # when it lands a merged part. Anything uncommitted in a file the merge
    # touches would go without a word, so it is checked before anything is
    # written rather than after.
    _, working = repo.status()
    dirty = sorted(entry.path for entry in working if entry.state != "untracked")
    if dirty:
        listed = ", ".join(dirty[:4]) + (f" and {len(dirty) - 4} more" if len(dirty) > 4 else "")
        die(f"commit or restore your changes before merging: {listed}")
        return

    base = repo.merge_base(head, other)
    if base == head:
        ref = repo.head_ref()
        if ref:
            repo.write_ref(ref, other)          # move this branch, stay on it
        else:
            repo.set_head_detached(other)
        repo.checkout(other, force=True)
        if ref:
            repo.set_head_to_branch(ref.rsplit("/", 1)[-1])
        print(f"fast-forwarded {bold(repo.current_branch() or 'HEAD')} to {brass(other[:10])}")
        return

    base_tree = repo.commit_tree(base) if base else Tree()
    result = merge_module.merge_trees(
        repo, base_tree, repo.commit_tree(head), repo.commit_tree(other),
        check_interference=not args.no_interference,
        check_equations=not args.no_equation_check,
    )

    print(f"{bold('merging')} {brass(args.branch)} into "
          f"{brass(repo.current_branch() or head[:10])}")
    print(dim(f"  common ancestor: {base[:10] if base else 'none'}"))
    print()

    for f in result.files:
        if f.status in ("unchanged", "ours"):
            continue
        style = {"merged": green, "theirs": blue, "added": green,
                 "removed": red, "conflict": red}.get(f.status, dim)
        print(f"  {style(f.status.rjust(9))}  {f.path}")
        for note in f.notes:
            print(f"             {dim(note)}")
        for conflict in f.conflicts:
            # These sentences are the most useful thing kerf prints, and they
            # run long. Wrapping them under a hanging indent keeps them
            # readable instead of letting the terminal fold them at column one.
            lines = textwrap.wrap(conflict.describe(), width=68) or [""]
            print(f"             {red('conflict:')} {lines[0]}")
            for line in lines[1:]:
                print(f"                       {line}")

    if result.conflicts:
        interference = [c for c in result.conflicts if c.scope == "interference"]
        equations = [c for c in result.conflicts if c.scope == "equation"]
        print()
        print(red(f"{len(result.conflicts)} conflict(s), nothing was committed"))
        if interference:
            print(yellow("  note: the feature trees merged cleanly but the geometry collides"))
        if equations:
            print(yellow("  note: both branches build on their own, and the merged part "
                         "would not rebuild"))
        _write_conflict_sides(repo, result)
        raise SystemExit(2)

    written = 0
    index = repo.read_index()
    for f in result.files:
        if f.status in ("unchanged", "ours"):
            continue
        full = os.path.join(repo.root, f.path)
        if f.status == "removed":
            if os.path.exists(full):
                os.remove(full)
            index.pop(f.path, None)
            continue
        if f.data is None:
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(f.data)
        index[f.path] = repo.stage_entry(f.path)
        written += 1
    repo.write_index(index)

    message = args.message or f"merge {args.branch} into {repo.current_branch() or 'HEAD'}"
    oid = repo.commit(message, parents=[head, other], allow_empty=True,
                      meta={"merge": f"{head[:10]}+{other[:10]}"})
    print()
    print(f"{green('merged cleanly')} into {bold(oid[:10])} ({written} files written)")


def _write_conflict_sides(repo: Repo, result: merge_module.MergeResult) -> None:
    for f in result.files:
        if f.status != "conflict" or not (f.ours_data or f.theirs_data):
            continue
        for suffix, data in (("ours", f.ours_data), ("theirs", f.theirs_data)):
            if data is None:
                continue
            stem, ext = os.path.splitext(f.path)
            out = os.path.join(repo.root, f"{stem}.{suffix}{ext}")
            with open(out, "wb") as fh:
                fh.write(data)
            print(dim(f"             wrote {os.path.relpath(out, repo.root)}"))


def cmd_lock(args) -> None:
    repo = open_repo(args)
    try:
        info = repo.lock(args.path, args.reason)
    except RepoError as exc:
        die(str(exc))
        return
    print(f"{green('locked')} {args.path} for {info['owner']}")
    if args.reason:
        print(dim(f"  reason: {args.reason}"))


def cmd_unlock(args) -> None:
    repo = open_repo(args)
    try:
        repo.unlock(args.path, force=args.force)
    except RepoError as exc:
        die(str(exc))
        return
    print(f"{yellow('unlocked')} {args.path}")


def cmd_locks(args) -> None:
    repo = open_repo(args)
    locks = repo.locks()
    if not locks:
        print(dim("no locks held"))
        return
    for path, info in sorted(locks.items()):
        who = green(info["owner"] + " (you)") if info["owner"] == repo.author else red(info["owner"])
        print(f"  {path}  {dim('held by')} {who}  {dim(stamp(info['since']))}")
        if info.get("reason"):
            print(f"      {dim(info['reason'])}")


def cmd_report(args) -> None:
    repo = open_repo(args)
    old, new, label_a, label_b = _resolve_pair(repo, args)
    diffs = diff_module.diff_trees(repo, old, new, resolution=args.resolution,
                                paths=args.paths or None)
    payloads: dict = {}
    for d in diffs:
        if d.status == "unchanged":
            continue
        old_model = diff_module.model_from_entry(repo, d.path, old.entries.get(d.old_path or d.path))
        new_model = diff_module.model_from_entry(repo, d.path, new.entries.get(d.path))
        payloads[d.path] = report_module.viewer_payload(
            old_model.mesh if old_model else None,
            new_model.mesh if new_model else None, args.resolution
        )

    head = repo.head_commit()
    meta = [
        ("Repository", os.path.basename(repo.root)),
        ("Branch", repo.current_branch() or "detached"),
        ("Before", label_a),
        ("After", label_b),
        ("Author", repo.author),
        ("Generated", report_module.now_stamp()),
    ]
    subtitle = args.subtitle or _report_subtitle(repo, label_a, label_b)
    html_doc = report_module.build_report(
        args.title or f"{os.path.basename(repo.root)} · {repo.current_branch() or 'detached'}",
        subtitle, meta, diffs, payloads,
        footer=f"{len([d for d in diffs if d.status != 'unchanged'])} parts changed",
    )
    out = args.out or os.path.join(repo.root, "kerf-report.html")
    with open(out, "w") as fh:
        fh.write(html_doc)
    size = os.path.getsize(out) / 1024
    print(f"wrote {bold(out)} {dim(f'({size:.0f} KiB)')}")


def _report_subtitle(repo: Repo, a: str, b: str) -> str:
    try:
        commit = repo.commit_obj(repo.resolve(b))
        return commit.short()
    except Exception:                                # noqa: BLE001
        return f"Geometry comparison between {a} and {b}"


def cmd_view(args) -> None:
    """Render one model.

    Pointing this at a loose file is a reasonable thing to do from anywhere,
    so a repository is only required when the target names a revision.
    """
    from .. import model as model_module

    repo = None
    if ":" in args.target:
        repo = open_repo(args)
        rev, _, path = args.target.partition(":")
        model = repo.model_at(rev, path)
        title = f"{path} at {rev}"
    else:
        if not os.path.isfile(args.target):
            die(f"no such file: {args.target}")
            return
        try:
            repo = open_repo(args)
        except RepoError:
            repo = None
        resolution = repo.config.get("eval_resolution", 56) if repo else 56
        model = model_module.load_file(args.target, resolution)
        title = args.target
    if model.mesh is None:
        die(f"cannot render {args.target}: {model.error or 'unsupported format'}")
        return
    model_diff = diff_module.ModelDiff(path=title, status="added", kind=model.kind,
                           new_stats=model.stats(), size_new=len(model.data))
    payload = report_module.viewer_payload(None, model.mesh, args.resolution)
    html_doc = report_module.build_report(
        os.path.basename(title), "Single revision preview",
        [("Model", os.path.basename(title)), ("Format", format_name(title)),
         ("Author", repo.author if repo else "—"),
         ("Generated", report_module.now_stamp())],
        [model_diff], {title: payload}, footer="single model preview",
    )
    out = args.out or "kerf-view.html"
    with open(out, "w") as fh:
        fh.write(html_doc)
    print(f"wrote {bold(out)}")


def _load_part(repo, target: str):
    """Read a part from the working tree or from a revision, as <rev>:<path>."""
    from ..parametric import Part

    if ":" in target:
        rev, _, path = target.partition(":")
        model = repo.model_at(rev, path)
        if model.part is None:
            die(f"{path} at {rev} is not a kerf part file")
        return model.part, f"{path} at {rev}"
    with open(target, "rb") as handle:
        data = handle.read()
    try:
        return Part.loads(data), target
    except Exception as error:               # noqa: BLE001
        die(f"cannot read {target}: {error}")
        return None, target


def cmd_equations(args) -> None:
    repo = open_repo(args)
    from ..parametric import build_graph, check_equations, format_graph

    part, label = _load_part(repo, args.target)
    graph = build_graph(part)
    counts = f"{len(graph.parameters)} parameters, {len(graph.fields)} driven dimensions"
    print(f"{bold(label)}  {dim(counts)}")
    print()

    issues = check_equations(part)
    values = {}
    if not issues:
        values = part.resolved_parameters()

    # The equations line up in one column and what they drive in another, so
    # the shape of the model is readable down the page.
    rows = []
    for line in format_graph(graph, values):
        name, _, rest = line.partition(" = ")
        expression, _, drives = rest.partition("   drives ")
        rows.append((name, expression.rstrip(), drives))
    width = max((len(f"{name} = {expression}") for name, expression, _ in rows), default=0)
    for name, expression, drives in rows:
        head = f"{name} = {expression}"
        text = f"  {brass(name)} = {expression}"
        if drives:
            text += " " * (width - len(head) + 3) + dim(f"drives {drives}")
        print(text)

    if args.explain:
        target = args.explain
        if target not in graph.parameters:
            die(f"{target} is not a parameter of this part")
        print()
        print(f"{bold(target)} is read by:")
        readers = graph.readers_of(target)
        for reader in readers:
            print(f"    {reader}")
        features = graph.feature_readers_of(target)
        if features:
            print(f"  and reaches {len(features)} feature(s): {', '.join(features)}")
        depends = graph.upstream(target)
        if depends:
            print(f"  it depends on: {', '.join(sorted(depends))}")

    if issues:
        print()
        for issue in issues:
            style = red if issue.severity == "error" else yellow
            print(f"  {style(issue.severity)}  {issue.describe()}")
        raise SystemExit(2)


def cmd_check(args) -> None:
    repo = open_repo(args)
    from ..model import classify
    from ..parametric import Part, check_part, sweep_all

    tree = repo.commit_tree(args.rev) if args.rev else None
    paths = []
    if tree is not None:
        paths = [p for p in tree.paths() if classify(p) == "parametric"]
    else:
        paths = [p for p in repo.read_index() if classify(p) == "parametric"]

    if not paths:
        print(dim("no part files tracked"))
        return

    failed = False
    for path in paths:
        try:
            if tree is not None:
                data = repo.store.get_typed(tree.entries[path].oid, "blob")
            else:
                with open(os.path.join(repo.root, path), "rb") as handle:
                    data = handle.read()
            part = Part.loads(data)
        except Exception as error:                   # noqa: BLE001
            # A part that will not even load is the loudest failure there is,
            # and `kerf check` is exactly where it should be reported.
            print(f"  {status_word(red, 'broken')}  {path}")
            print(f"                      {red('cannot be read: ' + str(error))}")
            failed = True
            continue

        issues = check_part(part, resolution=args.resolution)
        errors = [i for i in issues if i.severity == "error"]
        style, word = (
            (red, "broken") if errors else ((yellow, "warning") if issues else (green, "builds"))
        )
        print(f"  {status_word(style, word)}  {path}")
        for issue in issues:
            style = red if issue.severity == "error" else yellow
            print(f"                      {style(issue.describe())}")
        failed = failed or bool(errors)

        if args.sweep and not errors:
            for result in sweep_all(part, spread=args.spread, steps=args.steps,
                                    resolution=args.resolution):
                if result.robust() and not result.warnings():
                    continue
                print(f"                      {yellow('range')} {result.summary()}")
    if failed:
        raise SystemExit(2)


def cmd_sweep(args) -> None:
    repo = open_repo(args)
    from ..parametric import default_range, sweep_parameter

    part, label = _load_part(repo, args.target)
    if args.parameter not in part.parameters:
        die(f"{args.parameter} is not a parameter of {label}")

    raw = part.parameters[args.parameter]
    if args.start is None or args.stop is None:
        if not isinstance(raw, (int, float)):
            die(f"{args.parameter} is an expression, so give --from and --to")
        low, high = default_range(float(raw), args.spread)
        start = args.start if args.start is not None else low
        stop = args.stop if args.stop is not None else high
    else:
        start, stop = args.start, args.stop

    result = sweep_parameter(part, args.parameter, start, stop, args.steps, args.resolution)
    print(f"{bold(label)}  {dim(f'driving {args.parameter} from {start:g} to {stop:g}')}")
    print()
    for row in result.volume_bars():
        value, _, rest = row.partition("  ")
        style = red if "fails" in rest else dim
        print(f"  {brass(value)}  {style(rest)}")
    print()
    if result.robust() and not result.warnings():
        print(f"  {green('holds')} {result.summary()}")
    else:
        print(f"  {yellow('note')}  {result.summary()}")
        for point in result.failures():
            print(f"        {red(f'{point.value:g}')}  {point.reason}")
        for point in result.warnings():
            detail = next(
                (i.message for i in point.issues if i.severity == "warning"), ""
            )
            print(f"        {yellow(f'{point.value:g}')}  {detail}")


def cmd_stats(args) -> None:
    repo = open_repo(args)
    s = repo.stats()
    rows = [
        ("commits", s["commits"]), ("branches", s["branches"]),
        ("tracked files", s["tracked_files"]), ("objects", s["objects"]),
        ("store size", f"{s['store_bytes'] / 1024:.1f} KiB"),
        ("working tree", f"{s['worktree_bytes'] / 1024:.1f} KiB"),
        ("locks", s["locks"]),
    ]
    for key, value in rows:
        print(f"  {dim(key.ljust(16))} {value}")
    if s["worktree_bytes"]:
        ratio = s["store_bytes"] / s["worktree_bytes"]
        print(f"  {dim('store / worktree'.ljust(16))} {ratio:.2f}×")


def cmd_config(args) -> None:
    repo = open_repo(args)
    if args.key is None:
        for k, v in sorted(repo.config.items()):
            print(f"  {dim(k.ljust(18))} {v}")
        return
    if args.value is None:
        print(repo.config.get(args.key, ""))
        return
    value: object = args.value
    if args.key in NUMERIC_CONFIG:
        try:
            value = int(args.value)
        except ValueError:
            die(f"{args.key} has to be a whole number, not {args.value!r}")
            return
        if value < 4:
            die(f"{args.key} has to be at least 4")
            return
    elif args.value.lstrip("-").isdigit():
        value = int(args.value)
    repo.set_config(args.key, value)
    print(f"{args.key} = {value}")


def cmd_export(args) -> None:
    repo = open_repo(args)
    count = repo.export(args.rev, args.dest)
    print(f"exported {count} files from {args.rev} to {args.dest}")


def cmd_demo(args) -> None:
    from ..demo import build_demo

    root = os.path.abspath(args.path)
    build_demo(root, quiet=args.quiet)


