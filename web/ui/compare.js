// The edit and compare tab.
//
// One part is held twice: the committed revision and the working copy. Every
// edit to the working copy re-evaluates both and shows the difference, which
// is the whole idea of kerf reduced to something you can drag.

import { clonePart, evaluatePart, parsePart, sharedGridFor } from '../engine/part.js';
import { classifyTriangles, diffParts, diffVolumes, isEmptyDiff } from '../engine/diff.js';
import { buildFeatureList, buildParameterControls } from './controls.js';
import { clear, element, number, percent, vector, volume } from './format.js';

export function createCompareTab(context) {
  const { viewer, catalog, loadPart } = context;
  const slot = document.getElementById('viewer-slot');
  const picker = document.getElementById('part-picker');
  const summary = document.getElementById('part-summary');
  const badge = document.getElementById('revision-badge');
  const controls = document.getElementById('parameter-controls');
  const features = document.getElementById('feature-list');
  const diffBody = document.getElementById('diff-body');
  const diffStatus = document.getElementById('diff-status');

  const state = {
    entry: null,
    baseline: null,
    working: null,
    revision: 1,
    mode: 'changes',
    pending: false,
  };

  for (const entry of catalog.parts) {
    const option = element('option', null, entry.name);
    option.value = entry.id;
    picker.appendChild(option);
  }

  picker.addEventListener('change', () => selectPart(picker.value));
  document.getElementById('reset-btn').addEventListener('click', () => {
    state.working = clonePart(state.baseline);
    rebuildControls();
    schedule(true);
  });
  document.getElementById('commit-btn').addEventListener('click', () => {
    state.baseline = clonePart(state.working);
    state.revision += 1;
    badge.textContent = `at revision ${state.revision}`;
    schedule(true);
  });
  document.getElementById('recentre').addEventListener('click', () => viewer.recentre());

  for (const button of document.querySelectorAll('#view-modes [data-mode]')) {
    button.addEventListener('click', () => {
      state.mode = button.dataset.mode;
      for (const other of document.querySelectorAll('#view-modes [data-mode]')) {
        other.setAttribute('aria-pressed', String(other === button));
      }
      schedule();
    });
  }

  async function selectPart(id) {
    const entry = catalog.parts.find((item) => item.id === id) || catalog.parts[0];
    const document_ = await loadPart(entry);
    state.entry = entry;
    state.baseline = parsePart(document_);
    state.working = clonePart(state.baseline);
    state.revision = 1;
    badge.textContent = 'at revision 1';
    summary.textContent = document_.meta?.summary || '';
    viewer.framed = false;
    rebuildControls();
    schedule(true);
  }

  function rebuildControls() {
    let resolved = {};
    try {
      resolved = evaluatePart(state.working, 8).params;
    } catch {
      resolved = {};
    }
    buildParameterControls(controls, state.working, resolved, (name, value) => {
      state.working.parameters[name] = value;
      schedule();
    });
    buildFeatureList(features, state.working, (id, suppressed) => {
      const feature = state.working.features.find((item) => item.id === id);
      feature.suppressed = suppressed;
      rebuildControls();
      schedule();
    });
  }

  // Redraw on the next frame rather than on every input event, so dragging a
  // slider does not queue up more work than the browser can finish.
  function schedule(refit = false) {
    if (state.pending) return;
    state.pending = true;
    requestAnimationFrame(() => {
      state.pending = false;
      try {
        render(refit);
      } catch (error) {
        showError(error);
      }
    });
  }

  function showError(error) {
    clear(diffBody).appendChild(
      element('p', 'conflict-detail', `This part cannot be evaluated: ${error.message}`),
    );
    diffStatus.textContent = 'error';
    diffStatus.className = 'badge is-conflict';
  }

  function render(refit) {
    const resolution = state.entry.resolution || 40;
    const grid = sharedGridFor([state.baseline, state.working], resolution);
    const before = evaluatePart(state.baseline, resolution, grid);
    const after = evaluatePart(state.working, resolution, grid);

    const newSurface = classifyTriangles(after.mesh, before.occupancy, grid);
    const goneSurface = classifyTriangles(before.mesh, after.occupancy, grid);

    const layers = [];
    if (state.mode === 'before') {
      layers.push({ positions: before.mesh.positions, indices: before.mesh.indices, color: 'neutral' });
    } else if (state.mode === 'after') {
      layers.push({ positions: after.mesh.positions, indices: after.mesh.indices, color: 'neutral' });
    } else if (state.mode === 'ghost') {
      layers.push({ positions: after.mesh.positions, indices: after.mesh.indices, color: 'neutral' });
      layers.push({
        positions: before.mesh.positions, indices: before.mesh.indices,
        color: 'removed', alpha: 0.22,
      });
    } else {
      layers.push({ positions: after.mesh.positions, indices: newSurface.shared, color: 'neutral' });
      layers.push({ positions: after.mesh.positions, indices: newSurface.only, color: 'added' });
      layers.push({ positions: before.mesh.positions, indices: goneSurface.only, color: 'removed' });
    }

    const bounds = [grid.origin, grid.origin.map((v, axis) => v + grid.dims[axis] * grid.pitch)];
    viewer.setLayers(layers, bounds, refit);

    const tree = diffParts(state.baseline, state.working);
    const volumes = diffVolumes(before.occupancy, after.occupancy, grid);
    renderDiff(tree, volumes, before.stats, after.stats);
  }

  function renderDiff(tree, volumes, beforeStats, afterStats) {
    const host = clear(diffBody);
    const treeEmpty = isEmptyDiff(tree);

    if (treeEmpty && volumes.unchanged) {
      diffStatus.textContent = 'no change';
      diffStatus.className = 'badge';
      host.appendChild(element(
        'p', 'empty-note',
        'The working copy matches the committed revision. Move a parameter or '
        + 'turn a feature off to see what kerf reports.',
      ));
      return;
    }

    diffStatus.textContent = treeEmpty ? 'geometry changed' : 'modified';
    diffStatus.className = 'badge is-changed';

    if (tree.parameters.length || Object.keys(tree.parametersAdded).length
        || Object.keys(tree.parametersRemoved).length) {
      const section = element('div', 'readout');
      section.appendChild(element('h3', null, 'Parameters'));
      for (const change of tree.parameters) {
        const line = element('div', 'line');
        line.appendChild(element('span', 'key', change.key));
        line.appendChild(element('span', 'change', `${change.before} → ${change.after}`));
        if (change.pct !== null) {
          const chip = element('span', `chip ${change.pct >= 0 ? 'chip-up' : 'chip-down'}`);
          chip.textContent = percent(change.pct);
          line.appendChild(chip);
        }
        section.appendChild(line);
        const driven = tree.impact[change.key];
        if (driven && driven.length) {
          const shown = driven.slice(0, 3).join(', ');
          const extra = driven.length > 3 ? ` and ${driven.length - 3} more` : '';
          section.appendChild(element('p', 'impact', `drives ${shown}${extra}`));
        }
      }
      host.appendChild(section);
    }

    if (tree.features.length) {
      const section = element('div', 'readout');
      section.appendChild(element('h3', null, 'Features'));
      for (const change of tree.features) {
        const row = element('div', `feat feat-${change.status}`);
        row.appendChild(element('span', 'feat-mark'));
        const body = element('div');
        const head = element('p');
        head.appendChild(element('span', 'feat-name', change.label));
        head.appendChild(element('span', 'feat-status', change.status));
        body.appendChild(head);
        for (const field of change.changes.slice(0, 4)) {
          body.appendChild(element(
            'p', 'feat-fields',
            `${field.key}: ${field.before ?? '—'} → ${field.after ?? '—'}`,
          ));
        }
        row.appendChild(body);
        section.appendChild(row);
      }
      host.appendChild(section);
    }

    const section = element('div', 'readout');
    section.appendChild(element('h3', null, 'Where material changed'));
    const total = Math.max(volumes.commonVolume + volumes.addedVolume + volumes.removedVolume, 1e-9);
    const bar = element('div', 'vbar');
    for (const [name, value] of [
      ['vbar-kept', volumes.commonVolume],
      ['vbar-add', volumes.addedVolume],
      ['vbar-rem', volumes.removedVolume],
    ]) {
      const piece = element('span', name);
      piece.style.width = `${(value / total) * 100}%`;
      bar.appendChild(piece);
    }
    section.appendChild(bar);

    const key = element('p', 'vbar-key');
    key.innerHTML = '';
    const legend = [
      ['dot-kept', `unchanged ${volume(volumes.commonVolume)}`],
      ['dot-added', `added ${volume(volumes.addedVolume)}`],
      ['dot-removed', `removed ${volume(volumes.removedVolume)}`],
    ];
    for (const [dot, text] of legend) {
      const item = element('span');
      item.appendChild(element('span', `dot ${dot}`));
      item.appendChild(document.createTextNode(text));
      key.appendChild(item);
    }
    section.appendChild(key);

    if (volumes.regions.length) {
      const table = element('table', 'readout-table');
      const head = element('tr');
      for (const label of ['Region', 'Volume', 'Centre', 'Extent']) {
        const cell = element(label === 'Region' ? 'th' : 'td', null, label);
        head.appendChild(cell);
      }
      table.appendChild(head);
      for (const region of volumes.regions.slice(0, 5)) {
        const row = element('tr');
        row.appendChild(element('th', null, region.kind));
        row.appendChild(element('td', null, volume(region.volume)));
        row.appendChild(element('td', null, vector(region.centroid)));
        row.appendChild(element('td', null, vector(region.size)));
        table.appendChild(row);
      }
      section.appendChild(table);
    }

    if (volumes.noiseCells) {
      section.appendChild(element(
        'p', 'fineprint',
        `${volumes.noiseCells} boundary cells differ by less than one `
        + `${volumes.pitch.toFixed(2)} mm cell, so they are counted as measurement noise.`,
      ));
    }
    host.appendChild(section);

    const table = element('table', 'readout-table');
    const rows = [
      ['Volume mm³', beforeStats.volume, afterStats.volume],
      ['Surface mm²', beforeStats.area, afterStats.area],
      ['Triangles', beforeStats.triangles, afterStats.triangles],
      ['Features', beforeStats.activeFeatures, afterStats.activeFeatures],
    ];
    const head = element('tr');
    head.appendChild(element('th', null, ''));
    head.appendChild(element('td', null, 'before'));
    head.appendChild(element('td', null, 'after'));
    table.appendChild(head);
    for (const [label, before, after] of rows) {
      const row = element('tr');
      row.appendChild(element('th', null, label));
      row.appendChild(element('td', null, number(before)));
      row.appendChild(element('td', null, number(after)));
      table.appendChild(row);
    }
    const measurements = element('div', 'readout');
    measurements.appendChild(element('h3', null, 'Measurements'));
    measurements.appendChild(table);
    host.appendChild(measurements);
  }

  return {
    id: 'compare',
    slot,
    async activate() {
      if (!state.entry) await selectPart(catalog.parts[0].id);
      else schedule();
    },
  };
}
