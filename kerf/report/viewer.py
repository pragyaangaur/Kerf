"""The WebGL viewer that ships inside every report.

Flat shading is worked out in the fragment shader from screen space
derivatives, so the mesh needs no normal attribute and stays indexed. That
keeps the payload small enough to inline. Triangles are split into three
index groups for kept, added and removed surface, and each group is drawn in
its own colour, which is what makes a change readable at a glance.
"""

VIEWER_JS = r"""
const KERF = (() => {
  const dec = (b64) => {
    const bin = atob(b64); const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  };
  const f32 = (b64) => new Float32Array(dec(b64));
  const u32 = (b64) => new Uint32Array(dec(b64));

  // --- tiny mat4 -----------------------------------------------------
  const M = {
    ident: () => new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]),
    mul: (a, b) => {
      const o = new Float32Array(16);
      for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
        let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k];
        o[i * 4 + j] = s;
      }
      return o;
    },
    persp: (fov, aspect, near, far) => {
      const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
      return new Float32Array([f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0]);
    },
    look: (eye, at, up) => {
      const sub = (a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
      const norm = (v)=>{const l=Math.hypot(...v)||1;return [v[0]/l,v[1]/l,v[2]/l];};
      const cross = (a,b)=>[a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
      const dot = (a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
      const z = norm(sub(eye, at)); const x = norm(cross(up, z)); const y = cross(z, x);
      return new Float32Array([x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
                               -dot(x,eye),-dot(y,eye),-dot(z,eye),1]);
    }
  };

  const VS = `#version 300 es
  in vec3 aPos;
  uniform mat4 uProj, uView, uModel;
  out vec3 vWorld, vView;
  void main() {
    vec4 w = uModel * vec4(aPos, 1.0);
    vWorld = w.xyz;
    vec4 v = uView * w;
    vView = v.xyz;
    gl_Position = uProj * v;
  }`;

  const FS = `#version 300 es
  precision highp float;
  in vec3 vWorld, vView;
  uniform vec3 uColor, uRim;
  uniform float uAlpha;
  out vec4 frag;
  void main() {
    vec3 n = normalize(cross(dFdx(vView), dFdy(vView)));
    if (!gl_FrontFacing) n = -n;
    vec3 key = normalize(vec3(0.45, 0.35, 0.82));
    vec3 fill = normalize(vec3(-0.6, -0.25, 0.35));
    float d = max(dot(n, key), 0.0);
    float f = max(dot(n, fill), 0.0);
    vec3 v = normalize(-vView);
    float spec = pow(max(dot(reflect(-key, n), v), 0.0), 42.0) * 0.28;
    float fres = pow(1.0 - max(dot(n, v), 0.0), 3.0);
    vec3 c = uColor * (0.30 + 0.72 * d + 0.20 * f) + spec + uRim * fres * 0.55;
    frag = vec4(c, uAlpha);
  }`;

  const LVS = `#version 300 es
  in vec3 aPos; in vec3 aCol;
  uniform mat4 uProj, uView, uModel;
  out vec3 vCol;
  void main() { vCol = aCol; gl_Position = uProj * uView * uModel * vec4(aPos, 1.0); }`;

  const LFS = `#version 300 es
  precision highp float;
  in vec3 vCol; uniform float uAlpha; out vec4 frag;
  void main() { frag = vec4(vCol, uAlpha); }`;

  function compile(gl, vs, fs) {
    const mk = (type, src) => {
      const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  function gridLines(min, max) {
    const pos = [], col = [];
    const span = Math.max(max[0]-min[0], max[1]-min[1], max[2]-min[2]);
    const step = Math.pow(10, Math.round(Math.log10(span / 8)));
    const z = min[2] - span * 0.04;
    const x0 = Math.floor((min[0] - span*0.2)/step)*step, x1 = Math.ceil((max[0] + span*0.2)/step)*step;
    const y0 = Math.floor((min[1] - span*0.2)/step)*step, y1 = Math.ceil((max[1] + span*0.2)/step)*step;
    for (let x = x0; x <= x1 + 1e-9; x += step) { pos.push(x,y0,z, x,y1,z); col.push(0,0,0, 0,0,0); }
    for (let y = y0; y <= y1 + 1e-9; y += step) { pos.push(x0,y,z, x1,y,z); col.push(0,0,0, 0,0,0); }
    return { pos: new Float32Array(pos), col: new Float32Array(col), step };
  }

  function triad(scale) {
    const s = scale;
    return {
      pos: new Float32Array([0,0,0, s,0,0, 0,0,0, 0,s,0, 0,0,0, 0,0,s]),
      col: new Float32Array([0.85,0.28,0.24, 0.85,0.28,0.24, 0.30,0.62,0.35, 0.30,0.62,0.35,
                             0.29,0.47,0.80, 0.29,0.47,0.80])
    };
  }

  class Viewer {
    constructor(canvas, data, palette) {
      this.canvas = canvas; this.data = data; this.pal = palette;
      this.gl = canvas.getContext('webgl2', { antialias: true, alpha: true, premultipliedAlpha: false });
      if (!this.gl) { canvas.parentElement.classList.add('viewer-unsupported'); return; }
      const gl = this.gl;
      this.prog = compile(gl, VS, FS);
      this.lprog = compile(gl, LVS, LFS);
      this.mode = data.groups.added || data.groups.removed ? 'changes' : 'after';
      this.buffers = {};
      this.upload();
      const c = data.center, r = data.radius || 1;
      this.target = [c[0], c[1], c[2]];
      this.home = { yaw: -0.92, pitch: 0.52, dist: r * 3.1 };
      this.yaw = this.home.yaw; this.pitch = this.home.pitch; this.dist = this.home.dist;
      this.bind();
      this.dirty = true;
      this.loop = this.loop.bind(this);
      requestAnimationFrame(this.loop);
    }

    upload() {
      const gl = this.gl, d = this.data;
      const vbo = (arr) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
        gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW); return b; };
      const ibo = (arr) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, b);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, arr, gl.STATIC_DRAW); return b; };
      this.buffers.newPos = d.newPos ? vbo(f32(d.newPos)) : null;
      this.buffers.oldPos = d.oldPos ? vbo(f32(d.oldPos)) : null;
      this.groups = {};
      for (const [k, v] of Object.entries(d.groups)) {
        if (!v || !v.idx) continue;
        this.groups[k] = { buf: ibo(u32(v.idx)), count: v.count, src: v.src };
      }
      const g = gridLines(d.min, d.max);
      this.grid = { pos: vbo(g.pos), col: vbo(g.col), count: g.pos.length / 3 };
      const t = triad(d.radius * 0.55);
      this.triad = { pos: vbo(t.pos), col: vbo(t.col), count: 6 };
    }

    bind() {
      const cv = this.canvas;
      let drag = null;
      const pt = (e) => ({ x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 1 });
      cv.addEventListener('pointerdown', (e) => {
        drag = pt(e); cv.setPointerCapture(e.pointerId); cv.classList.add('grabbing');
      });
      cv.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        drag.x = e.clientX; drag.y = e.clientY;
        if (drag.pan) {
          const k = this.dist * 0.0018;
          const right = [Math.cos(this.yaw), -Math.sin(this.yaw), 0];
          this.target[0] -= right[0] * dx * k; this.target[1] -= right[1] * dx * k;
          this.target[2] += dy * k;
        } else {
          this.yaw += dx * 0.0072;
          this.pitch = Math.max(-1.45, Math.min(1.45, this.pitch + dy * 0.0072));
        }
        this.dirty = true;
      });
      const end = (e) => { drag = null; cv.classList.remove('grabbing'); };
      cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
      cv.addEventListener('wheel', (e) => {
        e.preventDefault();
        this.dist = Math.max(this.data.radius * 0.25,
                     Math.min(this.data.radius * 22, this.dist * Math.exp(e.deltaY * 0.0012)));
        this.dirty = true;
      }, { passive: false });
      cv.addEventListener('dblclick', () => this.reset());
      // the canvas is a flex child sized by its neighbour, and web fonts land
      // after first paint: redraw whenever the box actually changes
      if (window.ResizeObserver) {
        new ResizeObserver(() => { this.dirty = true; }).observe(cv);
      }
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => { this.dirty = true; });
      }
    }

    reset() {
      const c = this.data.center;
      this.target = [c[0], c[1], c[2]];
      this.yaw = this.home.yaw; this.pitch = this.home.pitch; this.dist = this.home.dist;
      this.dirty = true;
    }

    setMode(m) { this.mode = m; this.dirty = true; }

    loop() {
      if (this.dirty) { this.draw(); this.dirty = false; }
      requestAnimationFrame(this.loop);
    }

    resize() {
      const gl = this.gl, cv = this.canvas;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.round(cv.clientWidth * dpr));
      const h = Math.max(1, Math.round(cv.clientHeight * dpr));
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
      gl.viewport(0, 0, w, h);
      return w / h;
    }

    eye() {
      const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
      return [this.target[0] + this.dist * cp * Math.cos(this.yaw),
              this.target[1] + this.dist * cp * Math.sin(this.yaw),
              this.target[2] + this.dist * sp];
    }

    plan() {
      // which index groups to draw, against which vertex buffer, in what colour
      const p = this.pal, G = this.groups, out = [];
      const push = (name, color, alpha) => {
        const g = G[name]; if (!g || !g.count) return;
        out.push({ g, color, alpha, buf: g.src === 'old' ? this.buffers.oldPos : this.buffers.newPos });
      };
      if (this.mode === 'before') { push('oldAll', p.neutral, 1); }
      else if (this.mode === 'after') { push('newAll', p.neutral, 1); }
      else if (this.mode === 'ghost') {
        push('newAll', p.neutral, 1);
        push('oldAll', p.removed, 0.22);
      } else {
        push('kept', p.neutral, 1);
        push('added', p.added, 1);
        push('removed', p.removed, 0.92);
      }
      return out;
    }

    draw() {
      const gl = this.gl;
      const aspect = this.resize();
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK);
      const proj = M.persp(0.72, aspect, this.data.radius * 0.02, this.data.radius * 60);
      const view = M.look(this.eye(), this.target, [0, 0, 1]);
      const model = M.ident();

      // grid
      gl.useProgram(this.lprog);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lprog, 'uProj'), false, proj);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lprog, 'uView'), false, view);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lprog, 'uModel'), false, model);
      gl.uniform1f(gl.getUniformLocation(this.lprog, 'uAlpha'), 0.16);
      const la = gl.getAttribLocation(this.lprog, 'aPos');
      const lc = gl.getAttribLocation(this.lprog, 'aCol');
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.grid.pos);
      gl.enableVertexAttribArray(la); gl.vertexAttribPointer(la, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.grid.col);
      gl.enableVertexAttribArray(lc); gl.vertexAttribPointer(lc, 3, gl.FLOAT, false, 0, 0);
      const gc = this.pal.grid;
      gl.vertexAttrib3f(lc, gc[0], gc[1], gc[2]);
      gl.disableVertexAttribArray(lc);
      gl.drawArrays(gl.LINES, 0, this.grid.count);

      // solids
      gl.useProgram(this.prog);
      const u = (n) => gl.getUniformLocation(this.prog, n);
      gl.uniformMatrix4fv(u('uProj'), false, proj);
      gl.uniformMatrix4fv(u('uView'), false, view);
      gl.uniformMatrix4fv(u('uModel'), false, model);
      gl.uniform3fv(u('uRim'), this.pal.rim);
      const ap = gl.getAttribLocation(this.prog, 'aPos');
      const jobs = this.plan();
      for (const pass of [0, 1]) {
        for (const j of jobs) {
          if ((j.alpha < 1) !== (pass === 1)) continue;
          gl.bindBuffer(gl.ARRAY_BUFFER, j.buf);
          gl.enableVertexAttribArray(ap);
          gl.vertexAttribPointer(ap, 3, gl.FLOAT, false, 0, 0);
          gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, j.g.buf);
          gl.uniform3fv(u('uColor'), j.color);
          gl.uniform1f(u('uAlpha'), j.alpha);
          gl.depthMask(j.alpha >= 1);
          gl.drawElements(gl.TRIANGLES, j.g.count, gl.UNSIGNED_INT, 0);
        }
      }
      gl.depthMask(true);

      // orientation triad, drawn into a corner viewport
      const size = Math.round(Math.min(this.canvas.width, this.canvas.height) * 0.19);
      gl.viewport(8, 8, size, size);
      gl.disable(gl.DEPTH_TEST);
      const tview = M.look(
        [Math.cos(this.pitch) * Math.cos(this.yaw), Math.cos(this.pitch) * Math.sin(this.yaw),
         Math.sin(this.pitch)].map(v => v * this.data.radius * 2.4),
        [0, 0, 0], [0, 0, 1]);
      gl.useProgram(this.lprog);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lprog, 'uProj'), false,
                          M.persp(0.72, 1, this.data.radius * 0.05, this.data.radius * 20));
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lprog, 'uView'), false, tview);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lprog, 'uModel'), false, M.ident());
      gl.uniform1f(gl.getUniformLocation(this.lprog, 'uAlpha'), 0.9);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.triad.pos);
      gl.enableVertexAttribArray(la); gl.vertexAttribPointer(la, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.triad.col);
      gl.enableVertexAttribArray(lc); gl.vertexAttribPointer(lc, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, this.triad.count);
      gl.disableVertexAttribArray(lc);
      gl.enable(gl.DEPTH_TEST);
    }
  }

  function palette() {
    const cs = getComputedStyle(document.documentElement);
    const hex = (name, fb) => {
      const v = (cs.getPropertyValue(name) || fb).trim() || fb;
      const m = v.replace('#', '');
      const n = m.length === 3 ? m.split('').map(c => c + c).join('') : m;
      return [parseInt(n.slice(0,2),16)/255, parseInt(n.slice(2,4),16)/255, parseInt(n.slice(4,6),16)/255];
    };
    return {
      neutral: hex('--viewer-solid', '#9aa39d'),
      added: hex('--viewer-added', '#1e8e63'),
      removed: hex('--viewer-removed', '#c13b2e'),
      rim: hex('--viewer-rim', '#ffffff'),
      grid: hex('--viewer-grid', '#8d968f')
    };
  }

  function boot() {
    const pal = palette();
    const views = [];
    document.querySelectorAll('[data-kerf-view]').forEach((holder) => {
      const payload = JSON.parse(document.getElementById(holder.dataset.kerfView).textContent);
      const canvas = holder.querySelector('canvas');
      let v;
      try { v = new Viewer(canvas, payload, pal); }
      catch (err) { holder.classList.add('viewer-unsupported'); console.error(err); return; }
      views.push(v);
      holder.querySelectorAll('[data-mode]').forEach((btn) => {
        btn.addEventListener('click', () => {
          holder.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', 'false'));
          btn.setAttribute('aria-pressed', 'true');
          v.setMode(btn.dataset.mode);
        });
      });
      const active = holder.querySelector(`[data-mode="${v.mode}"]`);
      if (active) active.setAttribute('aria-pressed', 'true');
      const reset = holder.querySelector('[data-reset]');
      if (reset) reset.addEventListener('click', () => v.reset());
    });
    const redraw = () => views.forEach(v => { v.dirty = true; });
    window.addEventListener('resize', redraw);
    if (window.matchMedia) {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      if (mq.addEventListener) mq.addEventListener('change', redraw);
    }
    new MutationObserver(redraw).observe(document.documentElement,
      { attributes: true, attributeFilter: ['data-theme'] });
    return views;
  }

  return { boot };
})();
document.addEventListener('DOMContentLoaded', () => KERF.boot());
"""
