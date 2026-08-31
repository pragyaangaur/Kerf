// Feature geometry as signed distance fields.
//
// Every feature is a function giving the distance from a point to its
// surface, negative inside. Combining features is arithmetic on those
// distances, and a fillet is a smooth version of the same arithmetic. The
// whole field is filled one feature at a time over a flat array, which keeps
// the inner loop free of allocation.

import { resolve, resolveVec } from './expr.js';

export function featureBounds(feature, params) {
  const centre = resolveVec(feature.center, params);
  let half;
  if (feature.type === 'box') {
    half = resolveVec(feature.size, params, [1, 1, 1]).map((v) => v / 2);
  } else if (feature.type === 'cylinder') {
    const radius = resolve(feature.radius ?? 1, params);
    const halfHeight = resolve(feature.height ?? 1, params) / 2;
    half = [radius, radius, radius];
    half['xyz'.indexOf((feature.axis || 'z').toLowerCase())] = halfHeight;
  } else if (feature.type === 'sphere') {
    const radius = resolve(feature.radius ?? 1, params);
    half = [radius, radius, radius];
  } else {
    const ring = resolve(feature.radius ?? 1, params);
    const tube = resolve(feature.tube ?? 0.25, params);
    half = [ring + tube, ring + tube, tube];
  }
  if (feature.rotate) {
    half = rotatedHalfExtent(half, resolveVec(feature.rotate, params));
  }
  return [
    [centre[0] - half[0], centre[1] - half[1], centre[2] - half[2]],
    [centre[0] + half[0], centre[1] + half[1], centre[2] + half[2]],
  ];
}

// Carry a point into the feature's own frame, which is what the field does
// before it measures anything. Kept beside featureBounds so the two cannot
// drift apart.
function toLocal([x, y, z], [rx, ry, rz]) {
  let px = x;
  let py = y;
  let pz = z;
  if (rx) {
    const c = Math.cos(-rx);
    const s = Math.sin(-rx);
    const ny = py * c - pz * s;
    pz = py * s + pz * c;
    py = ny;
  }
  if (ry) {
    const c = Math.cos(-ry);
    const s = Math.sin(-ry);
    const nx = px * c - pz * s;
    pz = px * s + pz * c;
    px = nx;
  }
  if (rz) {
    const c = Math.cos(-rz);
    const s = Math.sin(-rz);
    const nx = px * c - py * s;
    py = px * s + py * c;
    px = nx;
  }
  return [px, py, pz];
}

// Half extent of the box that holds a rotated box. Every corner is carried
// through the inverse of the transform the field applies, and the box around
// those eight points is the answer: exact for a box, and a safe
// over-estimate for the round shapes, which is the right way round for
// something that only sizes a lattice.
function rotatedHalfExtent(half, degrees) {
  const radians = degrees.map((d) => (d * Math.PI) / 180);
  if (!radians.some((value) => value)) return half;
  // toLocal maps world to local, so its transpose maps local back out.
  const columns = [
    toLocal([1, 0, 0], radians),
    toLocal([0, 1, 0], radians),
    toLocal([0, 0, 1], radians),
  ];
  const out = [0, 0, 0];
  for (const sx of [-1, 1]) {
    for (const sy of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const corner = [sx * half[0], sy * half[1], sz * half[2]];
        for (let axis = 0; axis < 3; axis += 1) {
          // columns[axis] is the column of the world-to-local matrix, so
          // reading down it applies that matrix's transpose, which is the
          // local-to-world direction wanted here.
          const value =
            corner[0] * columns[axis][0] +
            corner[1] * columns[axis][1] +
            corner[2] * columns[axis][2];
          out[axis] = Math.max(out[axis], Math.abs(value));
        }
      }
    }
  }
  return out;
}

// Compile a feature into a closure with its numbers already resolved.
//
// The field is sampled at hundreds of thousands of points, so resolving the
// same expressions inside that loop dominates the cost. Resolving once and
// capturing the results makes a live parameter drag feel immediate.
export function compileFeature(feature, params) {
  const centre = resolveVec(feature.center, params);
  const [cx, cy, cz] = centre;

  let rotate = null;
  if (feature.rotate) {
    const [rx, ry, rz] = resolveVec(feature.rotate, params).map((d) => (d * Math.PI) / 180);
    if (rx || ry || rz) {
      rotate = {
        cx: Math.cos(-rx), sx: Math.sin(-rx),
        cy: Math.cos(-ry), sy: Math.sin(-ry),
        cz: Math.cos(-rz), sz: Math.sin(-rz),
        rx, ry, rz,
      };
    }
  }

  const local = (x, y, z, out) => {
    let px = x - cx;
    let py = y - cy;
    let pz = z - cz;
    if (rotate) {
      if (rotate.rx) {
        const ny = py * rotate.cx - pz * rotate.sx;
        const nz = py * rotate.sx + pz * rotate.cx;
        py = ny; pz = nz;
      }
      if (rotate.ry) {
        const nx = px * rotate.cy - pz * rotate.sy;
        const nz = px * rotate.sy + pz * rotate.cy;
        px = nx; pz = nz;
      }
      if (rotate.rz) {
        const nx = px * rotate.cz - py * rotate.sz;
        const ny = px * rotate.sz + py * rotate.cz;
        px = nx; py = ny;
      }
    }
    out[0] = px; out[1] = py; out[2] = pz;
  };

  const point = [0, 0, 0];

  if (feature.type === 'box') {
    const size = resolveVec(feature.size, params, [1, 1, 1]);
    const round = resolve(feature.round ?? 0, params);
    const hx = size[0] / 2 - round;
    const hy = size[1] / 2 - round;
    const hz = size[2] / 2 - round;
    return (x, y, z) => {
      local(x, y, z, point);
      const qx = Math.abs(point[0]) - hx;
      const qy = Math.abs(point[1]) - hy;
      const qz = Math.abs(point[2]) - hz;
      const ox = qx > 0 ? qx : 0;
      const oy = qy > 0 ? qy : 0;
      const oz = qz > 0 ? qz : 0;
      const outside = Math.sqrt(ox * ox + oy * oy + oz * oz);
      const largest = qx > qy ? (qx > qz ? qx : qz) : (qy > qz ? qy : qz);
      return outside + (largest < 0 ? largest : 0) - round;
    };
  }

  if (feature.type === 'sphere') {
    const radius = resolve(feature.radius ?? 1, params);
    return (x, y, z) => {
      local(x, y, z, point);
      return Math.sqrt(
        point[0] * point[0] + point[1] * point[1] + point[2] * point[2],
      ) - radius;
    };
  }

  if (feature.type === 'cylinder') {
    const axis = 'xyz'.indexOf((feature.axis || 'z').toLowerCase());
    const radius = resolve(feature.radius ?? 1, params);
    const halfHeight = resolve(feature.height ?? 1, params) / 2;
    const first = axis === 0 ? 1 : 0;
    const second = axis === 2 ? 1 : 2;
    return (x, y, z) => {
      local(x, y, z, point);
      const a = point[first];
      const b = point[second];
      const radial = Math.sqrt(a * a + b * b) - radius;
      const axial = Math.abs(point[axis]) - halfHeight;
      const ox = radial > 0 ? radial : 0;
      const oy = axial > 0 ? axial : 0;
      const outside = Math.sqrt(ox * ox + oy * oy);
      const largest = radial > axial ? radial : axial;
      return outside + (largest < 0 ? largest : 0);
    };
  }

  if (feature.type === 'torus') {
    const ring = resolve(feature.radius ?? 1, params);
    const tube = resolve(feature.tube ?? 0.25, params);
    return (x, y, z) => {
      local(x, y, z, point);
      const planar = Math.sqrt(point[0] * point[0] + point[1] * point[1]) - ring;
      return Math.sqrt(planar * planar + point[2] * point[2]) - tube;
    };
  }

  throw new Error(`unhandled feature type ${feature.type}`);
}

// One point against one feature. The interference check asks about scattered
// points rather than a lattice, so it goes through here.
export function featureDistance(feature, params, x, y, z) {
  return compileFeature(feature, params)(x, y, z);
}

function smoothUnion(a, b, k) {
  if (k <= 0) return Math.min(a, b);
  const h = Math.min(Math.max(0.5 + (0.5 * (b - a)) / k, 0), 1);
  return b * (1 - h) + a * h - k * h * (1 - h);
}

function smoothSubtract(a, b, k) {
  if (k <= 0) return Math.max(a, -b);
  const h = Math.min(Math.max(0.5 - (0.5 * (b + a)) / k, 0), 1);
  return a * (1 - h) + -b * h + k * h * (1 - h);
}

function smoothIntersect(a, b, k) {
  if (k <= 0) return Math.max(a, b);
  const h = Math.min(Math.max(0.5 - (0.5 * (b - a)) / k, 0), 1);
  return b * (1 - h) + a * h + k * h * (1 - h);
}

export const COMBINE = { add: smoothUnion, subtract: smoothSubtract, intersect: smoothIntersect };

// Fill a flat array with the part's distance field, sampled at lattice points.
export function evaluateField(features, params, grid) {
  const [nx, ny, nz] = grid.dims;
  const { origin, pitch } = grid;
  const field = new Float32Array(nx * ny * nz).fill(1e9);
  let started = false;

  for (const feature of features) {
    if (feature.suppressed) continue;
    const op = feature.op || 'add';
    // A part that begins with a cut has nothing to cut into yet.
    if (!started && op === 'subtract') continue;

    const distanceAt = compileFeature(feature, params);
    const blend = resolve(feature.blend ?? 0, params);
    const combine = COMBINE[op];

    let cursor = 0;
    for (let i = 0; i < nx; i += 1) {
      const x = origin[0] + i * pitch;
      for (let j = 0; j < ny; j += 1) {
        const y = origin[1] + j * pitch;
        for (let k = 0; k < nz; k += 1, cursor += 1) {
          const distance = distanceAt(x, y, origin[2] + k * pitch);
          field[cursor] = started ? combine(field[cursor], distance, blend) : distance;
        }
      }
    }
    started = true;
  }
  return field;
}
