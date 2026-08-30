# Where else a version control service is the right answer

Kerf started from one observation. Git is a general content tracker that happens to be excellent at one specific content type, which is line oriented text written by people who agree on where the lines are. Every other domain gets the general part and loses the specific part.

Reading across domains, the pattern behind a version control product for a specialised field is worth stating precisely. Almost every serious tool already keeps history, so history is not the gap. The gap is that four operations have to be redefined in the terms the domain uses.

| Operation | Git's answer | What the domain needs |
| --- | --- | --- |
| identity | hash the bytes | hash the meaning, such as the shape, the netlist, or the schema |
| diff | line by line | the units the practitioner thinks in |
| merge | three way on lines | the domain's stable objects, with a validity check on the result |
| review | a text diff in a browser | a rendering of the thing itself |

Each one fails in its own way. Get identity wrong and every save looks like a change. Get merge wrong and the answer becomes "lock the file". Get review wrong and nobody reviews.

A useful screen before building any of these is a four part test.

1. **Is the artifact structured and stored opaquely?** CAD passes, because a feature tree ends up serialised into a binary blob.
2. **Do practitioners already describe changes semantically?** They say "I opened the bore to 23.5". Anything said in a review can be computed.
3. **Is concurrent work currently handled by asking in chat who has the file?** That is the tell for a missing merge model.
4. **Does review need a rendering?** If a text diff answers the question, git is already enough.

## Tier one, the same shape as CAD

### Electronics design

This is the strongest analogue. A schematic is a graph of components, nets, and pins, serialised into vendor formats that compare as garbage. Layout adds geometry with hard physical constraints on top of it.

Identity means hashing the netlist rather than the file, so a re-route that changes no connectivity is not a schematic change. Diff means a line like "R14 100 kΩ to 47 kΩ, net VDD_3V3 gained two loads, fourteen vias moved". Merge means merging by reference designator and by net, then running design rule checking on the merged board. That last step is the same idea as kerf's interference check, and it exists for the same reason, because two clean edits can produce an illegal board.

Hardware teams already run repositories where the firmware is reviewable and the board is a binary nobody can review. AllSpice and Altium 365 are working in this space, which means the need is validated rather than solved.

### Building information modelling

Revit and IFC models are element graphs with a very poor merge story. Coordination happens in weekly clash detection meetings, which is interference detection run by hand, in batch, days after the fact. Element level merge with automatic clash checking is the same product as kerf's, scaled up to a building, and the discipline boundaries between structural, mechanical, and electrical work give you natural branches.

### Simulation and scientific pipelines

Here the artifact is the whole run, meaning the inputs, the mesh, the solver version, and the results. What people need is provenance and comparability rather than a binary diff. The question they actually ask is which of the forty things that differ between two runs explains the three percent change in drag. Identity becomes the hash of the input closure, diff becomes a parameter comparison plus result deltas, and review becomes plots side by side.

## Tier two, strong with a different centre of gravity

### Spreadsheets and financial models

This passes the test cleanly and is badly under served. A model is a dependency graph of formulas wearing a grid costume.

A diff reads as "WACC 8.5% to 9.2%, 340 dependent cells, enterprise value down 12%", which is kerf's impact analysis with a different noun. Two analysts editing different sheets is trivially mergeable, and today it is handled by emailing a file called `model_v7_FINAL_jd.xlsx`. Regulated finance would buy the audit trail on its own.

The catch is that Excel is the substrate and it is hostile to this. The answer is a plugin and a service rather than a command line tool.

### Prompts, agents, and model configurations

This is the novel case, and the one where diff has to mean something genuinely new. The artifact is text, so git works, and the meaningful comparison is behavioural.

Identity means that two prompts scoring identically on a suite are the same prompt for practical purposes. A diff reads as "this edit moved pass rate from 71% to 78%, regressed three cases, and cost twelve percent more". Merging two prompt edits is only safe once the merged prompt has been evaluated, which is the interference check again. Here it is unavoidable, because prompt edits interact in ways nobody can predict from the text.

Everyone is currently versioning prompts in git and reviewing them by feel.

### Datasets and models

This is partly solved by DVC, LakeFS, and Weights and Biases, and partly not. The unsolved half is semantic. A dataset should be compared by distribution shift and label drift, and a model by per layer weight change and per slice evaluation movement. "Three thousand rows added, class balance moved four points, accuracy on the Spanish slice fell six" is a diff. "The checksum changed" is not.

### Databases, schema and data together

Dolt proved that people want this. The interesting frontier is the merge validity check, where merging two schema branches has to verify that the merged schema still satisfies its constraints against real data. That is clash detection expressed in SQL.

## Tier three, real with a weaker merge story

- **Design files such as Figma and Sketch.** Component tree diff and layer merge. Figma shipped branching, which validates the need, and the merge is still largely manual. Visual review is native here, which is why the field is further along than CAD.
- **Geographic data.** OpenStreetMap has run feature level merging for years, which proves the model works. The commercial equivalent for internal geospatial data barely exists.
- **Video, audio, and game levels.** The timeline or the scene graph merges well. The media does not merge and does not need to, because it is content addressed and immutable. Unity's YAML scene merge is the existence proof, and it is bad enough to prove the demand.
- **Legal contracts.** Clause level identity and obligation level diff, so a change reads as "liability cap 1M to 2M, new 30 day cure period". The blocker is not technical. The artifact is Word, and the workflow is adversarial, so merging is often not what anyone wants.
- **Biological constructs.** Plasmids and DNA designs are annotated sequences, so a comparison is a sequence diff plus an annotation diff. Merge validity becomes the question of whether the merged construct still expresses. Benchling owns the versioning and the merge semantics are open.

## Where this instinct is wrong

The pattern is seductive, so the failure cases are worth stating plainly.

**Unstructured blobs.** Raw footage, scans, and photographs have no meaningful diff or merge, only storage. Content addressed storage plus locks is the whole product, and calling it version control oversells it.

**Domains with a real single source of truth.** When everyone genuinely works in one live document, branching adds ceremony to solve a problem that liveness already solved. Branching earns its keep when work has to be isolated, which happens when it is long running, risky, or reviewed before it lands.

**Anywhere the merge cannot be validated.** If you cannot check that the merged result is valid in the domain, automatic merging is a liability. Kerf's interference check is not a nice extra. It is the thing that makes automatic merging defensible at all.

## What to build next

Electronics. It has the closest structure to what already works in kerf, since the feature tree becomes a netlist and the interference check becomes design rule checking. The user base already lives in git for the firmware half of the same project, the formats are parseable, and the willingness to pay is not in doubt. Almost every mechanism in this prototype ports over, including the content addressed store, semantic identity, per object three way merge, the validity check on merge, and rendered review.

Spreadsheets is the bigger market and the harder engineering problem, in that order.
