// Run with:  node tests/test_rl.js
const assert = require("assert");
const RL = require("../assets/js/rl.js");

function train(algo, preset, episodes, seed) {
  const env = RL.preset(preset);
  const ag = new RL.Agent(env, { algo, alpha: 0.5, gamma: 1.0, epsilon: 0.1, seed });
  ag.runEpisodes(episodes);
  return { env, ag };
}

// 1. open grid: every algorithm reaches the goal greedily
for (const algo of ["qlearning", "sarsa", "expected"]) {
  const { ag } = train(algo, "open", 400, 3);
  const g = ag.greedyPath();
  assert(g.reached, algo + " should reach the goal on the open grid");
  console.log("ok open/" + algo, "path length", g.path.length - 1);
}

// 2. cliff walking: Q-learning learns the short, risky path along the cliff; SARSA a safer, longer one
const q = train("qlearning", "cliff", 800, 5), s = train("sarsa", "cliff", 800, 5);
const qLen = q.ag.greedyPath().path.length - 1, sLen = s.ag.greedyPath().path.length - 1;
assert(q.ag.greedyPath().reached && s.ag.greedyPath().reached);
assert(qLen <= sLen, `Q-learning path (${qLen}) should not be longer than SARSA path (${sLen})`);
const tail = (ag) => ag.history.slice(-200).reduce((a, b) => a + b, 0) / 200;
assert(tail(s.ag) > tail(q.ag), "online return: SARSA should beat Q-learning on cliff (safer while exploring)");
console.log("ok cliff: qLen", qLen, "sLen", sLen, "online returns", tail(q.ag).toFixed(1), tail(s.ag).toFixed(1));

// 3. walls block movement
const e = new RL.GridWorld(3, 3);
e.set(e.idx(1, 2), RL.WALL);
assert.strictEqual(e.step(e.idx(0, 2), 1, null).s2, e.idx(0, 2));
console.log("ok walls");
console.log("ALL RL TESTS PASSED");
