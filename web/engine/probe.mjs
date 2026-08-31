// Reads a job on stdin and prints the answers as JSON on stdout.
//
// This exists so the Python test suite can ask the JavaScript engine the same
// questions it asks its own, instead of the two being compared by hand. It is
// a test fixture and no part of the playground loads it.

import { evaluateExpression } from './expr.js';
import { parsePart, resolvedParameters, evaluatePart } from './part.js';
import { featureBounds } from './sdf.js';
import { measureSolid } from './validity.js';
import { defaultRange } from './sweep.js';

// Every directed edge has to appear once with its reverse. The directed form
// catches inconsistent winding as well as holes, which is the same test the
// Python side runs.
function isWatertight(mesh) {
  const seen = new Set();
  const idx = mesh.indices;
  for (let i = 0; i < idx.length; i += 3) {
    for (const [a, b] of [[0, 1], [1, 2], [2, 0]]) {
      const key = `${idx[i + a]},${idx[i + b]}`;
      if (seen.has(key)) return false;
      seen.add(key);
    }
  }
  for (const key of seen) {
    const [a, b] = key.split(',');
    if (!seen.has(`${b},${a}`)) return false;
  }
  return seen.size > 0;
}

const job = JSON.parse(await new Response(process.stdin).text());
const answer = {};

if (job.expressions) {
  answer.expressions = job.expressions.map(([text, params]) => {
    try {
      return { value: evaluateExpression(text, params) };
    } catch (error) {
      return { error: String(error.message) };
    }
  });
}

if (job.ranges) {
  answer.ranges = job.ranges.map((value) => defaultRange(value));
}

if (job.bounds) {
  answer.bounds = job.bounds.map((feature) => featureBounds(feature, {}));
}

if (job.parts) {
  answer.parts = job.parts.map(({ text, resolution }) => {
    const part = parsePart(text);
    const values = resolvedParameters(part);
    const solid = measureSolid(part, resolution);
    const built = evaluatePart(part, resolution);
    return {
      parameters: values,
      volume: solid.volume,
      bodies: solid.bodies,
      triangles: built.stats.triangles,
      meshVolume: built.stats.volume,
      watertight: isWatertight(built.mesh),
    };
  });
}

process.stdout.write(JSON.stringify(answer));
