// The re-export tab.
//
// The claim is that a CAD export writes a different file every time while
// describing the same solid. Rather than asserting it, the page exports the
// part twice, compares the bytes, and then asks kerf the same question.

import { clonePart, evaluatePart, parsePart } from '../engine/part.js';
import { equivalent, geometryHash } from '../engine/fingerprint.js';
import { countDifferentBytes, reexport, writeBinaryStl } from '../engine/stl.js';
import { bytes, clear, element } from './format.js';

export function createReexportTab(context) {
  const { viewer, catalog, loadPart } = context;
  const slot = document.getElementById('reexport-viewer-slot');
  const picker = document.getElementById('reexport-picker');
  const body = document.getElementById('reexport-body');
  const status = document.getElementById('reexport-status');

  const state = { entry: null, part: null, evaluated: null, seed: 1 };

  for (const entry of catalog.parts) {
    const option = element('option', null, entry.name);
    option.value = entry.id;
    picker.appendChild(option);
  }

  picker.addEventListener('change', () => select(picker.value));
  document.getElementById('reexport-btn').addEventListener('click', () => compare('same'));
  document.getElementById('toolchain-btn').addEventListener('click', () => compare('toolchain'));
  document.getElementById('real-edit-btn').addEventListener('click', () => compare('edit'));

  async function select(id) {
    const entry = catalog.parts.find((item) => item.id === id) || catalog.parts[0];
    state.entry = entry;
    state.part = parsePart(await loadPart(entry));
    state.evaluated = evaluatePart(state.part, entry.resolution || 40);
    viewer.framed = false;
    draw(state.evaluated);
    clear(body).appendChild(element(
      'p', 'empty-note', 'Press export to write the file a second time.',
    ));
    status.textContent = 'waiting';
    status.className = 'badge';
  }

  function draw(evaluated) {
    viewer.setLayers(
      [{ positions: evaluated.mesh.positions, indices: evaluated.mesh.indices, color: 'neutral' }],
      [evaluated.grid.origin, evaluated.grid.origin.map(
        (value, axis) => value + evaluated.grid.dims[axis] * evaluated.grid.pitch,
      )],
    );
  }

  // Three cases, because the identity check has two layers and both are worth
  // seeing. A deterministic exporter reorders facets and stamps the header,
  // and the geometry id alone settles that. A different toolchain also leaves
  // float noise behind, and then the tolerance comparison settles it. A real
  // edit has to come out different under both, or the whole idea is useless.
  async function compare(mode) {
    if (!state.evaluated) return;
    const first = state.evaluated.mesh;
    const realEdit = mode === 'edit';
    let second;
    let headline;

    if (realEdit) {
      const edited = clonePart(state.part);
      const name = Object.keys(edited.parameters)[0];
      if (name !== undefined && typeof edited.parameters[name] === 'number') {
        edited.parameters[name] = Number((edited.parameters[name] * 1.04).toFixed(3));
        headline = `${name} moved by four percent`;
      } else {
        edited.features[0].suppressed = true;
        headline = 'the first feature was suppressed';
      }
      second = evaluatePart(edited, state.entry.resolution || 40).mesh;
    } else if (mode === 'toolchain') {
      state.seed += 1;
      second = reexport(first, state.seed, 2e-6);
      headline = 'the same part, written by a different toolchain';
    } else {
      state.seed += 1;
      second = reexport(first, state.seed, 0);
      headline = 'the same part, exported a second time by the same tool';
    }

    const firstBytes = writeBinaryStl(first, 'export one');
    const secondBytes = writeBinaryStl(second, `export two ${Date.now()}`);
    const byteReport = countDifferentBytes(firstBytes, secondBytes);
    const [firstHash, secondHash] = await Promise.all([
      geometryHash(first), geometryHash(second),
    ]);
    const check = equivalent(first, second);

    render({ headline, byteReport, firstHash, secondHash, check, realEdit, firstBytes });
  }

  function render(report) {
    const host = clear(body);
    const changedShare = (report.byteReport.different / report.byteReport.total) * 100;

    host.appendChild(element('p', 'summary', report.headline));

    const git = element('div', 'verdict verdict-git');
    git.appendChild(element('h4', null, 'What a byte comparison says'));
    git.appendChild(element('p', 'figure', `${changedShare.toFixed(0)}% of the file differs`));
    git.appendChild(element(
      'p', null,
      `${bytes(report.byteReport.different)} of ${bytes(report.byteReport.total)} changed. `
      + 'A version control system that compares bytes reports the whole part as rewritten.',
    ));
    host.appendChild(git);

    const same = report.check.same;
    const kerf = element('div', `verdict ${same ? 'verdict-kerf' : 'verdict-git'}`);
    kerf.appendChild(element('h4', null, 'What kerf says'));
    kerf.appendChild(element(
      'p', 'figure',
      same ? 'no design change' : 'the solid changed',
    ));
    if (same) {
      kerf.appendChild(element(
        'p', null,
        `Every vertex moved by at most ${report.check.deviation.toExponential(2)} mm, which is `
        + `${((report.check.deviation / report.check.diagonal) * 1e6).toFixed(0)} parts per million `
        + 'of the part. Nobody edited this model.',
      ));
    } else {
      kerf.appendChild(element(
        'p', null,
        'The shapes do not agree within tolerance, so this is real work and it '
        + 'belongs in the history.',
      ));
    }
    host.appendChild(kerf);

    const hashes = element('div', 'readout');
    hashes.appendChild(element('h3', null, 'Geometry id'));
    const table = element('table', 'readout-table');
    for (const [label, value] of [['first export', report.firstHash], ['second', report.secondHash]]) {
      const row = element('tr');
      row.appendChild(element('th', null, label));
      row.appendChild(element('td', null, `${value.slice(0, 24)}…`));
      table.appendChild(row);
    }
    hashes.appendChild(table);
    hashes.appendChild(element(
      'p', 'fineprint',
      report.firstHash === report.secondHash
        ? 'The two exports hash to the same value. The hash is taken over the canonical '
          + 'form of the solid, so facet order and the header never reach it.'
        : report.realEdit
          ? 'The hashes differ because the solid differs. That is the answer you want here.'
          : 'The hashes differ, because the float noise crossed the rounding step the hash '
            + 'uses. This is the case the tolerance comparison above exists for.',
    ));
    host.appendChild(hashes);

    status.textContent = same ? 'no design change' : 'real change';
    status.className = `badge ${same ? 'is-clean' : 'is-conflict'}`;
  }

  return {
    id: 'reexport',
    slot,
    async activate() {
      if (!state.entry) await select(catalog.parts[0].id);
      else draw(state.evaluated);
    },
  };
}
