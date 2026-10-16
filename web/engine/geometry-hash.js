// Deciding whether two meshes describe the same solid.
//
// Two questions get asked, in order. The first is whether the shapes are
// exactly the same once the file format's freedom is removed, and the
// geometry hash answers it. The second is whether they agree to within a
// tolerance, and the deviation measure answers that. The second question
// exists because some exporters write float noise into a part nobody edited.

// Hash the shape rather than the file. Triangle order, the order of corners
// inside a triangle, vertex numbering and float noise below the tolerance all
// wash out. Winding survives, so a solid and its inside out twin differ.
export async function geometryHash(mesh, relTol = 1e-6) {
  if (mesh.isEmpty()) return 'empty';
  const [low, high] = mesh.bbox();
  const diagonal = Math.hypot(high[0] - low[0], high[1] - low[1], high[2] - low[2]);
  const tolerance = Math.max(diagonal * relTol, 1e-9);

  const count = mesh.triangleCount;
  const rows = new Int32Array(count * 9);
  const p = mesh.positions;

  for (let face = 0; face < count; face += 1) {
    const corners = [];
    for (let corner = 0; corner < 3; corner += 1) {
      const at = mesh.indices[face * 3 + corner] * 3;
      corners.push([
        Math.round(p[at] / tolerance),
        Math.round(p[at + 1] / tolerance),
        Math.round(p[at + 2] / tolerance),
      ]);
    }
    // Rotate so the smallest corner leads. Rotation keeps the winding, so the
    // surface orientation survives the canonical form.
    let leading = 0;
    for (let corner = 1; corner < 3; corner += 1) {
      if (compare(corners[corner], corners[leading]) < 0) leading = corner;
    }
    for (let corner = 0; corner < 3; corner += 1) {
      const source = corners[(leading + corner) % 3];
      rows.set(source, face * 9 + corner * 3);
    }
  }

  const order = Array.from({ length: count }, (unused, index) => index);
  order.sort((a, b) => {
    for (let column = 0; column < 9; column += 1) {
      const difference = rows[a * 9 + column] - rows[b * 9 + column];
      if (difference) return difference;
    }
    return 0;
  });

  const sorted = new Int32Array(count * 9);
  order.forEach((source, target) => {
    sorted.set(rows.subarray(source * 9, source * 9 + 9), target * 9);
  });

  const digest = await crypto.subtle.digest('SHA-256', sorted.buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function compare(a, b) {
  for (let axis = 0; axis < 3; axis += 1) {
    if (a[axis] !== b[axis]) return a[axis] - b[axis];
  }
  return 0;
}

// Largest distance from a vertex of b to the nearest vertex of a. Vertices are
// paired with a spatial hash rather than by index or by sort order, because
// CAD meshes contain many exactly coincident coordinates and any ordering key
// reshuffles them under the very noise this exists to see through.
export function maxVertexDeviation(a, b) {
  if (a.isEmpty() || b.isEmpty()) return Infinity;
  if (a.vertexCount !== b.vertexCount || a.triangleCount !== b.triangleCount) return Infinity;

  const [low, high] = a.bbox();
  const diagonal = Math.hypot(high[0] - low[0], high[1] - low[1], high[2] - low[2]) || 1;
  const cell = diagonal * 1e-4;

  const buckets = new Map();
  const key = (i, j, k) => `${i},${j},${k}`;
  for (let index = 0; index < a.vertexCount; index += 1) {
    const at = index * 3;
    const bucket = key(
      Math.floor(a.positions[at] / cell),
      Math.floor(a.positions[at + 1] / cell),
      Math.floor(a.positions[at + 2] / cell),
    );
    const list = buckets.get(bucket);
    if (list) list.push(at);
    else buckets.set(bucket, [at]);
  }

  let worst = 0;
  for (let index = 0; index < b.vertexCount; index += 1) {
    const at = index * 3;
    const bi = Math.floor(b.positions[at] / cell);
    const bj = Math.floor(b.positions[at + 1] / cell);
    const bk = Math.floor(b.positions[at + 2] / cell);
    let best = Infinity;
    for (let di = -1; di <= 1; di += 1) {
      for (let dj = -1; dj <= 1; dj += 1) {
        for (let dk = -1; dk <= 1; dk += 1) {
          const list = buckets.get(key(bi + di, bj + dj, bk + dk));
          if (!list) continue;
          for (const other of list) {
            const distance = Math.hypot(
              a.positions[other] - b.positions[at],
              a.positions[other + 1] - b.positions[at + 1],
              a.positions[other + 2] - b.positions[at + 2],
            );
            if (distance < best) best = distance;
          }
        }
      }
    }
    if (best > worst) worst = best;
    if (worst === Infinity) return Infinity;
  }
  return worst;
}

// The same solid to within a fraction of its own size. This recognises the
// same tessellation with moved coordinates, which is what a re-export
// produces. A genuine re-mesh needs a surface distance measure to judge, so
// kerf reports it as a difference rather than guessing.
export function equivalent(a, b, relTol = 1e-5) {
  const [low, high] = a.bbox();
  const diagonal = Math.hypot(high[0] - low[0], high[1] - low[1], high[2] - low[2]) || 1;
  const deviation = maxVertexDeviation(a, b);
  return { same: deviation <= diagonal * relTol, deviation, diagonal };
}
