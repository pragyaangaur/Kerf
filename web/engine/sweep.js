// Driving a parameter through a range and watching what breaks.
//
// Every guide to parametric CAD gives the same advice. After writing your
// equations, change each variable across the range you expect and check the
// model still rebuilds, because equations that work at the nominal value
// often fail at the extremes. Almost nobody does it, because by hand it means
// typing a number, waiting for a rebuild, and reading the tree, over and over.

import { clonePart } from './part.js';
import { checkPart, measureSolid } from './validity.js';

export function defaultRange(value, spread = 0.6) {
  const magnitude = Math.abs(value) || 1;
  return [Math.max(value - magnitude * spread, magnitude * 0.05), value + magnitude * spread];
}

export function sweepParameter(part, name, start, stop, steps = 11, resolution = 22) {
  const nominal = typeof part.parameters[name] === 'number' ? part.parameters[name] : null;
  const count = Math.max(2, steps);
  const points = [];

  for (let index = 0; index < count; index += 1) {
    const value = start + ((stop - start) * index) / (count - 1);
    const trial = clonePart(part);
    trial.parameters[name] = value;
    const issues = checkPart(trial, { resolution });
    const errors = issues.filter((item) => item.severity === 'error');
    let volume = null;
    let bodies = 0;
    if (!errors.length) {
      const measured = measureSolid(trial, resolution);
      volume = measured.volume;
      bodies = measured.bodies;
    }
    points.push({ value, ok: !errors.length, volume, bodies, issues });
  }

  return { parameter: name, nominal, points };
}

export function failures(result) {
  return result.points.filter((point) => !point.ok);
}

export function warnings(result) {
  return result.points.filter(
    (point) => point.ok && point.issues.some((item) => item.severity === 'warning'),
  );
}

// The unbroken span around the value the part shipped with. A part that fails
// in the middle of its range and works at both ends has no single span to
// quote, and the failure list says so instead.
export function workingRange(result) {
  const { points } = result;
  if (!points.some((point) => point.ok)) return null;
  let index = 0;
  if (result.nominal !== null) {
    let best = Infinity;
    points.forEach((point, i) => {
      const distance = Math.abs(point.value - result.nominal);
      if (distance < best) { best = distance; index = i; }
    });
  }
  if (!points[index].ok) return null;
  let low = index;
  let high = index;
  while (low > 0 && points[low - 1].ok) low -= 1;
  while (high < points.length - 1 && points[high + 1].ok) high += 1;
  return [points[low].value, points[high].value];
}

export function summarise(result) {
  const broken = failures(result);
  const warned = warnings(result);
  let note = '';
  if (warned.length) {
    const detail = warned[0].issues.find((i) => i.severity === 'warning');
    note = `, and at ${format(warned[0].value)} the part ${detail ? detail.message : 'looks wrong'}`;
  }
  if (!broken.length) {
    const first = format(result.points[0].value);
    const last = format(result.points[result.points.length - 1].value);
    return `builds across ${first} to ${last}${note}`;
  }
  const span = workingRange(result);
  if (!span) return 'fails at every value tried';
  return `builds from ${format(span[0])} to ${format(span[1])}, `
    + `and ${broken.length} of ${result.points.length} values fail${note}`;
}

function format(value) {
  return Number(value.toFixed(2)).toString();
}
