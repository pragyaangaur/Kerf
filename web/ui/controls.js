// The parameter controls.
//
// A range and a number box are wired to the same value, because dragging is
// how somebody explores a part and typing is how they pin a dimension down.
// Every change reports through one callback so the caller can re-evaluate.

import { clear, element } from './format.js';

// Ranges are guessed from the value the part shipped with. A dimension is
// rarely useful below zero, and a factor of about three either way covers the
// edits somebody actually makes while looking at a part.
function rangeFor(value) {
  const magnitude = Math.abs(value) || 1;
  const step = magnitude >= 20 ? 0.5 : magnitude >= 4 ? 0.1 : 0.05;
  return {
    min: Math.max(0, Math.round((value - magnitude * 0.8) / step) * step),
    max: Math.round((value + magnitude * 1.6) / step) * step,
    step,
  };
}

export function buildParameterControls(host, part, resolved, onChange) {
  clear(host);
  const names = Object.keys(part.parameters);
  if (!names.length) {
    host.appendChild(element('p', 'empty-note', 'This part has no parameters.'));
    return;
  }

  for (const name of names) {
    const raw = part.parameters[name];
    const row = element('div', 'control');
    const label = element('label', 'control-label');
    label.textContent = name;
    label.setAttribute('for', `param-${name}`);
    row.appendChild(label);

    if (typeof raw !== 'number') {
      // An expression is shown as it was written, because rewriting it into a
      // number would throw away the link the author put there on purpose.
      const shown = element('span', 'control-expression mono', `${raw} = ${(resolved[name] ?? 0).toFixed(2)}`);
      row.appendChild(shown);
      host.appendChild(row);
      continue;
    }

    const { min, max, step } = rangeFor(raw);
    const slider = element('input', 'control-range');
    slider.type = 'range';
    slider.min = String(min);
    slider.max = String(max);
    slider.step = String(step);
    slider.value = String(raw);
    slider.id = `param-${name}`;

    const box = element('input', 'control-number mono');
    box.type = 'number';
    box.step = String(step);
    box.value = String(raw);
    box.setAttribute('aria-label', `${name} value`);

    const apply = (value) => {
      const next = Number(value);
      if (Number.isNaN(next)) return;
      slider.value = String(next);
      box.value = String(next);
      onChange(name, next);
    };

    slider.addEventListener('input', () => apply(slider.value));
    box.addEventListener('change', () => apply(box.value));

    row.appendChild(slider);
    row.appendChild(box);
    host.appendChild(row);
  }
}

export function buildFeatureList(host, part, onToggle) {
  clear(host);
  for (const feature of part.features) {
    const row = element('div', `feature-row${feature.suppressed ? ' is-off' : ''}`);
    const toggle = element('input');
    toggle.type = 'checkbox';
    toggle.checked = !feature.suppressed;
    toggle.id = `feature-${feature.id}`;
    toggle.addEventListener('change', () => onToggle(feature.id, !toggle.checked));

    const label = element('label', 'feature-label');
    label.setAttribute('for', `feature-${feature.id}`);
    label.textContent = feature.name || feature.id;

    const kind = element('span', 'feature-kind mono', `${feature.op || 'add'} ${feature.type}`);

    row.appendChild(toggle);
    row.appendChild(label);
    row.appendChild(kind);
    host.appendChild(row);
  }
}
