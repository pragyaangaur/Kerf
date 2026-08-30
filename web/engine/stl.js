// Writing binary STL, and writing it again the way a CAD system would.
//
// The second part is what makes the re-export demonstration honest. Rather
// than claiming that exporters shuffle facets and jitter floats, the page
// does it and then measures the result.

import { Mesh } from './mesh.js';

export function writeBinaryStl(mesh, header = 'kerf') {
  const count = mesh.triangleCount;
  const buffer = new ArrayBuffer(84 + count * 50);
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);
  const stamp = new TextEncoder().encode(header.slice(0, 80));
  bytes.set(stamp, 0);
  view.setUint32(80, count, true);

  const p = mesh.positions;
  for (let face = 0; face < count; face += 1) {
    const a = mesh.indices[face * 3] * 3;
    const b = mesh.indices[face * 3 + 1] * 3;
    const c = mesh.indices[face * 3 + 2] * 3;
    const ux = p[b] - p[a]; const uy = p[b + 1] - p[a + 1]; const uz = p[b + 2] - p[a + 2];
    const vx = p[c] - p[a]; const vy = p[c + 1] - p[a + 1]; const vz = p[c + 2] - p[a + 2];
    let nx = uy * vz - uz * vy;
    let ny = uz * vx - ux * vz;
    let nz = ux * vy - uy * vx;
    const length = Math.hypot(nx, ny, nz) || 1;
    nx /= length; ny /= length; nz /= length;

    let offset = 84 + face * 50;
    view.setFloat32(offset, nx, true);
    view.setFloat32(offset + 4, ny, true);
    view.setFloat32(offset + 8, nz, true);
    offset += 12;
    for (const corner of [a, b, c]) {
      view.setFloat32(offset, p[corner], true);
      view.setFloat32(offset + 4, p[corner + 1], true);
      view.setFloat32(offset + 8, p[corner + 2], true);
      offset += 12;
    }
    view.setUint16(offset, 0, true);
  }
  return buffer;
}

// Produce the same solid the way a second export would write it. The facet
// order changes, the header carries a new stamp, and every coordinate moves
// by less than the tolerance.
export function reexport(mesh, seed = 1, jitter = 2e-6) {
  const random = makeRandom(seed);
  const [low, high] = mesh.bbox();
  const diagonal = Math.hypot(high[0] - low[0], high[1] - low[1], high[2] - low[2]) || 1;
  const noise = diagonal * jitter;

  const positions = new Float32Array(mesh.positions.length);
  for (let i = 0; i < positions.length; i += 1) {
    positions[i] = mesh.positions[i] + (random() - 0.5) * noise;
  }

  const faceCount = mesh.triangleCount;
  const order = Array.from({ length: faceCount }, (unused, index) => index);
  for (let i = faceCount - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  const indices = new Uint32Array(mesh.indices.length);
  order.forEach((source, target) => {
    indices[target * 3] = mesh.indices[source * 3];
    indices[target * 3 + 1] = mesh.indices[source * 3 + 1];
    indices[target * 3 + 2] = mesh.indices[source * 3 + 2];
  });

  return new Mesh(positions, indices);
}

// A small deterministic generator, so the demonstration repeats exactly.
function makeRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

export function countDifferentBytes(a, b) {
  const left = new Uint8Array(a);
  const right = new Uint8Array(b);
  const length = Math.min(left.length, right.length);
  let different = Math.abs(left.length - right.length);
  for (let i = 0; i < length; i += 1) if (left[i] !== right[i]) different += 1;
  return { different, total: Math.max(left.length, right.length) };
}
