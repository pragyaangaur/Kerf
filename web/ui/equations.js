// The equations tab.
//
// A CAD model is held together by equations, and this is where you can pull
// on them. Rewrite one and the part rebuilds. Drive one across a range and
// the chart shows the volume it produces and the values where the part stops
// building at all.

import { clonePart, evaluatePart, parsePart, resolvedParameters } from '../engine/part.js';
import { buildGraph, featureReadersOf } from '../engine/graph.js';
import { checkPart } from '../engine/validity.js';
import { defaultRange, failures, sweepParameter, summarise, warnings } from '../engine/sweep.js';
import { clear, element, number, volume } from './format.js';

export function createEquationsTab(context) {
  const { viewer, catalog, loadPart } = context;
  const slot = document.getElementById('equations-viewer-slot');
  const picker = document.getElementById('equation-part-picker');
  const list = document.getElementById('equation-list');
  const issueBox = document.getElementById('equation-issues');
  const sweepPicker = document.getElementById('sweep-parameter');
  const fromInput = document.getElementById('sweep-from');
  const toInput = document.getElementById('sweep-to');
  const chartHost = document.getElementById('sweep-chart');
  const sweepNote = document.getElementById('sweep-note');
  const caption = document.getElementById('equations-caption');

  const state = { entry: null, part: null, shown: null, sweep: null };

  for (const entry of catalog.parts) {
    const option = element('option', null, entry.name);
    option.value = entry.id;
    picker.appendChild(option);
  }

  picker.addEventListener('change', () => select(picker.value));
  sweepPicker.addEventListener('change', () => {
    resetRange();
    runSweep();
  });
  for (const input of [fromInput, toInput]) {
    input.addEventListener('change', () => runSweep());
  }
  document.getElementById('sweep-run').addEventListener('click', () => runSweep());
  document.getElementById('equations-reset').addEventListener('click', () => select(picker.value));

  async function select(id) {
    const entry = catalog.parts.find((item) => item.id === id) || catalog.parts[0];
    const document_ = await loadPart(entry);
    state.entry = entry;
    state.part = parsePart(document_);
    viewer.framed = false;
    rebuild(true);
    resetSweepChoices();
    resetRange();
    runSweep();
  }

  function resetSweepChoices() {
    clear(sweepPicker);
    for (const [name, raw] of Object.entries(state.part.parameters)) {
      if (typeof raw !== 'number') continue;
      const option = element('option', null, name);
      option.value = name;
      sweepPicker.appendChild(option);
    }
  }

  function resetRange() {
    const name = sweepPicker.value;
    const raw = state.part.parameters[name];
    if (typeof raw !== 'number') return;
    const [low, high] = defaultRange(raw, 0.8);
    fromInput.value = String(Number(low.toFixed(2)));
    toInput.value = String(Number(high.toFixed(2)));
  }

  // Render the part at a given parameter value without disturbing the
  // document, so hovering a point on the chart is a preview rather than an
  // edit.
  function draw(part, label) {
    let evaluated;
    try {
      evaluated = evaluatePart(part, state.entry.resolution || 40);
    } catch (error) {
      caption.textContent = error.message;
      return;
    }
    viewer.setLayers(
      [{ positions: evaluated.mesh.positions, indices: evaluated.mesh.indices, color: 'neutral' }],
      [evaluated.grid.origin, evaluated.grid.origin.map(
        (value, axis) => value + evaluated.grid.dims[axis] * evaluated.grid.pitch,
      )],
    );
    caption.textContent = label;
  }

  function rebuild(refit = false) {
    const issues = checkPart(state.part, { resolution: 22 });
    renderList(issues);
    renderIssues(issues);
    if (!issues.some((item) => item.severity === 'error')) {
      const stats = evaluatePart(state.part, 8);
      draw(state.part, `as written, ${volume(measured())} of material`);
      if (refit) viewer.recentre();
      void stats;
    }
  }

  function measured() {
    try {
      const evaluated = evaluatePart(state.part, state.entry.resolution || 40);
      return evaluated.stats.volume;
    } catch {
      return 0;
    }
  }

  function renderList(issues) {
    const host = clear(list);
    const graph = buildGraph(state.part);
    let values = {};
    try {
      values = resolvedParameters(state.part);
    } catch {
      values = {};
    }
    // An equation issue names its home as "parameter bolt_d" or as a field
    // such as "hole.center.x". Only the first kind marks an input here.
    const broken = new Set(
      issues
        .filter((item) => item.scope === 'equation' && item.where.startsWith('parameter '))
        .map((item) => item.where.slice('parameter '.length)),
    );
    for (const item of issues) {
      if (item.scope === 'equation' && item.where.includes(' → ')) {
        for (const name of item.where.split(' → ')) broken.add(name.trim());
      }
    }

    for (const [name, raw] of Object.entries(state.part.parameters)) {
      const row = element('div', 'equation-row');
      const label = element('label', 'equation-name mono', name);
      label.setAttribute('for', `equation-${name}`);

      const input = element('input', 'equation-input mono');
      input.type = 'text';
      input.id = `equation-${name}`;
      input.value = String(raw);
      input.spellcheck = false;
      if (broken.has(name)) input.classList.add('is-broken');
      input.addEventListener('change', () => {
        const text = input.value.trim();
        const asNumber = Number(text);
        state.part.parameters[name] = text !== '' && Number.isFinite(asNumber) ? asNumber : text;
        rebuild();
        resetSweepChoices();
        runSweep();
      });

      const resolvedValue = values[name];
      const shown = element(
        'span', 'equation-value mono',
        resolvedValue === undefined ? '—' : number(resolvedValue, 3),
      );

      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(shown);

      const drives = featureReadersOf(graph, name);
      if (drives.length) {
        const listed = drives.slice(0, 3).join(', ');
        const extra = drives.length > 3 ? ` and ${drives.length - 3} more` : '';
        row.appendChild(element('span', 'equation-drives', `drives ${listed}${extra}`));
      } else {
        row.appendChild(element('span', 'equation-drives', 'drives nothing'));
      }
      host.appendChild(row);
    }
  }

  function renderIssues(issues) {
    const host = clear(issueBox);
    if (!issues.length) {
      host.appendChild(element('p', 'ok-note', 'Every equation resolves and the part builds.'));
      return;
    }
    for (const item of issues) {
      const row = element('div', `issue issue-${item.severity}`);
      row.appendChild(element('span', 'issue-where mono', item.where));
      row.appendChild(element('span', 'issue-message', item.message));
      host.appendChild(row);
    }
  }

  function runSweep() {
    const name = sweepPicker.value;
    if (!name || !state.part) return;
    const start = Number(fromInput.value);
    const stop = Number(toInput.value);
    if (!Number.isFinite(start) || !Number.isFinite(stop) || start === stop) return;

    let result;
    try {
      result = sweepParameter(state.part, name, start, stop, 13, 20);
    } catch (error) {
      clear(chartHost);
      sweepNote.textContent = error.message;
      return;
    }
    state.sweep = result;
    renderChart(result);
    const broken = failures(result);
    const warned = warnings(result);
    sweepNote.textContent = `${name} ${summarise(result)}`;
    sweepNote.className = broken.length ? 'sweep-note is-bad'
      : warned.length ? 'sweep-note is-warn' : 'sweep-note is-good';
  }

  function renderChart(result) {
    const host = clear(chartHost);
    const width = 460;
    const height = 150;
    const padding = { left: 6, right: 6, top: 10, bottom: 22 };
    const usable = width - padding.left - padding.right;
    const columns = result.points.length;
    const barWidth = Math.max(6, (usable / columns) * 0.68);
    const top = Math.max(...result.points.map((p) => p.volume || 0), 1);

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label',
      `Volume of the part as ${result.parameter} changes, with failing values marked`);
    svg.classList.add('chart');

    const make = (tag, attrs) => {
      const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
      for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
      return node;
    };

    const floor = height - padding.bottom;
    svg.appendChild(make('line', {
      x1: padding.left, y1: floor + 0.5, x2: width - padding.right, y2: floor + 0.5,
      class: 'chart-axis',
    }));

    result.points.forEach((point, index) => {
      const centre = padding.left + (usable / columns) * (index + 0.5);
      const x = centre - barWidth / 2;
      const warned = point.issues.some((item) => item.severity === 'warning');
      if (!point.ok) {
        svg.appendChild(make('rect', {
          x, y: floor - 12, width: barWidth, height: 12, class: 'chart-bar is-fail',
        }));
        svg.appendChild(make('text', {
          x: centre, y: floor - 16, 'text-anchor': 'middle', class: 'chart-fail-mark',
        })).textContent = '×';
      } else {
        const barHeight = Math.max(2, ((point.volume || 0) / top) * (floor - padding.top));
        svg.appendChild(make('rect', {
          x, y: floor - barHeight, width: barWidth, height: barHeight,
          class: `chart-bar${warned ? ' is-warn' : ''}`,
        }));
      }

      if (index === 0 || index === columns - 1 || index === Math.floor(columns / 2)) {
        const text = make('text', {
          x: centre, y: height - 6, 'text-anchor': 'middle', class: 'chart-label',
        });
        text.textContent = Number(point.value.toFixed(1));
        svg.appendChild(text);
      }

      const hit = make('rect', {
        x: centre - (usable / columns) / 2, y: padding.top,
        width: usable / columns, height: floor - padding.top, class: 'chart-hit',
      });
      const describe = point.ok
        ? `${result.parameter} = ${Number(point.value.toFixed(2))}, ${volume(point.volume || 0)}`
        : `${result.parameter} = ${Number(point.value.toFixed(2))}, will not build`;
      hit.addEventListener('mouseenter', () => preview(point, describe));
      hit.addEventListener('focus', () => preview(point, describe));
      hit.setAttribute('tabindex', '0');
      const title = make('title', {});
      title.textContent = describe;
      hit.appendChild(title);
      svg.appendChild(hit);
    });

    host.appendChild(svg);
  }

  function preview(point, describe) {
    if (!point.ok) {
      caption.textContent = describe;
      return;
    }
    const trial = clonePart(state.part);
    trial.parameters[state.sweep.parameter] = point.value;
    draw(trial, describe);
  }

  return {
    id: 'equations',
    slot,
    async activate() {
      if (!state.entry) await select(catalog.parts[0].id);
      else rebuild();
    },
  };
}
