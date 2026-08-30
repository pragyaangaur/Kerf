// Occupancy grids, and the regions found in them.
//
// The browser has the distance field already, so a cell is inside when the
// field is negative there. That is both faster and more exact than casting
// rays at a surface, which is what the command line tool has to do for a mesh
// that arrived without a feature tree.

export function occupancyFromField(field) {
  const grid = new Uint8Array(field.length);
  for (let i = 0; i < field.length; i += 1) grid[i] = field[i] < 0 ? 1 : 0;
  return grid;
}

export function countCells(grid) {
  let total = 0;
  for (let i = 0; i < grid.length; i += 1) total += grid[i];
  return total;
}

// Cells with all six neighbours occupied. A changed layer only one cell thick
// is thinner than the measurement itself, and that is what surface noise looks
// like. A region holding a seed is thicker than the lattice, so it is real.
export function interiorSeeds(grid, dims) {
  const [nx, ny, nz] = dims;
  const seeds = new Uint8Array(grid.length);
  const at = (i, j, k) => grid[(i * ny + j) * nz + k];
  for (let i = 1; i < nx - 1; i += 1) {
    for (let j = 1; j < ny - 1; j += 1) {
      for (let k = 1; k < nz - 1; k += 1) {
        if (!at(i, j, k)) continue;
        if (
          at(i - 1, j, k) && at(i + 1, j, k)
          && at(i, j - 1, k) && at(i, j + 1, k)
          && at(i, j, k - 1) && at(i, j, k + 1)
        ) {
          seeds[(i * ny + j) * nz + k] = 1;
        }
      }
    }
  }
  return seeds;
}

// Group occupied cells into regions joined across faces, using a flood fill
// with an explicit stack so a large region cannot overflow the call stack.
export function labelRegions(grid, dims) {
  const [nx, ny, nz] = dims;
  const labels = new Int32Array(grid.length).fill(0);
  const stack = [];
  let count = 0;

  for (let start = 0; start < grid.length; start += 1) {
    if (!grid[start] || labels[start]) continue;
    count += 1;
    labels[start] = count;
    stack.push(start);
    while (stack.length) {
      const index = stack.pop();
      const k = index % nz;
      const j = Math.floor(index / nz) % ny;
      const i = Math.floor(index / (ny * nz));
      const neighbours = [
        i > 0 ? index - ny * nz : -1,
        i < nx - 1 ? index + ny * nz : -1,
        j > 0 ? index - nz : -1,
        j < ny - 1 ? index + nz : -1,
        k > 0 ? index - 1 : -1,
        k < nz - 1 ? index + 1 : -1,
      ];
      for (const neighbour of neighbours) {
        if (neighbour >= 0 && grid[neighbour] && !labels[neighbour]) {
          labels[neighbour] = count;
          stack.push(neighbour);
        }
      }
    }
  }
  return { labels, count };
}
