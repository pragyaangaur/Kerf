// The .kpart document: a parameter table and an ordered list of features.
//
// A mesh records what a part looks like. A feature tree records why it looks
// that way, and that is the difference version control needs. A mesh cannot
// say that a hole grew by 2 mm, and it cannot be merged with somebody else's
// copy. A feature tree can do both.

import { ExpressionError, resolve } from './expr.js';
import { evaluateField, featureBounds } from './sdf.js';
import { occupancyFromField } from './voxels.js';
import { surfaceNets } from './tessellate.js';

export const FEATURE_TYPES = ['box', 'cylinder', 'sphere', 'torus'];
export const OPS = ['add', 'subtract', 'intersect'];

export function parsePart(text) {
  const raw = typeof text === 'string' ? JSON.parse(text) : text;
  if (!('kerf_part' in raw)) throw new Error("not a kerf part file (missing 'kerf_part')");
  const seen = new Set();
  for (const feature of raw.features || []) {
    if (!feature.id) throw new Error('every feature needs a stable id');
    if (seen.has(feature.id)) throw new Error(`duplicate feature id ${feature.id}`);
    if (!FEATURE_TYPES.includes(feature.type)) {
      throw new Error(`feature ${feature.id}: unknown type ${feature.type}`);
    }
    if (feature.op && !OPS.includes(feature.op)) {
      throw new Error(`feature ${feature.id}: unknown op ${feature.op}`);
    }
    seen.add(feature.id);
  }
  return {
    kerf_part: 1,
    name: raw.name || 'part',
    units: raw.units || 'mm',
    parameters: { ...(raw.parameters || {}) },
    features: (raw.features || []).map((feature) => ({ ...feature })),
  };
}

export function clonePart(part) {
  return JSON.parse(JSON.stringify(part));
}

export function serializePart(part) {
  return `${JSON.stringify(part, null, 2)}\n`;
}

export function featureLabel(feature) {
  return feature.name || `${feature.type}:${feature.id}`;
}

// Parameters may refer to each other, so this repeats until everything
// resolves. Anything left over is circular or points at a name that does not
// exist, and both cases are reported rather than silently dropped.
export function resolvedParameters(part) {
  const resolved = {};
  const pending = { ...part.parameters };
  for (let pass = 0; pass <= Object.keys(part.parameters).length; pass += 1) {
    const keys = Object.keys(pending);
    if (keys.length === 0) break;
    let progressed = false;
    for (const key of keys) {
      try {
        resolved[key] = resolve(pending[key], resolved);
      } catch {
        continue;
      }
      delete pending[key];
      progressed = true;
    }
    if (!progressed) break;
  }
  const left = Object.keys(pending);
  if (left.length) {
    throw new ExpressionError(
      `unresolvable parameters (circular or undefined): ${left.sort().join(', ')}`,
    );
  }
  return resolved;
}

export function activeFeatures(part) {
  return part.features.filter((feature) => !feature.suppressed);
}

// A box containing the part. Only features that add material count, because a
// cut can reach far outside the solid it cuts.
export function partBounds(part, params) {
  const boxes = activeFeatures(part)
    .filter((feature) => (feature.op || 'add') !== 'subtract')
    .map((feature) => featureBounds(feature, params));
  if (!boxes.length) return [[-1, -1, -1], [1, 1, 1]];
  const low = [0, 1, 2].map((axis) => Math.min(...boxes.map((box) => box[0][axis])));
  const high = [0, 1, 2].map((axis) => Math.max(...boxes.map((box) => box[1][axis])));
  const pad = Math.max(Math.max(...[0, 1, 2].map((a) => high[a] - low[a])) * 0.05, 1e-6);
  return [low.map((v) => v - pad), high.map((v) => v + pad)];
}

export function buildGrid(bounds, resolution) {
  const [low, high] = bounds;
  const span = [0, 1, 2].map((axis) => high[axis] - low[axis]);
  const pitch = Math.max(...span) / Math.max(resolution, 4);
  return {
    origin: low.slice(),
    pitch,
    dims: span.map((size) => Math.max(2, Math.ceil(size / pitch)) + 1),
  };
}

// Evaluate a part once and keep everything that came out of it. The field is
// reused for the mesh and for the occupancy grid, so a comparison costs one
// pass rather than two.
export function evaluatePart(part, resolution = 44, sharedGrid = null) {
  const params = resolvedParameters(part);
  const grid = sharedGrid || buildGrid(partBounds(part, params), resolution);
  const field = evaluateField(activeFeatures(part), params, grid);
  const mesh = surfaceNets(field, grid);
  return {
    part,
    params,
    grid,
    field,
    mesh,
    occupancy: occupancyFromField(field),
    stats: {
      ...mesh.stats(),
      features: part.features.length,
      activeFeatures: activeFeatures(part).length,
      parameters: Object.keys(part.parameters).length,
    },
  };
}

// One lattice that covers both revisions, so two fields can be subtracted
// cell by cell.
export function sharedGridFor(parts, resolution) {
  const boxes = parts.map((part) => partBounds(part, resolvedParameters(part)));
  const low = [0, 1, 2].map((axis) => Math.min(...boxes.map((box) => box[0][axis])));
  const high = [0, 1, 2].map((axis) => Math.max(...boxes.map((box) => box[1][axis])));
  return buildGrid([low, high], resolution);
}
