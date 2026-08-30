// The equation graph.
//
// CAD models are held together by equations. A dimension is rarely a number,
// it is bolt_d/2, and that expression is the design intent somebody wrote
// down. The engine already reads those expressions to build geometry, so the
// graph they form costs nothing extra and answers questions a file
// comparison cannot reach.

import { expressionDependencies } from './expr.js';
import { featureLabel } from './part.js';

// Fields holding a fixed choice rather than a number. A value like "y" here
// names an axis, and reading it as an expression would invent a parameter.
const ENUM_KEYS = new Set(['axis']);
const RESERVED = new Set(['id', 'type', 'op', 'name', 'suppressed', ...ENUM_KEYS]);

export function buildGraph(part) {
  const parameters = new Map();
  for (const [name, expression] of Object.entries(part.parameters)) {
    parameters.set(name, { name, expression, reads: expressionDependencies(expression) });
  }

  const fields = [];
  for (const feature of part.features) {
    const label = featureLabel(feature);
    for (const [key, value] of Object.entries(feature)) {
      if (RESERVED.has(key)) continue;
      if (Array.isArray(value)) {
        value.forEach((item, index) => {
          const reads = expressionDependencies(item);
          if (!reads.size) return;
          const suffix = index < 3 ? 'xyz'[index] : String(index);
          fields.push({
            featureId: feature.id, featureLabel: label,
            key: `${key}.${suffix}`, expression: item, reads,
            name: `${feature.id}.${key}.${suffix}`,
          });
        });
      } else {
        const reads = expressionDependencies(value);
        if (reads.size) {
          fields.push({
            featureId: feature.id, featureLabel: label,
            key, expression: value, reads, name: `${feature.id}.${key}`,
          });
        }
      }
    }
  }
  return { parameters, fields };
}

export function readersOf(graph, name) {
  const found = [];
  for (const ref of graph.parameters.values()) if (ref.reads.has(name)) found.push(ref.name);
  for (const ref of graph.fields) if (ref.reads.has(name)) found.push(ref.name);
  return found.sort();
}

export function downstream(graph, name) {
  const seen = new Set();
  const frontier = [name];
  while (frontier.length) {
    const current = frontier.pop();
    for (const reader of readersOf(graph, current)) {
      if (seen.has(reader)) continue;
      seen.add(reader);
      if (graph.parameters.has(reader)) frontier.push(reader);
    }
  }
  return seen;
}

export function upstream(graph, name) {
  const seen = new Set();
  const start = graph.parameters.get(name);
  const frontier = start ? [...start.reads] : [];
  while (frontier.length) {
    const current = frontier.pop();
    if (seen.has(current)) continue;
    seen.add(current);
    const parent = graph.parameters.get(current);
    if (parent) frontier.push(...parent.reads);
  }
  return seen;
}

// Feature labels that end up depending on a parameter, following the graph
// through any other parameters in between.
export function featureReadersOf(graph, name) {
  const reached = downstream(graph, name);
  reached.add(name);
  const ordered = [];
  const seen = new Set();
  for (const ref of graph.fields) {
    if (![...ref.reads].some((read) => reached.has(read))) continue;
    if (seen.has(ref.featureLabel)) continue;
    seen.add(ref.featureLabel);
    ordered.push(ref.featureLabel);
  }
  return ordered;
}

export function dangling(graph) {
  const known = new Set(graph.parameters.keys());
  const missing = [];
  for (const ref of graph.parameters.values()) {
    for (const name of [...ref.reads].sort()) {
      if (!known.has(name)) missing.push([`parameter ${ref.name}`, name]);
    }
  }
  for (const ref of graph.fields) {
    for (const name of [...ref.reads].sort()) {
      if (!known.has(name)) missing.push([ref.name, name]);
    }
  }
  return missing;
}

export function cycles(graph) {
  const colour = new Map();
  const stack = [];
  const found = [];

  const visit = (name) => {
    colour.set(name, 1);
    stack.push(name);
    for (const read of [...graph.parameters.get(name).reads].sort()) {
      if (!graph.parameters.has(read)) continue;
      const state = colour.get(read) || 0;
      if (state === 0) visit(read);
      else if (state === 1) found.push([...stack.slice(stack.indexOf(read)), read]);
    }
    stack.pop();
    colour.set(name, 2);
  };

  for (const name of [...graph.parameters.keys()].sort()) {
    if (!(colour.get(name) || 0)) visit(name);
  }
  return found;
}

export function roots(graph) {
  return [...graph.parameters.values()].filter((ref) => !ref.reads.size).map((ref) => ref.name);
}
