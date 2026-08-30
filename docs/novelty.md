# What kerf does that other tools do not

This is a check on the idea rather than a pitch for it. Each capability is listed with whoever already does it, and the ones where the honest answer is "this already exists" are listed first so they are not quietly skipped.

The short version is that most of kerf is not new. One thing is, and it is worth naming precisely: **kerf refuses a merge because the merged part would not build.** Every other tool answers the question "did these two people disagree". Kerf also answers "is the thing you would get actually valid", and that second question is where the whole argument sits.

## The scorecard

| Capability | Who already does it | Verdict |
| --- | --- | --- |
| Version history for CAD | Every PDM system, Onshape, GrabCAD, git plus LFS | Not new |
| Branch and merge for CAD | Onshape, natively and well | Not new |
| Visual comparison of two revisions | Onshape compare, CoLab, several PDM viewers | Not new |
| Feature level merge | Onshape, inside its own database | Not new, but only there |
| Identity based on the shape rather than the file | Nothing found | New for file based work |
| Telling a value change from an equation change | Nothing found | New |
| Refusing a merge whose result self-interferes | Nothing found | New |
| Refusing a merge whose equations would not resolve | Nothing found | New |
| Sweeping a parameter to find where a model breaks | Design study tools do the sweep for other reasons | Partly new |

## Where kerf is not new, and it matters

**Onshape has already solved branch and merge for CAD.** It branches without check-out locks, merges at feature level, and shows a visual comparison. It identifies conflicts at the feature level before merging and refuses to touch features that conflict. Anybody claiming that branching CAD is an unsolved problem has not looked at Onshape.

There are two real differences, and neither is a technical breakthrough. Onshape's merge lives inside Onshape's database, so it does not help a team whose parts are files on disk, which is still most teams. And Onshape's merge answers whether the two branches disagreed, which is not the same question as whether the merged model is any good.

**Visual diff is table stakes.** Kerf's report is nicer than some and it is not a differentiator.

**Storage is solved.** Content addressed storage of large binaries is what Git LFS, DVC, and every PDM vault already do.

## The one thing that is actually new

A merge in any other tool ends when the two sides stop disagreeing. Kerf adds a second step, which is to build the thing the merge produced and ask whether it is valid.

Two gates exist today.

**Geometry.** Two people add features on separate branches. Neither edit touches the other's fields, so every text level and feature level merge succeeds. The merged part has a cable tie slot cutting through a chassis mount slot. Kerf evaluates the merged solid, finds the overlap, and reports the volume the two features share.

**Equations.** One person renames `bolt_pitch` to `hole_pitch`. The other adds a hole positioned at `bolt_pitch/2`. Both branches build. The merged part references a name that no longer exists, which is a rebuild error waiting for whoever opens the file next. Kerf resolves the merged equation graph and refuses.

The second case is the sharper one, because no amount of care on either branch prevents it. The failure is created by the merge, and only something that evaluates the merge can see it.

This is not a new idea in general. Continuous integration has run tests on merge results for twenty years, and electronics has run design rule checks for longer. What appears to be missing is anyone applying it to mechanical CAD, where the equivalent checks exist as separate downstream review steps. Clash detection happens in a weekly coordination meeting. Rebuild errors are found when somebody opens the file. Both are the same class of problem caught days late.

## Equations, and why they are the better half of this

CAD equations are the part of the model that carries intent. A dimension of 15.5 says nothing. A dimension of `bolt_pitch/2` says that this hole is meant to follow the bolt pattern, and it will keep following it when somebody changes the pattern. Every CAD system supports this, and every guide recommends it.

Version control has never engaged with that layer. Kerf reads it already, so three things fall out.

**A parameter change and an equation change are different events.** Changing a dimension from 15.5 to `bolt_pitch/2` may produce the exact same geometry, and it is still one of the more significant edits somebody can make, because it converts a measurement into a rule. Kerf reports it as `rule added`, with a note that the number did not move. A byte comparison sees a changed file, a visual comparison sees nothing at all, and neither is useful.

**Impact is computable.** When `bolt_pitch` changes, the features that read it are known from the expressions, so the diff can name them without anyone maintaining a list.

**A model can be tested like software.** Every guide to parametric CAD gives the same advice, which is to drive each variable across its expected range and confirm the model still rebuilds, because equations that hold at the nominal value often fail at the extremes. Almost nobody does it, because by hand it means typing a number, waiting for a rebuild, and reading the tree, over and over.

Kerf evaluates a part in a few milliseconds, so `kerf sweep` does that automatically and reports the range the model actually survives. On the sample bracket it finds that the part falls into two separate bodies once the plate is narrow enough, and on the spacer it finds the value where the bore swallows the tube. Both are real defects that sit in a model until somebody happens to type the wrong number.

Design study and optimisation tools already sweep parameters, and they do it to find a best value under a goal. Sweeping to find the range where the model stays valid, and storing that as a property of the part that version control can check on every change, is a different use of the same mechanism.

## What is not a moat

Being honest about this matters more than the list above.

**The geometry kernel is a toy.** Distance fields and surface nets against Parasolid or ACIS is not a contest. Anyone serious would license a kernel, and that removes any advantage in the geometry itself.

**The file format is a liability rather than an asset.** A format nobody else writes is a format nobody can adopt. It exists here to prove that feature level operations work, and betting on it would be a mistake.

**The command line interface is copyable in a week.**

**The interference check is not hard to implement.** Sampling two features for overlap is a first year exercise. The reason nobody has it is that nobody wired it into a merge, and that is a product decision rather than a technical barrier.

## What could become a moat

**The rule library.** Two gates exist here. A real version of this has many: tolerance stack-up violations, wall thickness below what the process can make, draft angles, fastener clearance, features that fall outside the stock, mass and centre of gravity budgets. That library is the same kind of asset a design rule check library is in electronics, and it takes years and real customers to build. A competitor can copy two gates in a month and cannot copy fifty.

**Being where the files are.** Onshape's answer requires moving the whole company into Onshape. A tool that sits on the files a team already has, offline, in their own repository, reaches teams that will never migrate. That is positioning rather than technology, and it is defensible for as long as CAD stays fragmented.

**The review habit.** If a team's merges start going through kerf, the accumulated history of what was checked and what was refused becomes the record of the design. That is a switching cost.

## The one sentence

Kerf is the only version control that refuses a merge because the merged part would not build.

## What would sink it

**Onshape adding validity gates.** They have the kernel, the merge, and the customers. Adding a clash and rebuild check on merge is a quarter of work for them, and it would remove the only genuinely new claim here.

**The format problem.** Kerf cannot read a STEP file, a SolidWorks part, or a Fusion document. Until it can, it is a demonstration rather than a tool, and every conversation ends the same way. Parsing STEP is the single highest value thing left to do, because the identity check, the volumetric comparison, and the interference gate all work on any solid, and only the feature level merge needs the native format.

**The honest possibility that teams do not want this.** Mechanical engineers did not ask for merge gates. They asked for their files to stop being overwritten. A tool that blocks merges may read as an obstacle rather than a safeguard, and the answer to that is a default that warns rather than refuses, which is a setting kerf does not yet have.
