import { FEATURE, MAX_CANDLES, MAX_PRICE_LEVELS, CANDLE_PRICE_LEVELS } from '../types/MemoryLayout.js';
import TerminalConfig from '../config/TerminalConfig.js';

const BBO_HISTORY_DEPTH = 216000;
const HEATMAP_TEX_HEIGHT = 4096;
const HEATMAP_TEX_WIDTH = 4096;
const MAX_BUBBLES = 100000;
const LUT_SIZE = 256;

const VERT_SRC_HEATMAP = `#version 300 es
precision highp float;
layout(location=0) in vec2 a_position;
uniform mat4 u_MVP;
uniform float u_scroll_offset;
out vec2 v_texcoord;
void main(){
  v_texcoord=a_position;
  v_texcoord.x=fract(v_texcoord.x+u_scroll_offset);
  gl_Position=u_MVP*vec4(a_position,0.0,1.0);
}`;

const FRAG_SRC_HEATMAP = `#version 300 es
precision highp float;
uniform sampler2D u_heatmap_texture;
uniform sampler2D u_lut_texture;
uniform float u_contrast_scale;
uniform float u_dimming;
in vec2 v_texcoord;
out vec4 fragColor;
void main(){
  float raw=texture(u_heatmap_texture,v_texcoord).r;
  float n=clamp(raw*u_contrast_scale,0.0,1.0);
  vec4 color=texture(u_lut_texture,vec2(n,0.5));
  fragColor=vec4(color.rgb*u_dimming,1.0);
}`;

const VERT_SRC_BUBBLE = `#version 300 es
precision highp float;
layout(location=0) in vec2 a_position;
layout(location=1) in vec2 a_inst_position;
layout(location=2) in float a_inst_radius;
layout(location=3) in vec4 a_inst_color;
layout(location=4) in float a_inst_type;
uniform mat4 u_MVP;
uniform float u_time;
out vec2 v_local_pos;
out vec4 v_color;
out float v_type;
out float v_time;
void main(){
  v_local_pos=a_position;
  v_color=a_inst_color;
  v_type=a_inst_type;
  v_time=u_time;
  vec2 wp=a_inst_position+a_position*a_inst_radius;
  gl_Position=u_MVP*vec4(wp,0.0,1.0);
}`;

const FRAG_SRC_BUBBLE = `#version 300 es
precision highp float;
in vec2 v_local_pos;
in vec4 v_color;
in float v_type;
in float v_time;
out vec4 fragColor;
void main(){
  float dist;
  float alpha;
  if(v_type<0.5){
    dist=length(v_local_pos);
    alpha=1.0-smoothstep(1.0-fwidth(dist),1.0,dist);
  }else if(v_type<1.5){
    vec2 d=abs(v_local_pos);
    dist=max(d.x,d.y);
    alpha=1.0-smoothstep(0.9-fwidth(dist),0.9,dist);
  }else if(v_type<2.5){
    dist=length(v_local_pos);
    alpha=1.0-smoothstep(1.0-fwidth(dist),1.0,dist);
    alpha*=0.7;
  }else{
    dist=length(v_local_pos);
    float pulse=0.5+0.5*sin(v_time*6.2831853);
    alpha=1.0-smoothstep(1.0-fwidth(dist),1.0,dist);
    alpha*=(0.5+0.5*pulse);
    fragColor=vec4(v_color.rgb,alpha*v_color.a);
    return;
  }
  fragColor=vec4(v_color.rgb,alpha*v_color.a);
}`;

const VERT_SRC_BBO = `#version 300 es
precision highp float;
layout(location=0) in vec2 a_position;
layout(location=1) in float a_side_flag;
uniform mat4 u_MVP;
out vec4 v_color;
void main(){
  v_color=a_side_flag<0.5?vec4(0.149,0.651,0.604,1.0):vec4(0.937,0.325,0.314,1.0);
  gl_Position=u_MVP*vec4(a_position,0.0,1.0);
}`;

const FRAG_SRC_BBO = `#version 300 es
precision highp float;
in vec4 v_color;
out vec4 fragColor;
void main(){fragColor=v_color;}`;

const VERT_SRC_VOLBAR = `#version 300 es
precision highp float;
layout(location=0) in vec2 a_position;
uniform mat4 u_MVP;
out vec4 v_color;
void main(){
  v_color = a_position.y < 0.0 ? vec4(0.149,0.651,0.604,0.7) : vec4(0.937,0.325,0.314,0.7);
  gl_Position=u_MVP*vec4(a_position,0.0,1.0);
}`;

const FRAG_SRC_VOLBAR = `#version 300 es
precision highp float;
in vec4 v_color;
out vec4 fragColor;
void main(){fragColor=v_color;}`;

export class WebGLHeatmap {
  constructor(canvas, featureSAB) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl2', {
      desynchronized: true,
      preserveDrawingBuffer: true,
      alpha: false,
      antialias: false,
    });
    this.featureSAB = featureSAB;

    if (!this.gl) {
      console.error('[NEXUS] WebGL2 not available');
      return;
    }

    this.viewState = {
      scrollX: 0,
      zoom: 40,
      priceMin: 4490,
      priceMax: 4510,
      pixelsPerTick: 0,
    };

    this.tickSize = 0.25;
    this.currentHeatmapCol = 0;
    this.rollingMeanResting = 1;
    this.bubbleCount = 0;
    this.startTime = performance.now() / 1000;
    this.dimming = 1.0;

    this._initGL();
  }

  _initGL() {
    const gl = this.gl;
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0.043, 0.055, 0.067, 1.0);

    this.heatmapProgram = this._createProgram(VERT_SRC_HEATMAP, FRAG_SRC_HEATMAP);
    this.bubbleProgram = this._createProgram(VERT_SRC_BUBBLE, FRAG_SRC_BUBBLE);
    this.bboProgram = this._createProgram(VERT_SRC_BBO, FRAG_SRC_BBO);
    this.volBarProgram = this._createProgram(VERT_SRC_VOLBAR, FRAG_SRC_VOLBAR);

    this._initHeatmapResources();
    this._initBubbleResources();
    this._initBBOResources();
    this._initLUT();
    this._initQuad();
    this._initVolumeBarResources();

    this.featureHeader = new Int32Array(this.featureSAB, 0, FEATURE.HEADER_SIZE / 4);
    this.absorptionFlags = new Uint8Array(this.featureSAB, FEATURE.ABSORPTION_FLAGS_OFFSET, MAX_PRICE_LEVELS);
    this.icebergMap = new Float32Array(this.featureSAB, FEATURE.ICEBERG_MAP_OFFSET, 65536);
    this.bboBid = new Float64Array(this.featureSAB, FEATURE.BBO_BID_OFFSET, BBO_HISTORY_DEPTH);
    this.bboAsk = new Float64Array(this.featureSAB, FEATURE.BBO_ASK_OFFSET, BBO_HISTORY_DEPTH);
    this.lobBidDepth = new Float64Array(this.featureSAB, FEATURE.LOB_BID_DEPTH_OFFSET, MAX_PRICE_LEVELS);
    this.lobAskDepth = new Float64Array(this.featureSAB, FEATURE.LOB_ASK_DEPTH_OFFSET, MAX_PRICE_LEVELS);

    this.columnData = new Float32Array(HEATMAP_TEX_HEIGHT);
    this.mvp = new Float32Array(16);
    this._computeMVP();
  }

  _createProgram(vertSrc, fragSrc) {
    const gl = this.gl;
    const vert = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vert, vertSrc);
    gl.compileShader(vert);
    if (!gl.getShaderParameter(vert, gl.COMPILE_STATUS)) {
      console.error('[NEXUS] Vert error:', gl.getShaderInfoLog(vert));
    }
    const frag = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(frag, fragSrc);
    gl.compileShader(frag);
    if (!gl.getShaderParameter(frag, gl.COMPILE_STATUS)) {
      console.error('[NEXUS] Frag error:', gl.getShaderInfoLog(frag));
    }
    const prog = gl.createProgram();
    gl.attachShader(prog, vert);
    gl.attachShader(prog, frag);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error('[NEXUS] Link error:', gl.getProgramInfoLog(prog));
    }
    return prog;
  }

  _initHeatmapResources() {
    const gl = this.gl;
    this.heatmapTexture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.heatmapTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, HEATMAP_TEX_WIDTH, HEATMAP_TEX_HEIGHT, 0, gl.RED, gl.FLOAT, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    this.u_heatmap_texture = gl.getUniformLocation(this.heatmapProgram, 'u_heatmap_texture');
    this.u_lut_texture = gl.getUniformLocation(this.heatmapProgram, 'u_lut_texture');
    this.u_contrast_scale = gl.getUniformLocation(this.heatmapProgram, 'u_contrast_scale');
    this.u_scroll_offset = gl.getUniformLocation(this.heatmapProgram, 'u_scroll_offset');
    this.u_dimming = gl.getUniformLocation(this.heatmapProgram, 'u_dimming');
    this.u_MVP_heatmap = gl.getUniformLocation(this.heatmapProgram, 'u_MVP');
  }

  _initLUT() {
    const gl = this.gl;
    const lutData = new Uint8Array(LUT_SIZE * 4);

    const stops = [
      { pos: 0.00, r: 0, g: 0, b: 0 },
      { pos: 0.15, r: 0, g: 0, b: 80 },
      { pos: 0.30, r: 0, g: 40, b: 180 },
      { pos: 0.50, r: 255, g: 200, b: 0 },
      { pos: 0.70, r: 255, g: 160, b: 0 },
      { pos: 0.85, r: 255, g: 80, b: 0 },
      { pos: 1.00, r: 255, g: 0, b: 0 },
    ];

    for (let i = 0; i < LUT_SIZE; i++) {
      const t = i / (LUT_SIZE - 1);
      let r, g, b;
      let lower = stops[0], upper = stops[stops.length - 1];
      for (let s = 0; s < stops.length - 1; s++) {
        if (t >= stops[s].pos && t <= stops[s + 1].pos) {
          lower = stops[s];
          upper = stops[s + 1];
          break;
        }
      }
      const range = upper.pos - lower.pos;
      const s = range > 0 ? (t - lower.pos) / range : 0;
      r = Math.round(lower.r + (upper.r - lower.r) * s);
      g = Math.round(lower.g + (upper.g - lower.g) * s);
      b = Math.round(lower.b + (upper.b - lower.b) * s);
      lutData[i * 4 + 0] = r;
      lutData[i * 4 + 1] = g;
      lutData[i * 4 + 2] = b;
      lutData[i * 4 + 3] = 255;
    }

    this.lutTexture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.lutTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, LUT_SIZE, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, lutData);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  _initQuad() {
    const gl = this.gl;
    const verts = new Float32Array([0,0,1,0,1,1, 0,0,1,1,0,1]);
    this.quadVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadVBO);
    gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);
  }

  _initBubbleResources() {
    const gl = this.gl;
    const quadVerts = new Float32Array([-1,-1,1,-1,1,1, -1,-1,1,1,-1,1]);
    this.bubbleQuadVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.bubbleQuadVBO);
    gl.bufferData(gl.ARRAY_BUFFER, quadVerts, gl.STATIC_DRAW);

    this.bubbleInstanceVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.bubbleInstanceVBO);
    gl.bufferData(gl.ARRAY_BUFFER, MAX_BUBBLES * 9 * 4, gl.DYNAMIC_DRAW);

    this.bubbleInstanceData = new Float32Array(MAX_BUBBLES * 9);
    this.bubbleCount = 0;

    this.u_MVP_bubble = gl.getUniformLocation(this.bubbleProgram, 'u_MVP');
    this.u_time = gl.getUniformLocation(this.bubbleProgram, 'u_time');
  }

  _initBBOResources() {
    const gl = this.gl;
    this.bboVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.bboVBO);
    gl.bufferData(gl.ARRAY_BUFFER, BBO_HISTORY_DEPTH * 3 * 4, gl.DYNAMIC_DRAW);
    this.bboData = new Float32Array(BBO_HISTORY_DEPTH * 3);
    this.u_MVP_bbo = gl.getUniformLocation(this.bboProgram, 'u_MVP');
  }

  _initVolumeBarResources() {
    const gl = this.gl;
    this.volBarVBO = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.volBarVBO);
    gl.bufferData(gl.ARRAY_BUFFER, 4096 * 6 * 2 * 4, gl.DYNAMIC_DRAW);
    this.volBarData = new Float32Array(4096 * 6 * 2);
    this.volBarCount = 0;
    this.u_MVP_volbar = gl.getUniformLocation(this.volBarProgram, 'u_MVP');
  }

  _computeMVP() {
    const { priceMin, priceMax } = this.viewState;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const left = 0;
    const right = w;
    const bottom = priceMin;
    const top = priceMax;
    const near = -1;
    const far = 1;
    const rl = 1 / (right - left);
    const tb = 1 / (top - bottom);
    const fn = 1 / (far - near);
    this.mvp.fill(0);
    this.mvp[0] = 2 * rl;
    this.mvp[5] = 2 * tb;
    this.mvp[10] = -2 * fn;
    this.mvp[12] = -(right + left) * rl;
    this.mvp[13] = -(top + bottom) * tb;
    this.mvp[14] = -(far + near) * fn;
    this.mvp[15] = 1;
  }

  updateViewState(vs) {
    this.viewState = { ...this.viewState, ...vs };
    this._computeMVP();
  }

  addBubble(x, y, radius, r, g, b, a, type) {
    if (this.bubbleCount >= MAX_BUBBLES) return;
    const idx = this.bubbleCount * 9;
    this.bubbleInstanceData[idx + 0] = x;
    this.bubbleInstanceData[idx + 1] = y;
    this.bubbleInstanceData[idx + 2] = radius;
    this.bubbleInstanceData[idx + 3] = r;
    this.bubbleInstanceData[idx + 4] = g;
    this.bubbleInstanceData[idx + 5] = b;
    this.bubbleInstanceData[idx + 6] = a;
    this.bubbleInstanceData[idx + 7] = type;
    this.bubbleInstanceData[idx + 8] = 0;
    this.bubbleCount++;
  }

  advanceHeatmapColumn() {
    const gl = this.gl;
    this.columnData.fill(0);

    for (let pIdx = 0; pIdx < MAX_PRICE_LEVELS && pIdx < HEATMAP_TEX_HEIGHT; pIdx++) {
      const bidDepth = this.lobBidDepth[pIdx] || 0;
      const askDepth = this.lobAskDepth[pIdx] || 0;
      const total = bidDepth + askDepth;
      if (total > 0) {
        this.columnData[pIdx] = total;
      }
    }

    gl.bindTexture(gl.TEXTURE_2D, this.heatmapTexture);
    gl.texSubImage2D(
      gl.TEXTURE_2D, 0,
      this.currentHeatmapCol, 0,
      1, HEATMAP_TEX_HEIGHT,
      gl.RED, gl.FLOAT,
      this.columnData
    );

    this.currentHeatmapCol = (this.currentHeatmapCol + 1) % HEATMAP_TEX_WIDTH;

    let sum = 0;
    let count = 0;
    for (let i = 0; i < this.columnData.length; i++) {
      if (this.columnData[i] > 0) {
        sum += this.columnData[i];
        count++;
      }
    }
    this.rollingMeanResting = count > 0 ? sum / count : 1;
  }

  render(timestamp) {
    const gl = this.gl;
    if (!gl) return;

    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);

    this._renderHeatmap();
    this._renderBubbles(timestamp);
    this._renderBBO();
  }

  _renderHeatmap() {
    const gl = this.gl;
    gl.useProgram(this.heatmapProgram);
    gl.uniformMatrix4fv(this.u_MVP_heatmap, false, this.mvp);
    gl.uniform1f(this.u_scroll_offset, this.currentHeatmapCol / HEATMAP_TEX_WIDTH);
    gl.uniform1f(this.u_contrast_scale, 1.0 / Math.max(this.rollingMeanResting, 0.001));
    gl.uniform1f(this.u_dimming, this.dimming);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.heatmapTexture);
    gl.uniform1i(this.u_heatmap_texture, 0);

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.lutTexture);
    gl.uniform1i(this.u_lut_texture, 1);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadVBO);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    gl.drawArrays(gl.TRIANGLES, 0, 6);
    gl.disableVertexAttribArray(0);
  }

  _renderBubbles(timestamp) {
    if (this.bubbleCount === 0) return;
    const gl = this.gl;
    const time = (timestamp || performance.now()) / 1000 - this.startTime;

    gl.useProgram(this.bubbleProgram);
    gl.uniformMatrix4fv(this.u_MVP_bubble, false, this.mvp);
    gl.uniform1f(this.u_time, time);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const instanceBytes = this.bubbleCount * 9 * 4;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.bubbleInstanceVBO);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.bubbleInstanceData.subarray(0, this.bubbleCount * 9));

    gl.bindBuffer(gl.ARRAY_BUFFER, this.bubbleQuadVBO);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.bubbleInstanceVBO);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 36, 0);
    gl.vertexAttribDivisor(1, 1);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 36, 8);
    gl.vertexAttribDivisor(2, 1);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 36, 12);
    gl.vertexAttribDivisor(3, 1);
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 1, gl.FLOAT, false, 36, 28);
    gl.vertexAttribDivisor(4, 1);

    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, this.bubbleCount);

    gl.disableVertexAttribArray(0);
    gl.disableVertexAttribArray(1);
    gl.disableVertexAttribArray(2);
    gl.disableVertexAttribArray(3);
    gl.disableVertexAttribArray(4);
    gl.vertexAttribDivisor(1, 0);
    gl.vertexAttribDivisor(2, 0);
    gl.vertexAttribDivisor(3, 0);
    gl.vertexAttribDivisor(4, 0);

    gl.disable(gl.BLEND);
    this.bubbleCount = 0;
  }

  _renderBBO() {
    const gl = this.gl;
    const bboSlotCount = Math.min(BBO_HISTORY_DEPTH, 3600);
    if (bboSlotCount < 2) return;

    gl.useProgram(this.bboProgram);
    gl.uniformMatrix4fv(this.u_MVP_bbo, false, this.mvp);

    let dataIdx = 0;
    for (let i = 0; i < bboSlotCount; i++) {
      const slot = i % BBO_HISTORY_DEPTH;
      this.bboData[dataIdx++] = (i / bboSlotCount) * this.canvas.width;
      this.bboData[dataIdx++] = this.bboBid[slot];
      this.bboData[dataIdx++] = 0;
    }

    gl.bindBuffer(gl.ARRAY_BUFFER, this.bboVBO);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.bboData.subarray(0, dataIdx));

    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 12, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 12, 8);

    gl.drawArrays(gl.LINE_STRIP, 0, bboSlotCount);

    dataIdx = 0;
    for (let i = 0; i < bboSlotCount; i++) {
      const slot = i % BBO_HISTORY_DEPTH;
      this.bboData[dataIdx++] = (i / bboSlotCount) * this.canvas.width;
      this.bboData[dataIdx++] = this.bboAsk[slot];
      this.bboData[dataIdx++] = 1;
    }

    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.bboData.subarray(0, dataIdx));
    gl.drawArrays(gl.LINE_STRIP, 0, bboSlotCount);

    gl.disableVertexAttribArray(0);
    gl.disableVertexAttribArray(1);
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
    this._computeMVP();
  }

  priceToY(price) {
    const { priceMin, priceMax } = this.viewState;
    return ((priceMax - price) / (priceMax - priceMin)) * this.canvas.height;
  }
}
