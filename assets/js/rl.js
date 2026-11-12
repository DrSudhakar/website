/* Tabular RL on a gridworld. Pure logic (no DOM) so it can be unit-tested in Node:  node tests/test_rl.js */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RL = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  // cell types
  const EMPTY = 0, WALL = 1, GOAL = 2, CLIFF = 3, START = 4;
  const ACTIONS = [[0, -1], [1, 0], [0, 1], [-1, 0]]; // up, right, down, left  (dx, dy)
  const ARROWS = ["↑", "→", "↓", "←"];

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  class GridWorld {
    constructor(w, h) {
      this.w = w; this.h = h;
      this.cells = new Uint8Array(w * h);
      this.start = (h - 1) * w; // bottom-left
      this.cells[this.start] = START;
      this.rewards = { step: -1, goal: 50, cliff: -100 };
      this.slip = 0; // probability of a random action instead of the chosen one
    }
    idx(x, y) { return y * this.w + x; }
    set(i, type) {
      if (type === START) { this.cells[this.start] = EMPTY; this.start = i; }
      else if (i === this.start) return; // start cell can only be moved, not erased
      this.cells[i] = type;
    }
    isTerminal(i) { return this.cells[i] === GOAL; }
    step(s, a, rng) {
      if (rng && this.slip > 0 && rng() < this.slip) a = Math.floor(rng() * 4);
      const x = s % this.w, y = (s / this.w) | 0;
      const nx = x + ACTIONS[a][0], ny = y + ACTIONS[a][1];
      let s2 = s;
      if (nx >= 0 && nx < this.w && ny >= 0 && ny < this.h && this.cells[this.idx(nx, ny)] !== WALL) s2 = this.idx(nx, ny);
      const t = this.cells[s2];
      if (t === GOAL) return { s2, r: this.rewards.goal, done: true };
      if (t === CLIFF) return { s2: this.start, r: this.rewards.cliff, done: false };
      return { s2, r: this.rewards.step, done: false };
    }
  }

  class Agent {
    constructor(env, opts) {
      this.env = env;
      this.opts = Object.assign({ algo: "qlearning", alpha: 0.5, gamma: 0.95, epsilon: 0.1, seed: 1, maxSteps: 300 }, opts || {});
      this.rng = mulberry32(this.opts.seed);
      this.reset();
    }
    reset() {
      this.Q = new Float64Array(this.env.w * this.env.h * 4);
      this.episode = 0; this.steps = 0; this.history = [];
      this.beginEpisode();
    }
    beginEpisode() {
      this.s = this.env.start; this.epReturn = 0; this.epSteps = 0;
      this.a = this.policy(this.s);
    }
    qmax(s) { let m = -Infinity; for (let a = 0; a < 4; a++) m = Math.max(m, this.Q[s * 4 + a]); return m; }
    greedy(s) {
      let best = [], m = -Infinity;
      for (let a = 0; a < 4; a++) { const q = this.Q[s * 4 + a]; if (q > m + 1e-12) { m = q; best = [a]; } else if (Math.abs(q - m) <= 1e-12) best.push(a); }
      return best[Math.floor(this.rng() * best.length)];
    }
    policy(s) { return this.rng() < this.opts.epsilon ? Math.floor(this.rng() * 4) : this.greedy(s); }
    expectedQ(s) {
      const e = this.opts.epsilon; let m = -Infinity;
      for (let a = 0; a < 4; a++) m = Math.max(m, this.Q[s * 4 + a]);
      let nBest = 0; for (let a = 0; a < 4; a++) if (Math.abs(this.Q[s * 4 + a] - m) <= 1e-12) nBest++;
      let v = 0;
      for (let a = 0; a < 4; a++) { const isBest = Math.abs(this.Q[s * 4 + a] - m) <= 1e-12; v += ((isBest ? (1 - e) / nBest : 0) + e / 4) * this.Q[s * 4 + a]; }
      return v;
    }
    /** one environment step; returns true if the episode ended */
    step() {
      const { alpha, gamma, algo } = this.opts;
      const s = this.s, a = this.a;
      const { s2, r, done } = this.env.step(s, a, this.rng);
      const a2 = this.policy(s2);
      let target;
      if (done) target = r;
      else if (algo === "sarsa") target = r + gamma * this.Q[s2 * 4 + a2];
      else if (algo === "expected") target = r + gamma * this.expectedQ(s2);
      else target = r + gamma * this.qmax(s2);
      this.Q[s * 4 + a] += alpha * (target - this.Q[s * 4 + a]);
      this.s = s2; this.a = a2; this.epReturn += r; this.epSteps++; this.steps++;
      if (done || this.epSteps >= this.opts.maxSteps) {
        this.history.push(this.epReturn); this.episode++; this.beginEpisode(); return true;
      }
      return false;
    }
    runEpisodes(n) { let c = 0; while (c < n) if (this.step()) c++; }
    /** greedy path from start (for display / evaluation) */
    greedyPath(limit) {
      const path = [this.env.start]; let s = this.env.start; const seen = new Set();
      for (let i = 0; i < (limit || 200); i++) {
        const a = this.greedy(s); const r = this.env.step(s, a, null);
        path.push(r.s2); if (r.done) return { path, reached: true };
        const key = r.s2 + ":" + a; if (seen.has(key)) break; seen.add(key); s = r.s2;
      }
      return { path, reached: false };
    }
  }

  // presets ---------------------------------------------------------------
  function preset(name) {
    const e = new GridWorld(10, 6);
    if (name === "cliff") {
      e.start = e.idx(0, 5); e.cells.fill(EMPTY); e.cells[e.start] = START;
      for (let x = 1; x < 9; x++) e.cells[e.idx(x, 5)] = CLIFF;
      e.cells[e.idx(9, 5)] = GOAL;
    } else if (name === "maze") {
      e.cells.fill(EMPTY); e.start = e.idx(0, 5); e.cells[e.start] = START;
      for (let y = 0; y < 5; y++) e.cells[e.idx(3, y)] = WALL;
      for (let y = 1; y < 6; y++) e.cells[e.idx(6, y)] = WALL;
      e.cells[e.idx(9, 0)] = GOAL;
    } else { // "open"
      e.cells.fill(EMPTY); e.start = e.idx(0, 5); e.cells[e.start] = START;
      e.cells[e.idx(9, 0)] = GOAL; e.cells[e.idx(4, 2)] = WALL; e.cells[e.idx(4, 3)] = WALL; e.cells[e.idx(5, 3)] = WALL;
    }
    return e;
  }

  return { GridWorld, Agent, preset, EMPTY, WALL, GOAL, CLIFF, START, ACTIONS, ARROWS };
});
