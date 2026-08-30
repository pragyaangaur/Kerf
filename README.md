# Kerf

**Version control that understands geometry.**

[Open the playground](https://pragyaangaur.github.io/Kerf/) to try it in your browser. Nothing is uploaded and nothing is precomputed. The geometry kernel, the diff, and the merge all run on your machine.

Git tracks bytes. A CAD file is bytes that mean something, and the gap between those two facts breaks the workflow in four places.

| What happens | What git reports | What actually happened |
| --- | --- | --- |
| You re-export an untouched part | 4 MB changed | nothing changed |
| You open a hole from 8 mm to 10 mm | 4 MB changed | one parameter moved, and four features followed it |
| Two people edit one part | conflict, resolve by hand | no line based merge can reconcile two edits to a solid |
| Somebody reviews the change | binary files differ | the reviewer needs to see where material moved |

Fixing this is not a matter of adding version history, because every CAD system already has version history. Four operations have to be redefined in the terms the domain uses: identity, diff, merge, and review. Kerf is a working prototype of all four.

## Try it without installing anything

The [playground](https://pragyaangaur.github.io/Kerf/) has three things to do.

1. **Edit and compare.** Drag a parameter and watch the diff appear. New material turns green, material that went away turns red, and the panel names the parameter that moved along with the features it drives.
2. **Equations.** Rewrite any equation and the part rebuilds. Point one at a name that does not exist and kerf reports it the way a rebuild error would. Then drive a parameter across a range and the chart shows the volume it produces and the values where the part stops building.
3. **Merge two branches.** Pick what two people did to the same bracket and merge them. Some pairs combine cleanly. One pair collides in space, and another renames a parameter the other branch depends on, so the merged part would not rebuild.
4. **The re-export problem.** Export the same part twice and compare the answers. A byte comparison reports most of the file as changed. Kerf reports no design change, and shows the largest distance any vertex moved.

## Install the command line tool

Kerf needs Python 3.10 or newer and NumPy. There are no other dependencies.

```bash
git clone https://github.com/pragyaangaur/Kerf.git
cd Kerf
pip install -e .
kerf --help
```

Build the worked example, which is a motor bracket going through a week of revisions.

```bash
kerf demo my-demo
cd my-demo
kerf log --stat
```

## What it does that git cannot

### It knows a re-export is not a change

Every CAD system writes a different byte stream each time you export. Facet order shuffles, the header carries a timestamp, and floats wobble in the last digit. Kerf hashes the canonical form of the solid instead, so triangle order, vertex numbering, and float noise below the tolerance all wash out.

```
$ kerf status

on branch main  (cd138012ca)

changed in the working tree
  re-export  parts/idler-housing.stl
             bytes differ, geometry identical
```

Exact fingerprints catch a deterministic exporter. When floats have genuinely drifted, a tolerance comparison pairs vertices with a spatial hash and reports the true worst case deviation. Pairing never uses sort order, because CAD meshes are full of exactly coincident coordinates that any ordering key reshuffles under the very noise this is meant to see through.

### It diffs intent rather than triangles

For native `.kpart` files the comparison runs per parameter and per feature. Expression dependencies give impact analysis at no extra cost, so changing one number names the features that follow it.

```
$ kerf diff HEAD~2 HEAD~1

   modified  parts/bracket.kpart  Kerf part
             bolt_d: 3.4 -> 3.6 (+5.9%), plate_t: 5 -> 7 (+40.0%); 1 added; +9.02 cm³
             param bolt_d: 3.4 -> 3.6 (+5.9%)
                   drives motor bolt NW, motor bolt NE, motor bolt SW +1 more
             param plate_t: 5 -> 7 (+40.0%)   drives base plate
             added corner gusset box
                added 9.02 cm³ at (0.0, 0.3, 10.0)
```

### It measures where material moved, in any format

Feature level diffing needs a native format. The volumetric diff does not, and it works on anything that tessellates, including an export from a CAD system kerf cannot open. Both revisions are filled onto one shared lattice and subtracted, and the changed cells are grouped into regions with a volume, a centre, and an extent.

A region that is nowhere thicker than one lattice cell is measurement noise rather than material, which is exactly what re-tessellation looks like. Kerf counts those cells separately and leaves them out of the reported change, so the number stays honest.

### It treats equations as part of the model

A dimension in CAD is rarely a number. It is a rule such as `bolt_d/2`, and that rule is the design intent the author wrote down. Kerf reads those expressions to build geometry, so the graph they form is available for free, and three things follow from it.

A change to an equation is a different event from a change to a value. Moving a dimension from 15.5 to `bolt_pitch/2` can leave the geometry byte for byte identical and still be one of the more significant edits somebody can make, because it turns a measurement into a rule. Kerf reports that as `rule added` and says the number did not move.

```
$ kerf equations parts/bracket.kpart

parts/bracket.kpart  8 parameters, 32 driven dimensions

  bolt_d = 3.6      drives motor bolt NW, motor bolt NE, motor bolt SW and 1 more
  bolt_pitch = 31   drives motor bolt NW, motor bolt NE, motor bolt SW and 1 more
  bore_d = 22       drives motor bore
  plate_t = 7       drives base plate
```

Every guide to parametric CAD says to drive each variable across its expected range and check the model still rebuilds, because equations that hold at the nominal value often fail at the extremes. Doing that by hand means typing a number, waiting for a rebuild, and reading the tree, over and over. Kerf evaluates a part in a few milliseconds, so it can do the sweep and report the range the model survives.

```
$ kerf sweep parts/bracket.kpart plate_w --from 8 --to 110 --steps 9

          8  ###  8,045 mm3
       20.8  #####  14,039 mm3
       33.5  ########  21,101 mm3
       46.2  ##########  28,109 mm3
         59  #############  35,260 mm3
       71.8  ################  42,835 mm3
       84.5  ##################  50,149 mm3
       97.2  #####################  57,891 mm3
        110  ########################  65,487 mm3

  note  plate_w builds across 8 to 110, and at 8 the part has fallen into 2 separate bodies
```

`kerf check --sweep` runs that over every parameter of every tracked part, which turns a chore nobody does into something continuous integration can fail on.

### It blocks merges that would not rebuild

One person renames `bolt_pitch` to `hole_pitch`. Another adds a hole positioned at `bolt_pitch/2`. Both branches build. The merged part references a name that no longer exists, and the person who finds out is whoever opens the file next.

```
$ kerf merge tidy-names

   conflict  parts/bracket.kpart
             conflict: equation bolt_e.center.x: reads 'bolt_pitch', which the
                       parameter table does not define. Both branches build on
                       their own, and the merged part would not rebuild.

1 conflict(s), nothing was committed
  note: both branches build on their own, and the merged part would not rebuild
```

No amount of care on either branch prevents this, because the merge creates the failure. Only something that evaluates the merged model can see it.

### It blocks merges that collide in space

Kerf merges feature by feature and parameter by parameter. It then does something no text merge can do, which is to evaluate the merged solid and check whether the two sides' additions occupy the same space.

```
$ kerf merge cable-tie

merging cable-tie into main

   conflict  parts/bracket.kpart
             feature cable tie slot added from theirs
             conflict: chassis slot R / cable tie slot: both branches cut material
                       here, and the two pockets break into one another over 252 mm³

1 conflict(s), nothing was committed
  note: the feature trees merged cleanly but the geometry collides
```

That merge is clean as text. It is also wrong, and kerf is the only part of the toolchain in a position to notice.

### It has locks, because some files genuinely cannot be merged

A `.sldprt` is opaque. Two edits to it cannot be reconciled by any tool, so kerf does not pretend otherwise. It versions the file, refuses to merge it automatically, and offers the workflow that works for a binary part.

```bash
kerf lock parts/housing.sldprt -r "adding the mounting boss"
```

### It renders the review

`kerf report` writes a self contained HTML page with a WebGL viewer. Added material is green, material that went away is red, and the measurements sit beside the model.

```bash
kerf report HEAD~2 HEAD -o review.html
```

## Commands

| Command | What it does |
| --- | --- |
| `init` `add` `unstage` `commit` | the staging cycle |
| `status` | geometry aware, and it separates a real edit from a re-export |
| `log [--stat]` `show` `ls` `cat` | history and inspection |
| `diff [a] [b] [-v]` | semantic comparison in the terminal |
| `report [a] [b] -o out.html` | visual comparison with a 3D viewer |
| `view <file>` | render one model to HTML |
| `branch` `checkout` `restore` | branching |
| `merge <branch>` | feature level merge, gated on the merged part being valid |
| `equations <part>` | the equations that drive a part, and what each one reaches |
| `sweep <part> <parameter>` | drive one parameter and find where the part breaks |
| `check [--sweep]` | confirm every tracked part still builds |
| `lock` `unlock` `locks` | claim parts that cannot be merged |
| `export` `stats` `config` | housekeeping |

## The `.kpart` format

A parameter table and an ordered feature tree, evaluated to geometry through signed distance fields. Every feature carries a stable `id`, which is what makes a three way merge possible. The full description is in [docs/kpart-format.md](docs/kpart-format.md).

```json
{
  "kerf_part": 1,
  "name": "nema17-bracket",
  "units": "mm",
  "parameters": { "plate_t": 7, "bolt_d": 3.6, "bolt_pitch": 31 },
  "features": [
    { "id": "base", "type": "box", "op": "add", "name": "base plate",
      "size": [60, 46, "plate_t"], "center": [0, 0, "plate_t/2"], "round": 2 },
    { "id": "bolt_a", "type": "cylinder", "op": "subtract", "name": "motor bolt NW",
      "radius": "bolt_d/2", "height": 40, "axis": "y",
      "center": ["-bolt_pitch/2", 18, "rise - 6 + bolt_pitch/2"] }
  ]
}
```

## How the code is laid out

```
kerf/
  objects/      content addressed store, and the three object types
  geometry/     meshes, fingerprinting, tolerance equivalence, voxel grids
  parametric/   expressions, features, distance fields, surface nets, parts,
                the equation graph, model validity, parameter sweeps
  formats/      STL and OBJ
  diff/         identity, then feature trees, then volume
  merge/        three way merge, plus the gates that check the merged result
  repo/         refs, staging, status, history, locks
  report/       the HTML review page and its viewer
  cli/          the command line

web/            the playground, which runs the same algorithms in JavaScript
  engine/       expressions, distance fields, tessellation, diff, merge
  viewer/       a WebGL renderer with no dependencies
  ui/           the three tabs
```

The Python engine and the JavaScript engine are separate implementations of the same design. They agree on volumes to the last digit the tessellation can support, which is checked by hand rather than by a shared test suite.

## Running the tests

```bash
python -m pytest tests -q
```

There are 110 tests covering the geometry kernel, the fingerprint invariances, the expression sandbox, the equation graph, model validity, parameter sweeps, diffing, merging, and the repository.

## What this is not

Kerf is a prototype built to prove the model. It is not a production tool, and the honest limits are these.

- **There is no B-rep.** Real CAD is NURBS surfaces and topology. Kerf works on meshes and on its own distance field trees. The concepts carry over to a B-rep kernel and the implementations do not.
- **Tessellation is approximate.** Surface nets on a lattice put volumes within a few tenths of a percent of analytic, which is fine for review and wrong for inspection.
- **The volumetric diff is bound by its resolution.** The default is a 56 cell lattice across the longest axis. Changes thinner than one cell are reported as noise, and `--resolution` raises that when you need it.
- **A genuine re-mesh reads as a change.** Tolerance equivalence only recognises the same tessellation with moved coordinates. Seeing through a re-mesh needs a surface distance measure, and guessing would be worse than saying so.
- **Native CAD formats are opaque.** STEP, SolidWorks, and Fusion files are versioned and lockable without being understood. STEP is the realistic first one to parse.
- **There is no server.** Repositories are local, so there is no push, no pull, and no way to arbitrate a lock between two people.

## Is any of this new

[docs/novelty.md](docs/novelty.md) is an honest answer rather than a pitch. Most of kerf is not new. Onshape already branches and merges CAD properly, visual comparison is table stakes, and content addressed storage of binaries is a solved problem.

One thing does appear to be new. Every other tool ends a merge when the two sides stop disagreeing. Kerf then builds the result and asks whether it is valid, and refuses the merge when the answer is no. That is the whole argument, and the same document sets out where the moat could be and what would sink the idea.

## Deploying the playground

The playground is plain static files under `web/`, so any host that serves a directory will do. GitHub Pages works in either of its two modes.

Building from a branch needs no setup. Jekyll is switched off by the `.nojekyll` file, the files under `web/` are served as they are, and the `index.html` at the repository root redirects there.

Building from GitHub Actions gives a cleaner URL, because the workflow uploads `web/` as the site root. It needs Pages set to that mode once, under Settings, then Pages, then Build and deployment. The workflow token is not allowed to change that setting on its own.

## Licence

MIT. See [LICENSE](LICENSE).
