// Parameter expressions.
//
// A part file may write any number as an expression over the parameter table,
// so "bolt_d/2" stays correct when bolt_d moves. The expression is parsed into
// a small tree and walked. eval is never used, because a part file is data
// that arrives from other people.

const FUNCTIONS = {
  sqrt: Math.sqrt, sin: Math.sin, cos: Math.cos, tan: Math.tan,
  abs: Math.abs, min: Math.min, max: Math.max, round: Math.round,
  floor: Math.floor, ceil: Math.ceil, atan2: Math.atan2, hypot: Math.hypot,
  pow: Math.pow,
  radians: (d) => (d * Math.PI) / 180,
  degrees: (r) => (r * 180) / Math.PI,
};

const CONSTANTS = { pi: Math.PI, tau: Math.PI * 2, e: Math.E };

export class ExpressionError extends Error {}

function tokenize(text) {
  const tokens = [];
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (/\s/.test(char)) { index += 1; continue; }
    if (/[0-9.]/.test(char)) {
      let end = index;
      while (end < text.length && /[0-9.eE]/.test(text[end])) {
        // An e only continues the number when a sign or digit follows it.
        if (/[eE]/.test(text[end]) && !/[0-9+-]/.test(text[end + 1] || '')) break;
        if (/[eE]/.test(text[end]) && /[+-]/.test(text[end + 1])) end += 1;
        end += 1;
      }
      const value = Number(text.slice(index, end));
      if (Number.isNaN(value)) throw new ExpressionError(`bad number in ${text}`);
      tokens.push({ type: 'number', value });
      index = end;
      continue;
    }
    if (/[A-Za-z_]/.test(char)) {
      let end = index;
      while (end < text.length && /[A-Za-z0-9_]/.test(text[end])) end += 1;
      tokens.push({ type: 'name', value: text.slice(index, end) });
      index = end;
      continue;
    }
    if ('+-*/%(),'.includes(char)) {
      tokens.push({ type: char });
      index += 1;
      continue;
    }
    if (char === '*' || char === '^') { tokens.push({ type: '^' }); index += 1; continue; }
    throw new ExpressionError(`unexpected character ${char} in ${text}`);
  }
  return tokens;
}

function parse(text) {
  const tokens = tokenize(text.replace(/\*\*/g, '^').replace(/\^/g, '^'));
  let position = 0;

  const peek = () => tokens[position];
  const take = (type) => {
    if (!peek() || peek().type !== type) {
      throw new ExpressionError(`expected ${type} in ${text}`);
    }
    return tokens[position++];
  };

  function primary() {
    const token = peek();
    if (!token) throw new ExpressionError(`unexpected end of ${text}`);
    if (token.type === 'number') { position += 1; return { kind: 'number', value: token.value }; }
    if (token.type === '-') { position += 1; return { kind: 'negate', operand: primary() }; }
    if (token.type === '+') { position += 1; return primary(); }
    if (token.type === '(') {
      position += 1;
      const inner = expression();
      take(')');
      return inner;
    }
    if (token.type === 'name') {
      position += 1;
      if (peek() && peek().type === '(') {
        position += 1;
        const args = [];
        if (peek() && peek().type !== ')') {
          args.push(expression());
          while (peek() && peek().type === ',') { position += 1; args.push(expression()); }
        }
        take(')');
        return { kind: 'call', name: token.value, args };
      }
      return { kind: 'name', name: token.value };
    }
    throw new ExpressionError(`unexpected token in ${text}`);
  }

  function power() {
    const base = primary();
    if (peek() && peek().type === '^') {
      position += 1;
      return { kind: 'binary', op: '^', left: base, right: power() };
    }
    return base;
  }

  function term() {
    let left = power();
    while (peek() && ['*', '/', '%'].includes(peek().type)) {
      const op = tokens[position++].type;
      left = { kind: 'binary', op, left, right: power() };
    }
    return left;
  }

  function expression() {
    let left = term();
    while (peek() && ['+', '-'].includes(peek().type)) {
      const op = tokens[position++].type;
      left = { kind: 'binary', op, left, right: term() };
    }
    return left;
  }

  const tree = expression();
  if (position !== tokens.length) throw new ExpressionError(`trailing input in ${text}`);
  return tree;
}

const cache = new Map();

function parseCached(text) {
  if (!cache.has(text)) cache.set(text, parse(text));
  return cache.get(text);
}

function walk(node, params) {
  switch (node.kind) {
    case 'number': return node.value;
    case 'negate': return -walk(node.operand, params);
    case 'name': {
      if (Object.prototype.hasOwnProperty.call(params, node.name)) return Number(params[node.name]);
      if (node.name in CONSTANTS) return CONSTANTS[node.name];
      throw new ExpressionError(`unknown parameter ${node.name}`);
    }
    case 'call': {
      const fn = FUNCTIONS[node.name];
      if (!fn) throw new ExpressionError(`function ${node.name} is not allowed`);
      return fn(...node.args.map((arg) => walk(arg, params)));
    }
    case 'binary': {
      const a = walk(node.left, params);
      const b = walk(node.right, params);
      if (node.op === '+') return a + b;
      if (node.op === '-') return a - b;
      if (node.op === '*') return a * b;
      if (node.op === '/') return a / b;
      if (node.op === '%') return a % b;
      return a ** b;
    }
    default: throw new ExpressionError('unsupported expression');
  }
}

export function evaluateExpression(text, params) {
  return walk(parseCached(text), params);
}

export function resolve(value, params) {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') return evaluateExpression(value, params);
  throw new ExpressionError(`expected a number or expression, got ${value}`);
}

export function resolveVec(value, params, fallback = [0, 0, 0]) {
  if (value === undefined || value === null) return fallback.slice();
  return value.map((item) => resolve(item, params));
}

// Which parameters an expression reads. This is what lets the diff say that
// changing bolt_d moved four holes.
export function expressionDependencies(value) {
  if (typeof value !== 'string') return new Set();
  let tree;
  try {
    tree = parseCached(value);
  } catch {
    return new Set();
  }
  const found = new Set();
  (function visit(node) {
    if (node.kind === 'name' && !(node.name in CONSTANTS)) found.add(node.name);
    if (node.kind === 'negate') visit(node.operand);
    if (node.kind === 'binary') { visit(node.left); visit(node.right); }
    if (node.kind === 'call') node.args.forEach(visit);
  })(tree);
  return found;
}
