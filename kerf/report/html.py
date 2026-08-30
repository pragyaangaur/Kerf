"""Building the HTML review report.

The page is laid out like an engineering drawing's revision block. A title
block sits at the top, and below it one numbered sheet per changed part,
each pairing a live 3D view with the ledger of what changed and by how much.
"""

from __future__ import annotations

import datetime
import html
import json
from typing import Optional

import numpy as np

from ..diff import ModelDiff, human_volume
from .viewer import VIEWER_JS

def e(text) -> str:
    """Escape a value for HTML."""
    return html.escape(str(text))


def _num(v: float, digits: int = 3) -> str:
    """Format a measurement for a table cell."""
    if v is None:
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if abs(v) >= 1e5 or (abs(v) < 1e-3 and v != 0):
        return f"{v:.3e}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _delta_chip(pct: Optional[float]) -> str:
    if pct is None:
        return ""
    cls = "up" if pct > 0 else ("down" if pct < 0 else "flat")
    return f'<span class="chip chip-{cls}">{pct:+.1f}%</span>'


STATUS_LABEL = {
    "added": "new part", "removed": "deleted", "modified": "modified",
    "reexported": "re-export only", "rewritten": "same solid, new tree",
    "unchanged": "unchanged",
    "renamed": "renamed", "renamed+modified": "renamed + modified",
}


# --------------------------------------------------------------- report


def build_report(title: str, subtitle: str, meta: list[tuple[str, str]],
                 diffs: list[ModelDiff], payloads: dict[str, Optional[dict]],
                 units: str = "mm", footer: str = "") -> str:
    changed = [d for d in diffs if d.status != "unchanged"]
    total_added = sum(d.volume.added_volume for d in changed if d.volume)
    total_removed = sum(d.volume.removed_volume for d in changed if d.volume)
    feature_changes = sum(len(d.parametric.features) for d in changed if d.parametric)
    param_changes = sum(
        len(d.parametric.parameters) + len(d.parametric.parameters_added)
        + len(d.parametric.parameters_removed)
        for d in changed if d.parametric
    )

    tiles = [
        ("Parts touched", str(len(changed)), f"of {len(diffs)} tracked"),
        ("Material added", human_volume(total_added, units), "across all parts"),
        ("Material removed", human_volume(total_removed, units), "across all parts"),
        ("Feature edits", str(feature_changes), f"{param_changes} parameter changes"),
    ]

    parts = [_HEAD.replace("{{TITLE}}", e(title)),
             _title_block(title, subtitle, meta),
             _tiles(tiles)]

    if not changed:
        parts.append(
            '<section class="sheet empty"><p class="empty-note">No geometric change between '
            'these revisions. Any byte differences are export noise.</p></section>'
        )

    for i, d in enumerate(changed, start=1):
        parts.append(_sheet(i, d, payloads.get(d.path), units))

    parts.append(_legend())
    parts.append(f'<footer class="doc-footer"><span>{e(footer)}</span>'
                 f'<span class="mono">kerf · geometry-aware version control</span></footer>')
    parts.append(f"<script>{VIEWER_JS}</script>")
    parts.append("</div>")
    return "\n".join(parts)


def _title_block(title: str, subtitle: str, meta: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<div class="tb-cell"><span class="tb-key">{e(k)}</span>'
        f'<span class="tb-val mono">{e(v)}</span></div>'
        for k, v in meta
    )
    return f"""
<header class="title-block">
  <div class="tb-head">
    <div>
      <p class="eyebrow">Revision comparison</p>
      <h1>{e(title)}</h1>
      <p class="lede">{e(subtitle)}</p>
    </div>
    <div class="tb-mark" aria-hidden="true">
      <svg viewBox="0 0 64 64" width="56" height="56">
        <rect x="4" y="4" width="56" height="56" rx="2" fill="none"
              stroke="currentColor" stroke-width="1.5" opacity="0.35"/>
        <path d="M16 46 L16 18 M16 32 L34 18 M16 32 L34 46" fill="none"
              stroke="currentColor" stroke-width="3.5" stroke-linecap="square"/>
        <path d="M44 14 L44 50" stroke="currentColor" stroke-width="1.5"
              stroke-dasharray="3 4" opacity="0.6"/>
      </svg>
    </div>
  </div>
  <div class="tb-grid">{cells}</div>
</header>"""


def _tiles(tiles: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f'<div class="tile"><span class="tile-key">{e(k)}</span>'
        f'<span class="tile-val mono">{e(v)}</span>'
        f'<span class="tile-sub">{e(sub)}</span></div>'
        for k, v, sub in tiles
    )
    return f'<section class="tiles">{cells}</section>'


def _sheet(index: int, d: ModelDiff, payload: Optional[dict], units: str) -> str:
    view_id = f"kerf-data-{index}"
    status = STATUS_LABEL.get(d.status, d.status)
    body = [
        f'<section class="sheet" id="sheet-{index}">',
        '  <div class="sheet-head">',
        f'    <span class="sheet-no mono">{index:02d}</span>',
        '    <div class="sheet-id">',
        f'      <h2>{e(d.path)}</h2>',
        f'      <p class="sheet-sum">{e(d.headline())}</p>',
        '    </div>',
        f'    <span class="status status-{e(d.status.split("+")[0])}">{e(status)}</span>',
        '  </div>',
        '  <div class="sheet-body">',
    ]
    body.append(_viewer_block(view_id, payload, d))
    body.append('    <div class="ledger">')
    body.append(_metrics_table(d, units))
    if d.parametric:
        body.append(_parametric_block(d))
    if d.volume:
        body.append(_volume_block(d, units))
    if d.note:
        body.append(f'      <p class="note">{e(d.note)}</p>')
    body.append("    </div>")
    body.append("  </div>")
    if payload:
        body.append(
            f'  <script type="application/json" id="{view_id}">{json.dumps(payload)}</script>'
        )
    body.append("</section>")
    return "\n".join(body)


def _viewer_block(view_id: str, payload: Optional[dict], d: ModelDiff) -> str:
    if payload is None:
        return ('    <div class="viewer viewer-none"><p>No preview: this format is opaque to '
                'kerf, or the model is too large to draw inline.</p></div>')
    has_diff = bool(payload["groups"].get("added") or payload["groups"].get("removed"))
    modes = [("changes", "Changes"), ("after", "After"), ("before", "Before"), ("ghost", "Ghost")]
    if not has_diff:
        modes = [("after", "Model")]
    buttons = "".join(
        f'<button type="button" data-mode="{m}" aria-pressed="false">{label}</button>'
        for m, label in modes
    )
    return f"""    <figure class="viewer" data-kerf-view="{view_id}">
      <canvas></canvas>
      <div class="viewer-bar">
        <div class="modes">{buttons}</div>
        <button type="button" data-reset class="ghost-btn" title="Reset the view">Recentre</button>
      </div>
      <figcaption class="viewer-hint">Drag to orbit · scroll to zoom · shift-drag to pan</figcaption>
      <p class="viewer-fallback">This browser cannot draw the 3D preview; the measurements
        beside it are unaffected.</p>
    </figure>"""


def _metrics_table(d: ModelDiff, units: str) -> str:
    rows = []
    keys = [("volume", f"Volume ({units}³)"), ("area", f"Surface area ({units}²)"),
            ("triangles", "Triangles"), ("components", "Solid bodies"),
            ("features", "Features"), ("parameters", "Parameters")]
    for key, label in keys:
        a = d.old_stats.get(key)
        b = d.new_stats.get(key)
        if a is None and b is None:
            continue
        pct = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a:
            pct = (b - a) / abs(a) * 100.0
        same = a == b
        rows.append(
            f'<tr class="{"same" if same else ""}"><th>{e(label)}</th>'
            f'<td class="mono">{_num(a) if a is not None else "—"}</td>'
            f'<td class="mono">{_num(b) if b is not None else "—"}</td>'
            f'<td class="mono">{"" if same else _delta_chip(pct)}</td></tr>'
        )

    for key, label in (("size", "Bounding box"), ("centroid", "Centroid")):
        a, b = d.old_stats.get(key), d.new_stats.get(key)
        if a is None and b is None:
            continue
        fmt = lambda v: " × ".join(f"{x:.1f}" for x in v) if v else "—"
        same = a is not None and b is not None and np.allclose(a, b, atol=1e-6)
        rows.append(
            f'<tr class="{"same" if same else ""} row-wide"><th>{e(label)}</th>'
            f'<td class="mono">{fmt(a)}</td><td class="mono">{fmt(b)}</td><td></td></tr>'
        )
    if not rows:
        return ""
    return f"""      <div class="block">
        <h3>Measurements</h3>
        <div class="scroll"><table class="metrics">
          <thead><tr><th></th><th>Before</th><th>After</th><th>Δ</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table></div>
      </div>"""


def _parametric_block(d: ModelDiff) -> str:
    p = d.parametric
    if p is None or p.empty():
        return ""
    out = ['      <div class="block"><h3>Feature tree</h3>']

    if p.parameters or p.parameters_added or p.parameters_removed:
        rows = []
        for c in p.parameters:
            rows.append(
                f'<tr><th class="mono">{e(c.key)}</th>'
                f'<td class="mono">{e(c.old)}</td><td class="mono">{e(c.new)}</td>'
                f'<td>{_delta_chip(c.pct)}</td></tr>'
            )
            impact = p.impact.get(c.key, [])
            if impact:
                more = f" +{len(impact) - 3} more" if len(impact) > 3 else ""
                rows.append(
                    f'<tr class="impact-row"><td colspan="4">drives '
                    f'{e(", ".join(impact[:3]))}{e(more)}</td></tr>'
                )
        for k, v in p.parameters_added.items():
            rows.append(f'<tr><th class="mono">{e(k)}</th><td>—</td>'
                        f'<td class="mono">{e(v)}</td><td><span class="chip chip-new">new</span></td></tr>')
        for k, v in p.parameters_removed.items():
            rows.append(f'<tr><th class="mono">{e(k)}</th><td class="mono">{e(v)}</td>'
                        f'<td>—</td><td><span class="chip chip-gone">removed</span></td></tr>')
        out.append('<h4>Parameters</h4><div class="scroll"><table class="params">'
                   '<thead><tr><th></th><th>Before</th><th>After</th><th></th></tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table></div>')

    if p.features:
        items = []
        for f in p.features:
            detail = "".join(f'<li class="mono">{e(c.describe())}</li>' for c in f.changes[:8])
            more = (f'<li class="more">+{len(f.changes) - 8} more fields</li>'
                    if len(f.changes) > 8 else "")
            move = ""
            if f.status == "reordered" and f.old_index is not None and f.new_index is not None:
                move = f'<span class="mono move">#{f.old_index + 1} → #{f.new_index + 1}</span>'
            items.append(
                f'<li class="feat feat-{e(f.status)}">'
                f'<span class="feat-mark" aria-hidden="true"></span>'
                f'<div><p class="feat-head"><span class="feat-name">{e(f.label or f.id)}</span>'
                f'<span class="feat-type mono">{e(f.feature_type)}</span>'
                f'<span class="feat-status">{e(f.status)}</span>{move}</p>'
                + (f'<ul class="feat-fields">{detail}{more}</ul>' if detail else "")
                + "</div></li>"
            )
        out.append(f'<h4>Features</h4><ul class="feats">{"".join(items)}</ul>')

    if p.renamed:
        out.append('<h4>Renamed</h4><ul class="renames">' + "".join(
            f'<li class="mono">{e(old)} → {e(new)}</li>' for _, old, new in p.renamed
        ) + "</ul>")
    out.append("</div>")
    return "\n".join(out)


def _volume_block(d: ModelDiff, units: str) -> str:
    v = d.volume
    if v is None or v.unchanged:
        return ""
    bar = ""
    total = max(v.common_volume + v.added_volume + v.removed_volume, 1e-12)
    widths = [v.common_volume / total * 100, v.added_volume / total * 100,
              v.removed_volume / total * 100]
    bar = (f'<div class="vbar" role="img" aria-label="Proportion of the body unchanged, '
           f'added and removed">'
           f'<span class="vbar-kept" style="width:{widths[0]:.2f}%"></span>'
           f'<span class="vbar-add" style="width:{widths[1]:.2f}%"></span>'
           f'<span class="vbar-rem" style="width:{widths[2]:.2f}%"></span></div>')

    rows = ""
    if v.regions:
        rows = "".join(
            f'<tr><td><span class="dot dot-{r.kind}"></span>{r.kind}</td>'
            f'<td class="mono">{human_volume(r.volume, units)}</td>'
            f'<td class="mono">{", ".join(f"{c:.1f}" for c in r.centroid)}</td>'
            f'<td class="mono">{" × ".join(f"{hi - lo:.1f}" for lo, hi in zip(r.bbox_min, r.bbox_max))}</td>'
            f'</tr>'
            for r in v.regions
        )
        rows = ('<div class="scroll"><table class="regions"><thead><tr><th>Change</th>'
                '<th>Volume</th><th>Centre (x, y, z)</th><th>Extent</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div>')

    moved = ""
    if v.translation:
        mag = float(np.linalg.norm(v.translation))
        moved = (f'<p class="note">The body appears to have moved rather than changed shape: '
                 f'a translation of {mag:.3g} {units} '
                 f'({", ".join(f"{t:+.2f}" for t in v.translation)}).</p>')

    return f"""      <div class="block">
        <h3>Where material changed</h3>
        {bar}
        <p class="vbar-key"><span class="dot dot-kept"></span>unchanged
          {human_volume(v.common_volume, units)}
          <span class="dot dot-added"></span>added {human_volume(v.added_volume, units)}
          <span class="dot dot-removed"></span>removed {human_volume(v.removed_volume, units)}</p>
        {moved}
        {rows}
        <p class="fineprint">Measured on a {v.resolution}³ voxel lattice
          ({v.pitch:.3g} {units} per cell); regions below two cells are treated as noise.</p>
      </div>"""


def _legend() -> str:
    return """
<section class="legend">
  <h3>Reading this report</h3>
  <dl>
    <div><dt>Geometry id</dt><dd>Kerf hashes the solid rather than the file. A re-export
      with reordered facets or a fresh timestamp is reported as unchanged.</dd></div>
    <div><dt>Feature tree</dt><dd>For native <code>.kpart</code> files the comparison runs
      per feature and per parameter, so a change reads as intent instead of as moved
      triangles.</dd></div>
    <div><dt>Volumetric diff</dt><dd>Both revisions are filled onto one shared lattice and
      subtracted. This works for any mesh, including exports from a CAD system kerf cannot
      open.</dd></div>
    <div><dt>Colours</dt><dd><span class="dot dot-added"></span>material present only after,
      <span class="dot dot-removed"></span>material present only before,
      <span class="dot dot-kept"></span>surface common to both.</dd></div>
  </dl>
</section>"""


def now_stamp() -> str:
    """The timestamp printed in the title block."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ CSS

_HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f2f4f0;
  --surface: #ffffff;
  --surface-2: #e9ece7;
  --ink: #141a17;
  --ink-2: #47524c;
  --muted: #6f7b74;
  --rule: #d5dbd4;
  --rule-strong: #b6bfb8;
  --accent: #9a6b1f;
  --accent-soft: #f0e2c6;
  --added: #1c7f59;
  --added-soft: #d9ece3;
  --removed: #b73f2f;
  --removed-soft: #f3ded9;
  --viewer-solid: #a8b0aa;
  --viewer-added: #2a9c6f;
  --viewer-removed: #c9503d;
  --viewer-rim: #ffffff;
  --viewer-grid: #7d867f;
  --display: "Saira Condensed", "Arial Narrow", sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
  --shadow: 0 1px 2px rgba(20, 26, 23, .06), 0 8px 24px -18px rgba(20, 26, 23, .5);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #101311;
    --surface: #181c19;
    --surface-2: #1f2521;
    --ink: #e8ede9;
    --ink-2: #b3bdb6;
    --muted: #8b968e;
    --rule: #2b332d;
    --rule-strong: #3c453e;
    --accent: #d7a94f;
    --accent-soft: #3a2f19;
    --added: #45bd8c;
    --added-soft: #17342a;
    --removed: #e0705a;
    --removed-soft: #3a221d;
    --viewer-solid: #7f8a83;
    --viewer-added: #3fb383;
    --viewer-removed: #d4604a;
    --viewer-rim: #cfe0d6;
    --viewer-grid: #4a544d;
    --shadow: 0 1px 2px rgba(0, 0, 0, .5), 0 12px 30px -20px rgba(0, 0, 0, .9);
  }
}
:root[data-theme="dark"] {
  --ground: #101311; --surface: #181c19; --surface-2: #1f2521;
  --ink: #e8ede9; --ink-2: #b3bdb6; --muted: #8b968e;
  --rule: #2b332d; --rule-strong: #3c453e;
  --accent: #d7a94f; --accent-soft: #3a2f19;
  --added: #45bd8c; --added-soft: #17342a;
  --removed: #e0705a; --removed-soft: #3a221d;
  --viewer-solid: #7f8a83; --viewer-added: #3fb383; --viewer-removed: #d4604a;
  --viewer-rim: #cfe0d6; --viewer-grid: #4a544d;
  --shadow: 0 1px 2px rgba(0,0,0,.5), 0 12px 30px -20px rgba(0,0,0,.9);
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--ground); color: var(--ink);
  font-family: var(--body); font-size: 15px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 40px 24px 72px; display: flex;
        flex-direction: column; gap: 28px; }
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
h1, h2, h3, h4 { font-family: var(--display); margin: 0; text-wrap: balance;
                 letter-spacing: .01em; }
h1 { font-size: clamp(30px, 4.4vw, 44px); font-weight: 700; line-height: 1.05;
     text-transform: uppercase; }
h2 { font-size: 23px; font-weight: 600; }
h3 { font-size: 14px; font-weight: 600; text-transform: uppercase;
     letter-spacing: .13em; color: var(--muted); }
h4 { font-size: 12px; font-weight: 600; text-transform: uppercase;
     letter-spacing: .13em; color: var(--muted); margin-top: 18px; }
p { margin: 0; }
a { color: var(--accent); }

/* --- title block ------------------------------------------------ */
.title-block { border: 1px solid var(--rule-strong); background: var(--surface);
               box-shadow: var(--shadow); }
.tb-head { display: flex; justify-content: space-between; align-items: flex-start;
           gap: 24px; padding: 26px 26px 22px; }
.tb-mark { color: var(--accent); flex: none; }
.eyebrow { font-family: var(--display); text-transform: uppercase; letter-spacing: .22em;
           font-size: 11px; color: var(--accent); font-weight: 600; margin-bottom: 6px; }
.lede { color: var(--ink-2); margin-top: 8px; max-width: 62ch; }
.tb-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           border-top: 1px solid var(--rule-strong); }
.tb-cell { padding: 11px 16px; border-right: 1px solid var(--rule);
           display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.tb-cell:last-child { border-right: 0; }
.tb-key { font-size: 10px; text-transform: uppercase; letter-spacing: .16em;
          color: var(--muted); font-family: var(--display); font-weight: 600; }
.tb-val { font-size: 13px; overflow-wrap: anywhere; }

/* --- tiles ------------------------------------------------------ */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 1px;
         background: var(--rule); border: 1px solid var(--rule); }
.tile { background: var(--surface); padding: 16px 18px; display: flex;
        flex-direction: column; gap: 2px; }
.tile-key { font-size: 10px; text-transform: uppercase; letter-spacing: .16em;
            color: var(--muted); font-family: var(--display); font-weight: 600; }
.tile-val { font-size: 25px; font-weight: 500; line-height: 1.2; }
.tile-sub { font-size: 12px; color: var(--muted); }

/* --- sheets ----------------------------------------------------- */
.sheet { border: 1px solid var(--rule-strong); background: var(--surface);
         box-shadow: var(--shadow); }
.sheet-head { display: flex; gap: 16px; align-items: baseline; padding: 18px 22px;
              border-bottom: 1px solid var(--rule); }
.sheet-no { font-family: var(--display); font-size: 13px; color: var(--accent);
            letter-spacing: .1em; padding-top: 4px; }
.sheet-id { flex: 1; min-width: 0; }
.sheet-id h2 { overflow-wrap: anywhere; }
.sheet-sum { color: var(--ink-2); font-size: 14px; margin-top: 3px; }
.status { font-family: var(--display); font-size: 11px; text-transform: uppercase;
          letter-spacing: .14em; padding: 4px 9px; border: 1px solid var(--rule-strong);
          color: var(--ink-2); white-space: nowrap; }
.status-added { color: var(--added); border-color: var(--added); background: var(--added-soft); }
.status-removed { color: var(--removed); border-color: var(--removed); background: var(--removed-soft); }
.status-reexported, .status-rewritten { color: var(--accent); border-color: var(--accent);
                                        background: var(--accent-soft); }
.sheet-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.12fr); }
@media (max-width: 860px) { .sheet-body { grid-template-columns: 1fr; } }

/* --- viewer ----------------------------------------------------- */
.viewer { margin: 0; position: relative; border-right: 1px solid var(--rule);
          background: linear-gradient(180deg, var(--surface-2), var(--surface));
          display: flex; flex-direction: column; min-height: 420px; }
@media (max-width: 860px) { .viewer { border-right: 0; border-bottom: 1px solid var(--rule); } }
.viewer canvas { flex: 1; width: 100%; height: 100%; min-height: 330px; display: block;
                 cursor: grab; touch-action: none; }
.viewer canvas.grabbing { cursor: grabbing; }
.viewer-bar { display: flex; justify-content: space-between; align-items: center;
              gap: 10px; padding: 8px 12px; border-top: 1px solid var(--rule); flex-wrap: wrap; }
.modes { display: flex; gap: 1px; background: var(--rule); border: 1px solid var(--rule); }
.modes button, .ghost-btn {
  font-family: var(--display); font-size: 11px; text-transform: uppercase;
  letter-spacing: .12em; padding: 6px 11px; border: 0; background: var(--surface);
  color: var(--muted); cursor: pointer; }
.modes button[aria-pressed="true"] { background: var(--accent); color: var(--surface); }
:root[data-theme="dark"] .modes button[aria-pressed="true"],
:root:not([data-theme="light"]) .modes button[aria-pressed="true"] { color: #14170f; }
.ghost-btn { border: 1px solid var(--rule); }
.modes button:hover, .ghost-btn:hover { color: var(--ink); }
.modes button:focus-visible, .ghost-btn:focus-visible,
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.viewer-hint { font-size: 11px; color: var(--muted); padding: 0 12px 10px;
               font-family: var(--mono); }
.viewer-fallback, .viewer-none p { display: none; font-size: 13px; color: var(--muted);
                                   padding: 24px; }
.viewer-unsupported canvas, .viewer-unsupported .viewer-bar,
.viewer-unsupported .viewer-hint { display: none; }
.viewer-unsupported .viewer-fallback { display: block; }
.viewer-none { align-items: center; justify-content: center; }
.viewer-none p { display: block; text-align: center; max-width: 34ch; }

/* --- ledger ----------------------------------------------------- */
.ledger { padding: 20px 22px 24px; display: flex; flex-direction: column; gap: 22px;
          min-width: 0; }
.block { display: flex; flex-direction: column; gap: 10px; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
tbody tr.row-wide td { white-space: normal; }
tr.impact-row td { text-align: left; font-size: 11px; color: var(--muted);
                   padding: 0 0 7px; border-bottom: 1px solid var(--rule);
                   white-space: normal; }
thead th { font-family: var(--display); font-size: 10px; text-transform: uppercase;
           letter-spacing: .14em; color: var(--muted); text-align: right;
           padding: 0 0 6px; font-weight: 600; border-bottom: 1px solid var(--rule); }
thead th:first-child { text-align: left; }
tbody th { text-align: left; font-weight: 500; color: var(--ink-2); padding: 6px 12px 6px 0;
           border-bottom: 1px solid var(--rule); white-space: nowrap; }
tbody td { text-align: right; padding: 6px 0 6px 12px; border-bottom: 1px solid var(--rule);
           white-space: nowrap; }
tbody tr.same th, tbody tr.same td { color: var(--muted); }
tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
.chip { font-family: var(--mono); font-size: 11px; padding: 1px 6px; border-radius: 2px;
        margin-left: 6px; }
.chip-up { background: var(--added-soft); color: var(--added); }
.chip-down { background: var(--removed-soft); color: var(--removed); }
.chip-flat { background: var(--surface-2); color: var(--muted); }
.chip-new { background: var(--added-soft); color: var(--added); }
.chip-gone { background: var(--removed-soft); color: var(--removed); }

/* --- features --------------------------------------------------- */
.feats { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.feat { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--rule); }
.feat:last-child { border-bottom: 0; }
.feat-mark { width: 3px; flex: none; background: var(--rule-strong); margin-top: 3px;
             border-radius: 2px; }
.feat-added .feat-mark { background: var(--added); }
.feat-removed .feat-mark { background: var(--removed); }
.feat-modified .feat-mark { background: var(--accent); }
.feat-head { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.feat-name { font-weight: 600; }
.feat-type { font-size: 11px; color: var(--muted); }
.feat-status { font-family: var(--display); font-size: 10px; text-transform: uppercase;
               letter-spacing: .13em; color: var(--muted); }
.feat-added .feat-status { color: var(--added); }
.feat-removed .feat-status { color: var(--removed); }
.feat-modified .feat-status { color: var(--accent); }
.move { font-size: 11px; color: var(--muted); }
.feat-fields { list-style: none; margin: 5px 0 0; padding: 0; display: flex;
               flex-direction: column; gap: 2px; font-size: 12.5px; color: var(--ink-2); }
.feat-fields li::before { content: "· "; color: var(--muted); }
.more { color: var(--muted); font-style: italic; }
.renames { list-style: none; margin: 0; padding: 0; font-size: 13px; color: var(--ink-2); }

/* --- volume ----------------------------------------------------- */
.vbar { display: flex; height: 10px; background: var(--surface-2);
        border: 1px solid var(--rule); overflow: hidden; }
.vbar span { display: block; height: 100%; }
.vbar-kept { background: var(--muted); opacity: .55; }
.vbar-add { background: var(--added); }
.vbar-rem { background: var(--removed); }
.vbar-key { font-size: 12px; color: var(--muted); display: flex; flex-wrap: wrap;
            gap: 4px 14px; align-items: center; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
       margin-right: 5px; vertical-align: baseline; }
.dot-kept { background: var(--rule-strong); }
.dot-added, .dot-add { background: var(--added); }
.dot-removed, .dot-rem { background: var(--removed); }
.regions td:first-child { text-align: left; text-transform: capitalize; }
.fineprint, .note { font-size: 12px; color: var(--muted); }
.note { border-left: 2px solid var(--accent); padding-left: 10px; }
.empty { padding: 40px 24px; }
.empty-note { color: var(--muted); text-align: center; }

/* --- legend / footer -------------------------------------------- */
.legend { border-top: 1px solid var(--rule-strong); padding-top: 20px;
          display: flex; flex-direction: column; gap: 12px; }
.legend dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
             gap: 16px 26px; margin: 0; }
.legend dt { font-family: var(--display); font-size: 12px; text-transform: uppercase;
             letter-spacing: .12em; color: var(--ink); margin-bottom: 3px; }
.legend dd { margin: 0; font-size: 13px; color: var(--muted); }
.legend code { font-family: var(--mono); font-size: 12px; }
.doc-footer { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;
              font-size: 11px; color: var(--muted); border-top: 1px solid var(--rule);
              padding-top: 14px; letter-spacing: .04em; }
@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>
<div class="wrap">"""
