// The merge tab.
//
// Two branches start from the same ancestor. The merge runs feature by
// feature, and the interesting case is the one where that succeeds and the
// resulting part is still wrong, which is what the interference check finds.

import { clonePart, evaluatePart, parsePart } from '../engine/part.js';
import { mergeParts } from '../engine/merge.js';
import { BRANCHES, branchById } from './branches.js';
import { clear, element } from './format.js';

export function createMergeTab(context) {
  const { viewer, catalog, loadPart } = context;
  const slot = document.getElementById('merge-viewer-slot');
  const oursPicker = document.getElementById('ours-picker');
  const theirsPicker = document.getElementById('theirs-picker');
  const toggle = document.getElementById('interference-toggle');
  const body = document.getElementById('merge-body');
  const status = document.getElementById('merge-status');

  const state = { base: null, result: null, view: 'merged', parts: {} };

  for (const picker of [oursPicker, theirsPicker]) {
    for (const branch of BRANCHES) {
      const option = element('option', null, branch.name);
      option.value = branch.id;
      picker.appendChild(option);
    }
  }
  oursPicker.value = 'mount-slots';
  theirsPicker.value = 'cable-tie';

  document.getElementById('merge-btn').addEventListener('click', () => run());
  document.getElementById('merge-recentre').addEventListener('click', () => viewer.recentre());
  for (const picker of [oursPicker, theirsPicker]) {
    picker.addEventListener('change', () => run());
  }
  toggle.addEventListener('change', () => run());

  for (const button of document.querySelectorAll('#merge-modes [data-merge-view]')) {
    button.addEventListener('click', () => {
      state.view = button.dataset.mergeView;
      for (const other of document.querySelectorAll('#merge-modes [data-merge-view]')) {
        other.setAttribute('aria-pressed', String(other === button));
      }
      draw();
    });
  }

  function branchPart(branch) {
    const part = clonePart(state.base);
    branch.apply(part);
    return part;
  }

  function run() {
    if (!state.base) return;
    const ours = branchById(oursPicker.value);
    const theirs = branchById(theirsPicker.value);
    state.parts = {
      base: state.base,
      ours: branchPart(ours),
      theirs: branchPart(theirs),
    };
    state.result = mergeParts(
      state.base, state.parts.ours, state.parts.theirs, toggle.checked,
    );
    state.parts.merged = state.result.merged;
    render(ours, theirs);
    draw();
  }

  function draw() {
    const part = state.parts[state.view] || state.parts.merged;
    if (!part) return;
    let evaluated;
    try {
      evaluated = evaluatePart(part, 40);
    } catch (error) {
      clear(body).appendChild(element('p', 'conflict-detail', error.message));
      return;
    }
    viewer.setLayers(
      [{ positions: evaluated.mesh.positions, indices: evaluated.mesh.indices, color: 'neutral' }],
      [evaluated.grid.origin, evaluated.grid.origin.map(
        (value, axis) => value + evaluated.grid.dims[axis] * evaluated.grid.pitch,
      )],
    );
  }

  function render(ours, theirs) {
    const host = clear(body);
    const result = state.result;

    const stories = element('div', 'readout');
    stories.appendChild(element('h3', null, 'What each person did'));
    stories.appendChild(element('p', 'note-item', `Ours: ${ours.story}`));
    stories.appendChild(element('p', 'note-item', `Theirs: ${theirs.story}`));
    host.appendChild(stories);

    if (result.clean) {
      status.textContent = 'merged cleanly';
      status.className = 'badge is-clean';
    } else {
      const onlyInterference = result.conflicts.every((item) => item.scope === 'interference');
      status.textContent = onlyInterference ? 'geometry collides' : 'conflict';
      status.className = 'badge is-conflict';
    }

    if (result.conflicts.length) {
      const section = element('div', 'readout');
      const count = result.conflicts.length;
      section.appendChild(element('h3', null, count === 1 ? '1 conflict' : `${count} conflicts`));
      for (const conflict of result.conflicts) {
        const box = element('div', 'conflict');
        box.appendChild(element('p', 'conflict-key', `${conflict.scope}: ${conflict.key}`));
        box.appendChild(element(
          'p', 'conflict-detail',
          conflict.detail
          || `ours ${JSON.stringify(conflict.ours)}, theirs ${JSON.stringify(conflict.theirs)}, ancestor ${JSON.stringify(conflict.base)}`,
        ));
        section.appendChild(box);
      }
      if (result.interference.length) {
        section.appendChild(element(
          'p', 'fineprint',
          'The feature trees merged with no disagreement. The conflict above '
          + 'comes from evaluating the merged part and finding that the two '
          + 'sets of changes occupy the same space. A text merge has no way to '
          + 'see this.',
        ));
      }
      host.appendChild(section);
    }

    if (result.notes.length) {
      const section = element('div', 'readout');
      section.appendChild(element('h3', null, 'What the merge did'));
      for (const note of result.notes) section.appendChild(element('p', 'note-item', note));
      host.appendChild(section);
    }

    if (result.clean && !result.notes.length) {
      host.appendChild(element(
        'p', 'empty-note',
        'Nothing to combine. The two branches made the same part.',
      ));
    }

    const summary = element('div', 'readout');
    summary.appendChild(element('h3', null, 'Merged tree'));
    summary.appendChild(element(
      'p', 'note-item',
      `${result.merged.features.length} features, `
      + `${Object.keys(result.merged.parameters).length} parameters`,
    ));
    host.appendChild(summary);
  }

  return {
    id: 'merge',
    slot,
    async activate() {
      if (!state.base) {
        const entry = catalog.parts.find((item) => item.id === 'bracket') || catalog.parts[0];
        state.base = parsePart(await loadPart(entry));
        viewer.framed = false;
        run();
      } else {
        draw();
      }
    },
  };
}
