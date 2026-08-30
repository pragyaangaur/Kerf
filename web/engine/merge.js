// Three way merge of two feature trees.
//
// Every feature carries a stable id, so the merge works per feature and per
// parameter instead of per line. Two people who touch different features get
// a clean merge. Two people who touch the same field get a conflict naming
// the field. After that the merged part is evaluated and checked for
// features that occupy the same space, because a merge can succeed on the
// tree and still be wrong in the part.

import { clonePart, featureLabel, resolvedParameters } from './part.js';
import { compileFeature, featureBounds } from './sdf.js';
import { checkEquations } from './validity.js';

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function fieldKeys(feature) {
  return Object.keys(feature).filter(
    (key) => !['id', 'type', 'op', 'name', 'suppressed'].includes(key),
  );
}

// Merge a list where the two sides moved different components. Moving a
// feature along x while somebody else moves it along y is two edits that can
// both survive. Returns null when the same component changed on both sides.
function mergeVector(base, ours, theirs) {
  if (!Array.isArray(base) || !Array.isArray(ours) || !Array.isArray(theirs)) return null;
  if (base.length !== ours.length || base.length !== theirs.length) return null;
  const combined = [];
  for (let i = 0; i < base.length; i += 1) {
    if (same(ours[i], theirs[i])) combined.push(ours[i]);
    else if (same(ours[i], base[i])) combined.push(theirs[i]);
    else if (same(theirs[i], base[i])) combined.push(ours[i]);
    else return null;
  }
  return combined;
}

function mergeFeature(base, ours, theirs) {
  const conflicts = [];
  const notes = [];
  const merged = { ...ours };
  const original = base || { id: ours.id, type: ours.type };

  for (const attribute of ['type', 'op', 'name', 'suppressed']) {
    const was = original[attribute];
    const mine = ours[attribute];
    const yours = theirs[attribute];
    if (same(mine, yours)) continue;
    if (same(mine, was)) {
      merged[attribute] = yours;
      notes.push(`${featureLabel(ours)}.${attribute} taken from theirs`);
    } else if (!same(yours, was)) {
      conflicts.push({
        scope: 'field', key: `${featureLabel(ours)}.${attribute}`,
        base: was, ours: mine, theirs: yours,
      });
    }
  }

  const keys = new Set([...fieldKeys(original), ...fieldKeys(ours), ...fieldKeys(theirs)]);
  for (const key of [...keys].sort()) {
    const was = original[key];
    const mine = ours[key];
    const yours = theirs[key];
    if (same(mine, yours)) continue;
    if (same(mine, was)) {
      if (yours === undefined) delete merged[key];
      else merged[key] = yours;
      notes.push(`${featureLabel(ours)}.${key} taken from theirs`);
    } else if (same(yours, was)) {
      // Only our side moved, so what is already in merged is correct.
    } else {
      const combined = mergeVector(was, mine, yours);
      if (combined) {
        merged[key] = combined;
        notes.push(`${featureLabel(ours)}.${key} merged one axis at a time`);
      } else {
        conflicts.push({
          scope: 'field', key: `${featureLabel(ours)}.${key}`,
          base: was, ours: mine, theirs: yours,
        });
      }
    }
  }
  return { merged, conflicts, notes };
}

// Report pairs of newly added features that share space. Only features added
// on opposite sides are compared, because anything already in the common
// ancestor was agreed before the branches split.
export function detectInterference(merged, oursAdded, theirsAdded, samples = 18) {
  if (!oursAdded.length || !theirsAdded.length) return [];
  let params;
  try {
    params = resolvedParameters(merged);
  } catch {
    return [];
  }

  const byId = new Map(merged.features.map((feature) => [feature.id, feature]));
  const found = [];

  for (const ourId of oursAdded) {
    const ours = byId.get(ourId);
    if (!ours || ours.suppressed) continue;
    for (const theirId of theirsAdded) {
      const theirs = byId.get(theirId);
      if (!theirs || theirs.suppressed) continue;

      const [ourLow, ourHigh] = featureBounds(ours, params);
      const [theirLow, theirHigh] = featureBounds(theirs, params);
      const low = [0, 1, 2].map((axis) => Math.max(ourLow[axis], theirLow[axis]));
      const high = [0, 1, 2].map((axis) => Math.min(ourHigh[axis], theirHigh[axis]));
      if ([0, 1, 2].some((axis) => high[axis] <= low[axis])) continue;

      // Compile both features once, rather than for every sample point.
      const ourDistance = compileFeature(ours, params);
      const theirDistance = compileFeature(theirs, params);
      let overlapping = 0;
      const stepCount = samples - 1;
      for (let i = 0; i < samples; i += 1) {
        const x = low[0] + ((high[0] - low[0]) * i) / stepCount;
        for (let j = 0; j < samples; j += 1) {
          const y = low[1] + ((high[1] - low[1]) * j) / stepCount;
          for (let k = 0; k < samples; k += 1) {
            const z = low[2] + ((high[2] - low[2]) * k) / stepCount;
            if (ourDistance(x, y, z) < 0 && theirDistance(x, y, z) < 0) overlapping += 1;
          }
        }
      }
      if (!overlapping) continue;

      const cell = [0, 1, 2].reduce((acc, axis) => acc * ((high[axis] - low[axis]) / stepCount), 1);
      const volume = overlapping * cell;
      const boxVolume = [0, 1, 2].reduce((acc, axis) => acc * Math.max(high[axis] - low[axis], 1e-9), 1);
      if (volume < 1e-9 || volume < 1e-4 * boxVolume) continue;

      const ops = [ours.op || 'add', theirs.op || 'add'];
      let detail;
      if (ops[0] === 'subtract' && ops[1] === 'subtract') {
        detail = `both branches cut material here, and the two pockets break into one another over ${volume.toFixed(0)} mm³`;
      } else if (ops.includes('subtract')) {
        const cut = ops[1] === 'subtract' ? theirs : ours;
        const solid = ops[1] === 'subtract' ? ours : theirs;
        detail = `${featureLabel(cut)} cuts ${volume.toFixed(0)} mm³ out of ${featureLabel(solid)}, which was added on the other branch`;
      } else {
        detail = `two bodies added independently occupy the same ${volume.toFixed(0)} mm³ of space`;
      }
      found.push({
        scope: 'interference',
        key: `${featureLabel(ours)} / ${featureLabel(theirs)}`,
        detail,
        volume,
      });
    }
  }
  return found;
}

// Equation problems the merge itself introduced. One person renames a
// parameter, the other writes a dimension reading the old name, and both
// branches build on their own. Only new problems are reported, because a part
// that was already broken is not this merge's fault.
export function detectEquationBreaks(merged, sides) {
  const existing = new Set();
  for (const side of sides) {
    if (!side) continue;
    for (const issue of checkEquations(side)) {
      existing.add(`${issue.severity}|${issue.where}|${issue.message}`);
    }
  }
  return checkEquations(merged)
    .filter((issue) => issue.severity === 'error')
    .filter((issue) => !existing.has(`${issue.severity}|${issue.where}|${issue.message}`))
    .map((issue) => ({
      scope: 'equation',
      key: issue.where,
      detail: `${issue.message}. Both branches build on their own, and the merged part would not rebuild.`,
    }));
}

export function mergeParts(base, ours, theirs, checkInterference = true, checkEquationsGate = true) {
  const merged = clonePart(ours);
  const conflicts = [];
  const notes = [];

  for (const attribute of ['name', 'units']) {
    if (same(ours[attribute], theirs[attribute])) continue;
    if (same(ours[attribute], base[attribute])) merged[attribute] = theirs[attribute];
    else if (!same(theirs[attribute], base[attribute])) {
      conflicts.push({
        scope: 'field', key: attribute,
        base: base[attribute], ours: ours[attribute], theirs: theirs[attribute],
      });
    }
  }

  const parameterKeys = new Set([
    ...Object.keys(base.parameters), ...Object.keys(ours.parameters), ...Object.keys(theirs.parameters),
  ]);
  for (const key of [...parameterKeys].sort()) {
    const was = base.parameters[key];
    const mine = ours.parameters[key];
    const yours = theirs.parameters[key];
    if (same(mine, yours)) continue;
    if (same(mine, was)) {
      if (yours === undefined) {
        delete merged.parameters[key];
        notes.push(`parameter ${key} removed by theirs`);
      } else {
        merged.parameters[key] = yours;
        notes.push(`parameter ${key} set to ${yours} from theirs`);
      }
    } else if (same(yours, was)) {
      // Only our side changed it.
    } else {
      conflicts.push({ scope: 'parameter', key, base: was, ours: mine, theirs: yours });
    }
  }

  const baseFeatures = new Map(base.features.map((feature) => [feature.id, feature]));
  const ourFeatures = new Map(ours.features.map((feature) => [feature.id, feature]));
  const theirFeatures = new Map(theirs.features.map((feature) => [feature.id, feature]));
  const theirsAdded = [];

  for (const [id, theirFeature] of theirFeatures) {
    const original = baseFeatures.get(id);
    const ourFeature = ourFeatures.get(id);
    if (!ourFeature && !original) {
      merged.features.push({ ...theirFeature });
      theirsAdded.push(id);
      notes.push(`feature ${featureLabel(theirFeature)} added from theirs`);
      continue;
    }
    if (!ourFeature && original) {
      if (!same(theirFeature, original)) {
        conflicts.push({
          scope: 'feature', key: id,
          detail: 'deleted on our side and modified on theirs',
          ours: 'deleted', theirs: 'modified', base: 'present',
        });
      }
      continue;
    }
    const outcome = mergeFeature(original, ourFeature, theirFeature);
    conflicts.push(...outcome.conflicts);
    notes.push(...outcome.notes);
    const position = merged.features.findIndex((feature) => feature.id === id);
    merged.features[position] = outcome.merged;
  }

  for (const [id, original] of baseFeatures) {
    if (theirFeatures.has(id)) continue;
    const ourFeature = ourFeatures.get(id);
    if (!ourFeature) continue;
    if (!same(ourFeature, original)) {
      conflicts.push({
        scope: 'feature', key: id,
        detail: 'modified on our side and deleted on theirs',
        ours: 'modified', theirs: 'deleted', base: 'present',
      });
    } else {
      merged.features = merged.features.filter((feature) => feature.id !== id);
      notes.push(`feature ${featureLabel(original)} removed by theirs`);
    }
  }

  // The validity gates run only on a merge that is otherwise clean. There is
  // no point saying the merged part will not rebuild when somebody still has
  // to resolve a conflict that changes it.
  let equationBreaks = [];
  if (checkEquationsGate && !conflicts.length) {
    equationBreaks = detectEquationBreaks(merged, [base, ours, theirs]);
    conflicts.push(...equationBreaks);
  }

  let interference = [];
  if (checkInterference && !conflicts.length) {
    const oursAdded = ours.features
      .filter((feature) => !baseFeatures.has(feature.id))
      .map((feature) => feature.id);
    interference = detectInterference(merged, oursAdded, theirsAdded);
    conflicts.push(...interference);
  }

  return {
    merged, conflicts, notes, interference, equationBreaks,
    clean: conflicts.length === 0,
  };
}
