// Formatting numbers the way a machinist would read them.

export function volume(value) {
  if (Math.abs(value) >= 1e6) return `${(value / 1000).toFixed(0)} cm³`;
  if (Math.abs(value) >= 1e3) return `${(value / 1000).toFixed(2)} cm³`;
  return `${value.toPrecision(3)} mm³`;
}

export function number(value, digits = 2) {
  if (value === null || value === undefined) return '—';
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function percent(value) {
  if (value === null || value === undefined) return '';
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

export function bytes(count) {
  if (count >= 1024 * 1024) return `${(count / 1024 / 1024).toFixed(1)} MB`;
  if (count >= 1024) return `${(count / 1024).toFixed(0)} KB`;
  return `${count} B`;
}

export function vector(values, digits = 1) {
  return values.map((value) => value.toFixed(digits)).join(', ');
}

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}
