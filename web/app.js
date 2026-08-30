// Boot the playground.
//
// One WebGL canvas is shared by every tab, because three live contexts would
// cost three times as much for no gain. The canvas moves into whichever tab
// is showing.

import { Viewer } from './viewer/renderer.js';
import { createCompareTab } from './ui/compare.js';
import { createMergeTab } from './ui/merge.js';
import { createReexportTab } from './ui/reexport.js';

const partCache = new Map();

async function loadPart(entry) {
  if (!partCache.has(entry.file)) {
    const response = await fetch(entry.file);
    if (!response.ok) throw new Error(`cannot load ${entry.file}`);
    partCache.set(entry.file, await response.json());
  }
  return structuredClone(partCache.get(entry.file));
}

function paletteFromCss() {
  const styles = getComputedStyle(document.documentElement);
  const read = (name, fallback) => {
    const value = (styles.getPropertyValue(name) || fallback).trim() || fallback;
    const hex = value.replace('#', '');
    const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
    return [0, 2, 4].map((offset) => parseInt(full.slice(offset, offset + 2), 16) / 255);
  };
  return {
    neutral: read('--muted', '#6f7b74'),
    added: read('--added', '#1c7f59'),
    removed: read('--removed', '#b73f2f'),
    rim: read('--surface', '#ffffff'),
    grid: read('--rule-strong', '#b6bfb8'),
  };
}

async function boot() {
  const catalog = await (await fetch('parts/index.json')).json();

  const canvas = document.createElement('canvas');
  const viewer = new Viewer(canvas);
  viewer.setPalette(paletteFromCss());

  if (!viewer.supported) {
    for (const slot of document.querySelectorAll('.viewer-slot')) {
      slot.textContent = 'This browser cannot draw the 3D view. The measurements still work.';
      slot.classList.add('empty-note');
    }
  }

  if (window.matchMedia) {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const refresh = () => viewer.setPalette(paletteFromCss());
    if (query.addEventListener) query.addEventListener('change', refresh);
  }

  const context = { viewer, catalog, loadPart };
  const tabs = [createCompareTab(context), createMergeTab(context), createReexportTab(context)];
  const byId = new Map(tabs.map((tab) => [tab.id, tab]));

  async function show(id) {
    for (const button of document.querySelectorAll('.tabs [data-tab]')) {
      button.setAttribute('aria-selected', String(button.dataset.tab === id));
    }
    for (const panel of document.querySelectorAll('[data-panel]')) {
      panel.hidden = panel.dataset.panel !== id;
    }
    const tab = byId.get(id);
    if (viewer.supported) tab.slot.appendChild(canvas);
    await tab.activate();
    viewer.dirty = true;
  }

  for (const button of document.querySelectorAll('.tabs [data-tab]')) {
    button.addEventListener('click', () => show(button.dataset.tab));
  }

  await show('compare');
}

boot().catch((error) => {
  const main = document.querySelector('main');
  const note = document.createElement('p');
  note.className = 'noscript';
  note.textContent = `The playground failed to start: ${error.message}`;
  main.prepend(note);
});
