// Comparing two revisions.
//
// Two layers run. The feature comparison says why a part changed, in the
// words the designer used. The volume comparison says where material moved,
// and it works on any shape at all.

import { expressionDependencies, resolve } from './expr.js';
import { featureLabel, resolvedParameters } from './part.js';
import { interiorSeeds, labelRegions } from './voxels.js';

function safeParams(part) {
  try {
    return resolvedParameters(part);
  } catch {
    return {};
  }
}

function numeric(value, params) {
  try {
    return resolve(value, params);
  } catch {
    return null;
  }
}

function percent(before, after) {
  if (before === null || after === null || before === 0) return null;
  return ((after - before) / Math.abs(before)) * 100;
}

function fieldChange(key, before, after, beforeValue, afterValue) {
  return { key, before, after, beforeValue, afterValue, pct: percent(beforeValue, afterValue) };
}

function diffFeatureFields(before, after, beforeParams, afterParams) {
  const changes = [];
  if (before.type !== after.type) changes.push(fieldChange('type', before.type, after.type, null, null));
  if ((before.op || 'add') !== (after.op || 'add')) {
    changes.push(fieldChange('op', before.op || 'add', after.op || 'add', null, null));
  }
  const skip = new Set(['id', 'type', 'op', 'name', 'suppressed']);
  const keys = new Set([...Object.keys(before), ...Object.keys(after)].filter((k) => !skip.has(k)));
  for (const key of [...keys].sort()) {
    const a = before[key];
    const b = after[key];
    if (JSON.stringify(a) === JSON.stringify(b)) continue;
    if (Array.isArray(a) || Array.isArray(b)) {
      const listA = Array.isArray(a) ? a : [a];
      const listB = Array.isArray(b) ? b : [b];
      const axes = 'xyz';
      for (let i = 0; i < Math.max(listA.length, listB.length); i += 1) {
        if (JSON.stringify(listA[i]) === JSON.stringify(listB[i])) continue;
        changes.push(fieldChange(
          `${key}.${i < 3 ? axes[i] : i}`, listA[i], listB[i],
          numeric(listA[i], beforeParams), numeric(listB[i], afterParams),
        ));
      }
    } else {
      changes.push(fieldChange(key, a, b, numeric(a, beforeParams), numeric(b, afterParams)));
    }
  }
  return changes;
}

export function diffParts(before, after) {
  const beforeParams = safeParams(before);
  const afterParams = safeParams(after);
  const result = {
    parameters: [], parametersAdded: {}, parametersRemoved: {},
    features: [], renamed: [], impact: {},
  };

  const keys = new Set([...Object.keys(before.parameters), ...Object.keys(after.parameters)]);
  for (const key of [...keys].sort()) {
    const hasBefore = key in before.parameters;
    const hasAfter = key in after.parameters;
    if (!hasAfter) result.parametersRemoved[key] = before.parameters[key];
    else if (!hasBefore) result.parametersAdded[key] = after.parameters[key];
    else if (before.parameters[key] !== after.parameters[key]) {
      result.parameters.push(fieldChange(
        key, before.parameters[key], after.parameters[key],
        beforeParams[key] ?? null, afterParams[key] ?? null,
      ));
    }
  }

  const changed = new Set([
    ...result.parameters.map((change) => change.key),
    ...Object.keys(result.parametersRemoved),
  ]);
  if (changed.size) {
    for (const feature of after.features) {
      const reads = new Set();
      for (const [key, value] of Object.entries(feature)) {
        if (['id', 'type', 'op', 'name', 'suppressed'].includes(key)) continue;
        const items = Array.isArray(value) ? value : [value];
        for (const item of items) {
          for (const name of expressionDependencies(item)) reads.add(name);
        }
      }
      for (const name of reads) {
        if (!changed.has(name)) continue;
        (result.impact[name] = result.impact[name] || []).push(featureLabel(feature));
      }
    }
  }

  const beforeIndex = new Map(before.features.map((feature, i) => [feature.id, i]));
  const afterIndex = new Map(after.features.map((feature, i) => [feature.id, i]));

  for (const feature of after.features) {
    if (!beforeIndex.has(feature.id)) {
      result.features.push({
        id: feature.id, status: 'added', label: featureLabel(feature),
        type: feature.type, changes: [], afterIndex: afterIndex.get(feature.id),
      });
    }
  }
  for (const feature of before.features) {
    if (!afterIndex.has(feature.id)) {
      result.features.push({
        id: feature.id, status: 'removed', label: featureLabel(feature),
        type: feature.type, changes: [], beforeIndex: beforeIndex.get(feature.id),
      });
    }
  }
  for (const feature of after.features) {
    if (!beforeIndex.has(feature.id)) continue;
    const original = before.features[beforeIndex.get(feature.id)];
    if ((original.name || '') !== (feature.name || '')) {
      result.renamed.push([feature.id, original.name || '', feature.name || '']);
    }
    const changes = diffFeatureFields(original, feature, beforeParams, afterParams);
    const wasSuppressed = Boolean(original.suppressed);
    const isSuppressed = Boolean(feature.suppressed);
    if (wasSuppressed !== isSuppressed) {
      result.features.push({
        id: feature.id, status: isSuppressed ? 'suppressed' : 'resumed',
        label: featureLabel(feature), type: feature.type, changes,
        beforeIndex: beforeIndex.get(feature.id), afterIndex: afterIndex.get(feature.id),
      });
    } else if (changes.length) {
      result.features.push({
        id: feature.id, status: 'modified', label: featureLabel(feature),
        type: feature.type, changes,
        beforeIndex: beforeIndex.get(feature.id), afterIndex: afterIndex.get(feature.id),
      });
    }
  }

  result.features.sort((a, b) => (a.afterIndex ?? 1e9) - (b.afterIndex ?? 1e9));
  return result;
}

export function isEmptyDiff(diff) {
  return !(
    diff.parameters.length
    || Object.keys(diff.parametersAdded).length
    || Object.keys(diff.parametersRemoved).length
    || diff.features.length
    || diff.renamed.length
  );
}

// Subtract two occupancy grids and describe what is left over. A region that
// is nowhere thicker than one cell is measurement noise rather than material,
// so it is counted separately and left out of the reported change.
export function diffVolumes(beforeGrid, afterGrid, grid) {
  const cell = grid.pitch ** 3;
  const added = new Uint8Array(beforeGrid.length);
  const removed = new Uint8Array(beforeGrid.length);
  let commonCells = 0;
  let beforeCells = 0;
  let afterCells = 0;

  for (let i = 0; i < beforeGrid.length; i += 1) {
    const was = beforeGrid[i];
    const now = afterGrid[i];
    beforeCells += was;
    afterCells += now;
    if (now && !was) added[i] = 1;
    else if (was && !now) removed[i] = 1;
    else if (was && now) commonCells += 1;
  }

  const result = {
    pitch: grid.pitch,
    resolution: Math.max(...grid.dims) - 1,
    volumeBefore: beforeCells * cell,
    volumeAfter: afterCells * cell,
    commonVolume: commonCells * cell,
    addedVolume: 0,
    removedVolume: 0,
    noiseVolume: 0,
    noiseCells: 0,
    regions: [],
  };

  for (const [kind, mask] of [['added', added], ['removed', removed]]) {
    const seeds = interiorSeeds(mask, grid.dims);
    const { labels, count } = labelRegions(mask, grid.dims);
    if (!count) continue;
    const seeded = new Set();
    for (let i = 0; i < seeds.length; i += 1) if (seeds[i]) seeded.add(labels[i]);

    const totals = new Array(count + 1).fill(0);
    const sums = Array.from({ length: count + 1 }, () => [0, 0, 0]);
    const lows = Array.from({ length: count + 1 }, () => [Infinity, Infinity, Infinity]);
    const highs = Array.from({ length: count + 1 }, () => [-Infinity, -Infinity, -Infinity]);
    const [, ny, nz] = grid.dims;

    for (let index = 0; index < labels.length; index += 1) {
      const label = labels[index];
      if (!label) continue;
      const k = index % nz;
      const j = Math.floor(index / nz) % ny;
      const i = Math.floor(index / (ny * nz));
      totals[label] += 1;
      const cellCoords = [i, j, k];
      for (let axis = 0; axis < 3; axis += 1) {
        sums[label][axis] += cellCoords[axis];
        lows[label][axis] = Math.min(lows[label][axis], cellCoords[axis]);
        highs[label][axis] = Math.max(highs[label][axis], cellCoords[axis]);
      }
    }

    for (let label = 1; label <= count; label += 1) {
      const cells = totals[label];
      const volume = cells * cell;
      if (!seeded.has(label)) {
        result.noiseVolume += volume;
        result.noiseCells += cells;
        continue;
      }
      result[kind === 'added' ? 'addedVolume' : 'removedVolume'] += volume;
      result.regions.push({
        kind,
        volume,
        cells,
        centroid: [0, 1, 2].map(
          (axis) => grid.origin[axis] + (sums[label][axis] / cells + 0.5) * grid.pitch,
        ),
        size: [0, 1, 2].map(
          (axis) => (highs[label][axis] - lows[label][axis] + 1) * grid.pitch,
        ),
      });
    }
  }

  result.regions.sort((a, b) => b.volume - a.volume);
  result.unchanged = result.regions.length === 0;
  const base = Math.max(result.volumeBefore, result.volumeAfter, 1e-12);
  result.changedFraction = (result.addedVolume + result.removedVolume) / base;
  return result;
}

// Sort a mesh's triangles by whether the other revision has that surface too.
// A triangle sitting exactly on the other solid's boundary is ambiguous, so
// the sample is taken a little way along the inward normal.
export function classifyTriangles(mesh, otherOccupancy, grid) {
  const [nx, ny, nz] = grid.dims;
  const shared = [];
  const only = [];
  const p = mesh.positions;
  const step = grid.pitch * 0.9;

  for (let i = 0; i < mesh.indices.length; i += 3) {
    const a = mesh.indices[i] * 3;
    const b = mesh.indices[i + 1] * 3;
    const c = mesh.indices[i + 2] * 3;
    const ux = p[b] - p[a]; const uy = p[b + 1] - p[a + 1]; const uz = p[b + 2] - p[a + 2];
    const vx = p[c] - p[a]; const vy = p[c + 1] - p[a + 1]; const vz = p[c + 2] - p[a + 2];
    let nxn = uy * vz - uz * vy;
    let nyn = uz * vx - ux * vz;
    let nzn = ux * vy - uy * vx;
    const length = Math.hypot(nxn, nyn, nzn) || 1;
    nxn /= length; nyn /= length; nzn /= length;

    const cx = (p[a] + p[b] + p[c]) / 3 - nxn * step;
    const cy = (p[a + 1] + p[b + 1] + p[c + 1]) / 3 - nyn * step;
    const cz = (p[a + 2] + p[b + 2] + p[c + 2]) / 3 - nzn * step;

    const gi = Math.floor((cx - grid.origin[0]) / grid.pitch);
    const gj = Math.floor((cy - grid.origin[1]) / grid.pitch);
    const gk = Math.floor((cz - grid.origin[2]) / grid.pitch);
    const inside = gi >= 0 && gj >= 0 && gk >= 0 && gi < nx && gj < ny && gk < nz
      && otherOccupancy[(gi * ny + gj) * nz + gk];

    const target = inside ? shared : only;
    target.push(mesh.indices[i], mesh.indices[i + 1], mesh.indices[i + 2]);
  }
  return { shared: new Uint32Array(shared), only: new Uint32Array(only) };
}
