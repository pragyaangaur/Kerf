# The `.kpart` format

A `.kpart` file is JSON holding a parameter table and an ordered list of features. It exists so that version control has something meaningful to compare and to merge. A mesh records what a part looks like, and a feature tree records why it looks that way.

## The document

```json
{
  "kerf_part": 1,
  "name": "nema17-bracket",
  "units": "mm",
  "parameters": { "plate_t": 7 },
  "features": [ ],
  "meta": { "designer": "dana" }
}
```

| Field | Meaning |
| --- | --- |
| `kerf_part` | format version, required |
| `name` | the part name |
| `units` | display units, `mm` by default |
| `parameters` | named numbers or expressions, which may refer to each other |
| `features` | the feature tree, applied in order |
| `meta` | free form, ignored during evaluation |

## Parameters and expressions

Any numeric field may be a literal or an expression over the parameter table.

```json
"radius": "bolt_d/2",
"center": ["-bolt_pitch/2", 18, "rise - 6"]
```

Expressions are read by walking a parsed syntax tree, so Python's `eval` is never called. A part file is data that arrives from other people, and treating it as code would be a mistake.

These are available inside an expression.

- The operators `+ - * / // % **`, unary minus, and brackets.
- The constants `pi`, `tau`, and `e`.
- The functions `sqrt sin cos tan abs min max round floor ceil atan2 radians degrees hypot pow`.

Anything else raises `ExpressionError`. That includes attribute access, comprehensions, imports, and any name the parameter table does not define.

Arithmetic that cannot produce a number raises the same error rather than a builtin one. Dividing by zero, the square root of a negative number, and a result that overflows a float are all things a parameter table can ask for, and each is a rebuild error that names the equation. An exponent above 1024 is refused instead of computed, because `2**(2**30)` is ordinary arithmetic that would take minutes.

Parameters may refer to other parameters. A definition that never resolves is either circular or points at a name that does not exist, and kerf reports it rather than looping.

Expression dependencies also drive impact analysis. When `bolt_d` changes, kerf reads every expression in the part and names the features that mention it.

## Features

Every feature needs a stable `id`. The id is the merge key, so it is what lets kerf tell the difference between a hole that moved and a hole that was deleted while another one was added. Renaming the human label is cosmetic. Changing the id is not.

```json
{
  "id": "bolt_nw",
  "type": "cylinder",
  "op": "subtract",
  "name": "motor bolt NW",
  "radius": "bolt_d/2",
  "height": 40,
  "axis": "y",
  "center": [-15.5, 18, 34],
  "blend": 0,
  "suppressed": false
}
```

| Field | Meaning |
| --- | --- |
| `id` | stable identity, required and unique |
| `type` | `box`, `cylinder`, `sphere`, or `torus` |
| `op` | `add`, `subtract`, or `intersect` |
| `name` | the label used in diffs and reports |
| `center` | position, at the origin by default |
| `rotate` | degrees about X, then Y, then Z |
| `blend` | fillet radius applied at this feature's boolean |
| `suppressed` | keep the feature in the file and leave it out of evaluation |

Each type has its own fields.

| Type | Fields |
| --- | --- |
| `box` | `size` as `[x, y, z]`, and `round` for the corner radius |
| `cylinder` | `radius`, `height`, and `axis` as `x`, `y`, or `z` |
| `sphere` | `radius` |
| `torus` | `radius` for the ring, and `tube` |

An `axis` outside `x`, `y`, and `z` is refused when the file is read rather than when the field is sampled. A torus always lies in the XY plane, and `rotate` is how you turn it out of that plane.

## Evaluation

Features fold in order into a signed distance field. An `add` is a union, a `subtract` is a difference, and an `intersect` keeps what is inside both. A non zero `blend` makes that boolean smooth, which is how a fillet is expressed. The fillet is real rather than cosmetic, because it changes the measured volume.

The field is sampled on a lattice and turned into triangles with naive surface nets. One vertex goes in every cell where the field changes sign, placed at the mean of the crossings on that cell's edges, and quads are stitched between the four cells that share a crossing edge.

The result is watertight, wound consistently, and facing outward. The test suite checks all three, because a mesh with mixed winding is a mesh nobody can slice. Watertight includes the faces at the very edge of the lattice, which is the boundary case worth stating: the surface can cross between the first two sample layers, and a stitcher that starts one layer in leaves a hole there that is invisible from most angles.

The lattice is sized from a box around every feature that adds material. A rotated feature contributes the box around where it ended up rather than around where it started, since otherwise the part is quietly cut off at the edge of its own sampling volume.

Resolution is a repository setting.

```bash
kerf config eval_resolution 72
```

Higher is slower and more accurate. The default of 56 puts volumes within a few tenths of a percent of analytic.

## Why not just store the mesh

Version control has to answer four questions, and only the tree can answer them.

1. What changed? The answer is `bolt_d: 3.4 → 3.6`, and not 1.2 MB of triangles.
2. What does that affect? The answer is the four features that read `bolt_d`.
3. Can these two edits be combined? They can, when they touch different features.
4. Should they be? Only when the resulting solids do not collide.
