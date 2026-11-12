// Run with:  node tests/test_affect.js
const assert = require("assert");
const A = require("../assets/js/affect.js");
const top = (b) => A.dominant(A.scores(b));

assert.strictEqual(top({}), "neutral");
assert.strictEqual(top({ mouthSmileLeft: 0.6, mouthSmileRight: 0.6, cheekSquintLeft: 0.4, cheekSquintRight: 0.4 }), "happiness");
assert.strictEqual(top({ browInnerUp: 0.6, browOuterUpLeft: 0.6, browOuterUpRight: 0.6, eyeWideLeft: 0.6, eyeWideRight: 0.6, jawOpen: 0.7 }), "surprise");
assert.strictEqual(top({ browDownLeft: 0.7, browDownRight: 0.7, mouthPressLeft: 0.6, mouthPressRight: 0.6, eyeSquintLeft: 0.4, eyeSquintRight: 0.4 }), "anger");
assert.strictEqual(top({ noseSneerLeft: 0.6, noseSneerRight: 0.6, mouthUpperUpLeft: 0.5, mouthUpperUpRight: 0.5 }), "disgust");
assert.strictEqual(top({ mouthFrownLeft: 0.6, mouthFrownRight: 0.6, browInnerUp: 0.4 }), "sadness");
const happy = A.valenceArousal(A.scores({ mouthSmileLeft: 0.7, mouthSmileRight: 0.7, cheekSquintLeft: 0.5, cheekSquintRight: 0.5 }));
const sad = A.valenceArousal(A.scores({ mouthFrownLeft: 0.6, mouthFrownRight: 0.6, browInnerUp: 0.4 }));
assert(happy.valence > 0.3 && sad.valence < -0.3, "valence sign");
const p = A.profile([{ scores: A.scores({ mouthSmileLeft: .7, mouthSmileRight: .7 }) }, { scores: A.scores({}) }]);
assert(p.share.happiness === 0.5 && p.share.neutral === 0.5);
console.log("ALL AFFECT TESTS PASSED");
