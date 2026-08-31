// Whether a part can be built at all.
//
// CAD calls this a rebuild error. A dimension points at a variable somebody
// deleted, two equations refer to each other in a loop, or a value reaches
// zero and a feature collapses. These checks answer the same question
// without opening a CAD system.

import { resolve } from './expr.js';
import { buildGraph, cycles, dangling } from './graph.js';
import { activeFeatures, buildGrid, partBounds, resolvedParameters } from './part.js';
import { evaluateField } from './sdf.js';
import { labelRegions, occupancyFromField } from './voxels.js';

const POSITIVE_KEYS = new Set(['radius', 'height', 'tube']);

const issue = (severity, scope, where, message) => ({ severity, scope, where, message });

export function checkEquations(part) {
  const graph = buildGraph(part);
  const issues = [];

  for (const [where, missing] of dangling(graph)) {
    issues.push(issue('error', 'equation', where,
      `reads "${missing}", which the parameter table does not define`));
  }
  for (const loop of cycles(graph)) {
    issues.push(issue('error', 'equation', loop.join(' → '),
      'these parameters depend on each other in a loop'));
  }
  if (issues.length) return issues;

  let values;
  try {
    values = resolvedParameters(part);
  } catch (error) {
    return [issue('error', 'equation', 'parameters', error.message)];
  }
  for (const [name, value] of Object.entries(values)) {
    if (!Number.isFinite(value)) issues.push(issue('error', 'equation', name, `resolves to ${value}`));
  }
  return issues;
}

function number(raw, values) {
  try {
    return resolve(raw, values);
  } catch {
    return null;
  }
}

export function checkFeatures(part, values) {
  const issues = [];
  for (const feature of activeFeatures(part)) {
    for (const [key, raw] of Object.entries(feature)) {
      if (POSITIVE_KEYS.has(key)) {
        const value = number(raw, values);
        if (value !== null && value <= 0) {
          issues.push(issue('error', 'feature', `${feature.name || feature.id}.${key}`,
            `is ${value}, and a size has to be above zero`));
        }
      } else if (key === 'size' && Array.isArray(raw)) {
        raw.forEach((item, index) => {
          const value = number(item, values);
          if (value !== null && value <= 0) {
            const axis = index < 3 ? 'xyz'[index] : index;
            issues.push(issue('error', 'feature', `${feature.name || feature.id}.size.${axis}`,
              `is ${value}, and a size has to be above zero`));
          }
        });
      }
    }
  }
  return issues;
}

// Volume and body count without tessellating. Counting whole cells aliases
// badly on a face lying along the lattice, so each cell contributes the
// fraction the distance says it fills.
// A lattice of cell centres rather than cell corners.
//
// Each sample here stands for one whole cell, and the fraction of that cell
// the surface leaves filled is what the volume adds up. Sampling the corners
// instead counts a shell of half cells at full weight, which is a real bias
// and put this engine a tenth of a percent above the Python one. The command
// line tool measures on cell centres, and so does this.
function cellCentres(grid) {
  return {
    origin: grid.origin.map((value) => value + grid.pitch / 2),
    pitch: grid.pitch,
    dims: grid.dims.map((size) => Math.max(1, size - 1)),
  };
}

export function measureSolid(part, resolution = 26) {
  const params = resolvedParameters(part);
  const grid = cellCentres(buildGrid(partBounds(part, params), resolution));
  const field = evaluateField(activeFeatures(part), params, grid);
  const cell = grid.pitch ** 3;
  let filled = 0;
  for (let i = 0; i < field.length; i += 1) {
    const fraction = 0.5 - field[i] / grid.pitch;
    filled += fraction < 0 ? 0 : fraction > 1 ? 1 : fraction;
  }
  const occupancy = occupancyFromField(field);
  let inside = 0;
  for (let i = 0; i < occupancy.length; i += 1) inside += occupancy[i];
  if (!inside) return { volume: 0, bodies: 0 };
  return { volume: filled * cell, bodies: labelRegions(occupancy, grid.dims).count };
}

export function checkPart(part, { geometry = true, resolution = 24 } = {}) {
  const issues = checkEquations(part);
  if (issues.length) return issues;

  const values = resolvedParameters(part);
  issues.push(...checkFeatures(part, values));
  if (issues.length || !geometry) return issues;

  if (!activeFeatures(part).length) {
    return [issue('error', 'geometry', 'part', 'has no features left to build')];
  }

  let measured;
  try {
    measured = measureSolid(part, resolution);
  } catch (error) {
    return [issue('error', 'geometry', 'part', `cannot be evaluated: ${error.message}`)];
  }
  if (measured.volume <= 0) {
    issues.push(issue('error', 'geometry', 'part', 'builds to nothing at this size'));
  } else if (measured.bodies > 1) {
    issues.push(issue('warning', 'geometry', 'part',
      `has fallen into ${measured.bodies} separate bodies`));
  }
  return issues;
}
