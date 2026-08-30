// A triangle mesh and the measurements taken from it.
//
// Vertices are held as a flat Float32Array so the same buffer can go straight
// into WebGL without another copy.

export class Mesh {
  constructor(positions, indices) {
    this.positions = positions;   // Float32Array, three numbers per vertex
    this.indices = indices;       // Uint32Array, three indices per triangle
  }

  get vertexCount() { return this.positions.length / 3; }

  get triangleCount() { return this.indices.length / 3; }

  isEmpty() { return this.indices.length === 0; }

  bbox() {
    if (this.vertexCount === 0) return [[0, 0, 0], [0, 0, 0]];
    const low = [Infinity, Infinity, Infinity];
    const high = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < this.positions.length; i += 3) {
      for (let axis = 0; axis < 3; axis += 1) {
        const value = this.positions[i + axis];
        if (value < low[axis]) low[axis] = value;
        if (value > high[axis]) high[axis] = value;
      }
    }
    return [low, high];
  }

  area() {
    let total = 0;
    const p = this.positions;
    for (let i = 0; i < this.indices.length; i += 3) {
      const a = this.indices[i] * 3;
      const b = this.indices[i + 1] * 3;
      const c = this.indices[i + 2] * 3;
      const ux = p[b] - p[a]; const uy = p[b + 1] - p[a + 1]; const uz = p[b + 2] - p[a + 2];
      const vx = p[c] - p[a]; const vy = p[c + 1] - p[a + 1]; const vz = p[c + 2] - p[a + 2];
      total += Math.hypot(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx);
    }
    return total / 2;
  }

  // Enclosed volume, from the divergence theorem over the faces.
  volume() {
    let total = 0;
    const p = this.positions;
    for (let i = 0; i < this.indices.length; i += 3) {
      const a = this.indices[i] * 3;
      const b = this.indices[i + 1] * 3;
      const c = this.indices[i + 2] * 3;
      const cx = p[b + 1] * p[c + 2] - p[b + 2] * p[c + 1];
      const cy = p[b + 2] * p[c] - p[b] * p[c + 2];
      const cz = p[b] * p[c + 1] - p[b + 1] * p[c];
      total += p[a] * cx + p[a + 1] * cy + p[a + 2] * cz;
    }
    return Math.abs(total / 6);
  }

  centroid() {
    const [low, high] = this.bbox();
    return [(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2];
  }

  stats() {
    const [low, high] = this.bbox();
    return {
      triangles: this.triangleCount,
      vertices: this.vertexCount,
      volume: this.volume(),
      area: this.area(),
      bboxMin: low,
      bboxMax: high,
      size: [high[0] - low[0], high[1] - low[1], high[2] - low[2]],
    };
  }
}
