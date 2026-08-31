// Turning a distance field into triangles with surface nets.
//
// One vertex goes in every cell where the field changes sign, placed at the
// mean of the crossings on that cell's edges. Quads are then stitched between
// the four cells that share a crossing edge. The winding is chosen so normals
// point out of the solid, which the viewer relies on for backface culling.

import { Mesh } from './mesh.js';

// Corner index inside a cell is 4*dx + 2*dy + dz.
const CORNERS = [];
for (let dx = 0; dx < 2; dx += 1) {
  for (let dy = 0; dy < 2; dy += 1) {
    for (let dz = 0; dz < 2; dz += 1) CORNERS.push([dx, dy, dz]);
  }
}

const EDGES = [
  [0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3],
  [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7],
];

export function surfaceNets(field, grid) {
  const [sx, sy, sz] = grid.dims;
  const { origin, pitch } = grid;
  const nx = sx - 1;
  const ny = sy - 1;
  const nz = sz - 1;
  if (nx < 1 || ny < 1 || nz < 1) return new Mesh(new Float32Array(0), new Uint32Array(0));

  const at = (i, j, k) => field[(i * sy + j) * sz + k];
  const cellIndex = new Int32Array(nx * ny * nz).fill(-1);
  const positions = [];

  for (let i = 0; i < nx; i += 1) {
    for (let j = 0; j < ny; j += 1) {
      for (let k = 0; k < nz; k += 1) {
        const values = new Array(8);
        let inside = 0;
        for (let corner = 0; corner < 8; corner += 1) {
          const [dx, dy, dz] = CORNERS[corner];
          const value = at(i + dx, j + dy, k + dz);
          values[corner] = value;
          if (value < 0) inside += 1;
        }
        if (inside === 0 || inside === 8) continue;

        let ax = 0; let ay = 0; let az = 0; let hits = 0;
        for (const [first, second] of EDGES) {
          const a = values[first];
          const b = values[second];
          if ((a < 0) === (b < 0)) continue;
          const denominator = Math.abs(a - b) < 1e-30 ? 1e-30 : a - b;
          const along = Math.min(Math.max(a / denominator, 0), 1);
          const pa = CORNERS[first];
          const pb = CORNERS[second];
          ax += pa[0] + along * (pb[0] - pa[0]);
          ay += pa[1] + along * (pb[1] - pa[1]);
          az += pa[2] + along * (pb[2] - pa[2]);
          hits += 1;
        }
        const divisor = hits || 1;
        cellIndex[(i * ny + j) * nz + k] = positions.length / 3;
        positions.push(
          origin[0] + (i + ax / divisor) * pitch,
          origin[1] + (j + ay / divisor) * pitch,
          origin[2] + (k + az / divisor) * pitch,
        );
      }
    }
  }

  if (positions.length === 0) return new Mesh(new Float32Array(0), new Uint32Array(0));

  const vertexAt = (i, j, k) => {
    if (i < 0 || j < 0 || k < 0 || i >= nx || j >= ny || k >= nz) return -1;
    return cellIndex[(i * ny + j) * nz + k];
  };

  const indices = [];
  const pushQuad = (q00, q10, q11, q01, flip) => {
    if (q00 < 0 || q10 < 0 || q11 < 0 || q01 < 0) return;
    if (flip) {
      indices.push(q11, q10, q00, q01, q11, q00);
    } else {
      indices.push(q00, q10, q11, q00, q11, q01);
    }
  };

  // One pass per face direction. The direction being crossed starts at zero,
  // because the surface can cross between the first two sample layers, and
  // the two directions across the face start at one so all four neighbouring
  // cells exist. Running a single loop from one for all three directions
  // drops that first layer of faces and leaves the mesh with a hole in it.
  //
  // The field is negative inside, so the outward face points away from the
  // solid. Each direction is handed differently, and y is the odd one.
  for (let i = 0; i < sx - 1; i += 1) {
    for (let j = 1; j < sy - 1; j += 1) {
      for (let k = 1; k < sz - 1; k += 1) {
        const here = at(i, j, k) < 0;
        if (here !== (at(i + 1, j, k) < 0)) {
          pushQuad(
            vertexAt(i, j - 1, k - 1), vertexAt(i, j, k - 1),
            vertexAt(i, j, k), vertexAt(i, j - 1, k), !here,
          );
        }
      }
    }
  }
  for (let j = 0; j < sy - 1; j += 1) {
    for (let i = 1; i < sx - 1; i += 1) {
      for (let k = 1; k < sz - 1; k += 1) {
        const here = at(i, j, k) < 0;
        if (here !== (at(i, j + 1, k) < 0)) {
          pushQuad(
            vertexAt(i - 1, j, k - 1), vertexAt(i, j, k - 1),
            vertexAt(i, j, k), vertexAt(i - 1, j, k), here,
          );
        }
      }
    }
  }
  for (let k = 0; k < sz - 1; k += 1) {
    for (let i = 1; i < sx - 1; i += 1) {
      for (let j = 1; j < sy - 1; j += 1) {
        const here = at(i, j, k) < 0;
        if (here !== (at(i, j, k + 1) < 0)) {
          pushQuad(
            vertexAt(i - 1, j - 1, k), vertexAt(i, j - 1, k),
            vertexAt(i, j, k), vertexAt(i - 1, j, k), !here,
          );
        }
      }
    }
  }

  return new Mesh(new Float32Array(positions), new Uint32Array(indices));
}
