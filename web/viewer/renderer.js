// The WebGL viewer.
//
// Flat shading is worked out in the fragment shader from screen space
// derivatives, so the mesh needs no normal attribute and stays indexed. Each
// layer draws with one colour, which is what makes a change readable: shared
// surface in grey, new surface in green, surface that went away in red.

import { identity, lookAt, perspective } from './mat4.js';

const VERTEX_SOURCE = `#version 300 es
in vec3 aPos;
uniform mat4 uProj, uView, uModel;
out vec3 vView;
void main() {
  vec4 world = uModel * vec4(aPos, 1.0);
  vec4 view = uView * world;
  vView = view.xyz;
  gl_Position = uProj * view;
}`;

const FRAGMENT_SOURCE = `#version 300 es
precision highp float;
in vec3 vView;
uniform vec3 uColor, uRim;
uniform float uAlpha;
out vec4 frag;
void main() {
  vec3 normal = normalize(cross(dFdx(vView), dFdy(vView)));
  if (!gl_FrontFacing) normal = -normal;
  vec3 key = normalize(vec3(0.45, 0.35, 0.82));
  vec3 fill = normalize(vec3(-0.6, -0.25, 0.35));
  float lit = max(dot(normal, key), 0.0);
  float bounce = max(dot(normal, fill), 0.0);
  vec3 toEye = normalize(-vView);
  float spec = pow(max(dot(reflect(-key, normal), toEye), 0.0), 42.0) * 0.28;
  float rim = pow(1.0 - max(dot(normal, toEye), 0.0), 3.0);
  vec3 shade = uColor * (0.30 + 0.72 * lit + 0.20 * bounce) + spec + uRim * rim * 0.55;
  frag = vec4(shade, uAlpha);
}`;

const LINE_VERTEX_SOURCE = `#version 300 es
in vec3 aPos;
uniform mat4 uProj, uView;
void main() { gl_Position = uProj * uView * vec4(aPos, 1.0); }`;

const LINE_FRAGMENT_SOURCE = `#version 300 es
precision highp float;
uniform vec3 uColor;
uniform float uAlpha;
out vec4 frag;
void main() { frag = vec4(uColor, uAlpha); }`;

function compile(gl, vertexSource, fragmentSource) {
  const make = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader));
    }
    return shader;
  };
  const program = gl.createProgram();
  gl.attachShader(program, make(gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, make(gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program));
  }
  return program;
}

export class Viewer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl2', { antialias: true, alpha: true });
    this.supported = Boolean(this.gl);
    if (!this.supported) return;

    const gl = this.gl;
    this.program = compile(gl, VERTEX_SOURCE, FRAGMENT_SOURCE);
    this.lineProgram = compile(gl, LINE_VERTEX_SOURCE, LINE_FRAGMENT_SOURCE);
    this.layers = [];
    this.buffers = [];
    this.grid = null;
    this.yaw = -0.92;
    this.pitch = 0.52;
    this.distance = 100;
    this.target = [0, 0, 0];
    this.radius = 30;
    this.palette = {
      neutral: [0.66, 0.69, 0.67],
      added: [0.25, 0.70, 0.51],
      removed: [0.79, 0.31, 0.24],
      rim: [1, 1, 1],
      grid: [0.55, 0.58, 0.55],
    };
    this.dirty = true;
    this.bindInput();
    const loop = () => {
      if (this.dirty) {
        this.draw();
        this.dirty = false;
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  setPalette(palette) {
    Object.assign(this.palette, palette);
    this.dirty = true;
  }

  bindInput() {
    const canvas = this.canvas;
    let drag = null;
    canvas.addEventListener('pointerdown', (event) => {
      drag = { x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 1 };
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add('grabbing');
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!drag) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      drag.x = event.clientX;
      drag.y = event.clientY;
      if (drag.pan) {
        const scale = this.distance * 0.0018;
        this.target[0] -= Math.cos(this.yaw) * dx * scale;
        this.target[1] += Math.sin(this.yaw) * dx * scale;
        this.target[2] += dy * scale;
      } else {
        this.yaw += dx * 0.0072;
        this.pitch = Math.max(-1.45, Math.min(1.45, this.pitch + dy * 0.0072));
      }
      this.dirty = true;
    });
    const release = () => { drag = null; canvas.classList.remove('grabbing'); };
    canvas.addEventListener('pointerup', release);
    canvas.addEventListener('pointercancel', release);
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      const next = this.distance * Math.exp(event.deltaY * 0.0012);
      this.distance = Math.max(this.radius * 0.3, Math.min(this.radius * 20, next));
      this.dirty = true;
    }, { passive: false });
    canvas.addEventListener('dblclick', () => this.recentre());
    if (window.ResizeObserver) {
      new ResizeObserver(() => { this.dirty = true; }).observe(canvas);
    }
  }

  // Frame the model the first time it appears, and leave the camera alone on
  // every update after that so a slider drag does not fight the view.
  setLayers(layers, bounds, refit = false) {
    if (!this.supported) return;
    const gl = this.gl;
    for (const buffer of this.buffers) {
      gl.deleteBuffer(buffer.position);
      gl.deleteBuffer(buffer.index);
    }
    this.buffers = layers.map((layer) => {
      const position = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, position);
      gl.bufferData(gl.ARRAY_BUFFER, layer.positions, gl.STATIC_DRAW);
      const index = gl.createBuffer();
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, index);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, layer.indices, gl.STATIC_DRAW);
      return { position, index, count: layer.indices.length, color: layer.color, alpha: layer.alpha ?? 1 };
    });

    if (bounds) {
      const [low, high] = bounds;
      const centre = [0, 1, 2].map((axis) => (low[axis] + high[axis]) / 2);
      const radius = Math.max(
        Math.hypot(high[0] - low[0], high[1] - low[1], high[2] - low[2]) / 2, 1e-3,
      );
      const firstTime = !this.framed;
      this.radius = radius;
      this.homeTarget = centre;
      if (firstTime || refit) {
        this.target = centre.slice();
        this.distance = radius * 3.1;
        this.framed = true;
      }
      this.buildGrid(low, high);
    }
    this.dirty = true;
  }

  buildGrid(low, high) {
    const gl = this.gl;
    const span = Math.max(high[0] - low[0], high[1] - low[1], high[2] - low[2]);
    const step = 10 ** Math.round(Math.log10(span / 8));
    const z = low[2] - span * 0.04;
    const points = [];
    const x0 = Math.floor((low[0] - span * 0.2) / step) * step;
    const x1 = Math.ceil((high[0] + span * 0.2) / step) * step;
    const y0 = Math.floor((low[1] - span * 0.2) / step) * step;
    const y1 = Math.ceil((high[1] + span * 0.2) / step) * step;
    for (let x = x0; x <= x1 + 1e-9; x += step) points.push(x, y0, z, x, y1, z);
    for (let y = y0; y <= y1 + 1e-9; y += step) points.push(x0, y, z, x1, y, z);
    if (this.grid) gl.deleteBuffer(this.grid.buffer);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(points), gl.STATIC_DRAW);
    this.grid = { buffer, count: points.length / 3 };
  }

  recentre() {
    if (this.homeTarget) this.target = this.homeTarget.slice();
    this.yaw = -0.92;
    this.pitch = 0.52;
    this.distance = this.radius * 3.1;
    this.dirty = true;
  }

  resize() {
    const gl = this.gl;
    const canvas = this.canvas;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    return width / height;
  }

  eye() {
    const flat = Math.cos(this.pitch);
    return [
      this.target[0] + this.distance * flat * Math.cos(this.yaw),
      this.target[1] + this.distance * flat * Math.sin(this.yaw),
      this.target[2] + this.distance * Math.sin(this.pitch),
    ];
  }

  draw() {
    if (!this.supported) return;
    const gl = this.gl;
    const aspect = this.resize();
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.CULL_FACE);
    gl.cullFace(gl.BACK);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const projection = perspective(0.72, aspect, this.radius * 0.02, this.radius * 60);
    const view = lookAt(this.eye(), this.target, [0, 0, 1]);

    if (this.grid) {
      gl.useProgram(this.lineProgram);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lineProgram, 'uProj'), false, projection);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lineProgram, 'uView'), false, view);
      gl.uniform3fv(gl.getUniformLocation(this.lineProgram, 'uColor'), this.palette.grid);
      gl.uniform1f(gl.getUniformLocation(this.lineProgram, 'uAlpha'), 0.18);
      const position = gl.getAttribLocation(this.lineProgram, 'aPos');
      gl.bindBuffer(gl.ARRAY_BUFFER, this.grid.buffer);
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, this.grid.count);
    }

    gl.useProgram(this.program);
    const uniform = (name) => gl.getUniformLocation(this.program, name);
    gl.uniformMatrix4fv(uniform('uProj'), false, projection);
    gl.uniformMatrix4fv(uniform('uView'), false, view);
    gl.uniformMatrix4fv(uniform('uModel'), false, identity());
    gl.uniform3fv(uniform('uRim'), this.palette.rim);
    const attribute = gl.getAttribLocation(this.program, 'aPos');

    // Opaque layers first, so a translucent ghost blends over a finished image.
    for (const pass of [1, 0]) {
      for (const buffer of this.buffers) {
        if (!buffer.count) continue;
        if ((buffer.alpha >= 1) !== (pass === 1)) continue;
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer.position);
        gl.enableVertexAttribArray(attribute);
        gl.vertexAttribPointer(attribute, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, buffer.index);
        gl.uniform3fv(uniform('uColor'), this.palette[buffer.color] || this.palette.neutral);
        gl.uniform1f(uniform('uAlpha'), buffer.alpha);
        gl.depthMask(buffer.alpha >= 1);
        gl.drawElements(gl.TRIANGLES, buffer.count, gl.UNSIGNED_INT, 0);
      }
    }
    gl.depthMask(true);
  }
}
