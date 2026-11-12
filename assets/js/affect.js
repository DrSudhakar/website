/* Facial-expression → affect profile. Pure maths (testable in Node: node tests/test_affect.js).
   Input: MediaPipe Face Landmarker blendshape scores {name: 0..1}.
   Method: transparent, FACS-inspired weighting of the Action Units each basic emotion is usually associated with
   (EMFACS, Ekman & Friesen). This estimates *facial movement*, not felt emotion — see the caveat on the page. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Affect = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";
  const EMOTIONS = ["happiness", "sadness", "surprise", "anger", "disgust", "fear", "neutral"];

  // weights: blendshape (L/R averaged) → contribution
  const RECIPES = {
    happiness: { mouthSmile: 0.65, cheekSquint: 0.35 },                                   // AU12 + AU6
    sadness:   { mouthFrown: 0.5, browInnerUp: 0.3, mouthShrugLower: 0.1, browDown: 0.1 },   // AU15 + AU1 (+AU4)
    surprise:  { browInnerUp: 0.25, browOuterUp: 0.25, eyeWide: 0.25, jawOpen: 0.25 },    // AU1+2+5+26
    anger:     { browDown: 0.4, eyeSquint: 0.2, mouthPress: 0.25, noseSneer: 0.15 },       // AU4+7+23(+9)
    disgust:   { noseSneer: 0.5, mouthUpperUp: 0.3, browDown: 0.1, mouthShrugUpper: 0.1 },// AU9+10
    fear:      { browInnerUp: 0.25, eyeWide: 0.3, mouthStretch: 0.25, browDown: 0.1, jawOpen: 0.1 } // AU1+2+4+5+20
  };
  // sensitivity: blendshape scores for natural expressions rarely exceed ~0.5, so rescale
  const GAIN = { happiness: 1.6, sadness: 2.2, surprise: 1.7, anger: 2.2, disgust: 2.2, fear: 2.2 };

  function bs(b, name) { // average of Left/Right variants, or the plain name
    if (b[name] !== undefined) return b[name];
    const l = b[name + "Left"], r = b[name + "Right"];
    if (l === undefined && r === undefined) return 0;
    return ((l || 0) + (r || 0)) / ((l !== undefined) + (r !== undefined));
  }
  const clamp01 = (x) => Math.max(0, Math.min(1, x));

  function scores(b) {
    const out = {};
    for (const e of Object.keys(RECIPES)) {
      let s = 0; for (const [k, w] of Object.entries(RECIPES[e])) if (w) s += w * bs(b, k);
      out[e] = clamp01(s * GAIN[e]);
    }
    // happiness suppresses brow-driven false positives (smiling squints the eyes and raises cheeks)
    out.anger *= 1 - 0.6 * out.happiness; out.sadness *= 1 - 0.6 * out.happiness; out.fear *= 1 - 0.4 * out.happiness;
    const peak = Math.max(...Object.values(out));
    out.neutral = clamp01(1 - peak * 1.5);
    return out;
  }

  /** Valence (−1..1) and arousal (0..1) as a weighted blend of the emotion scores (circumplex positions). */
  const VA = { happiness: [0.8, 0.5], sadness: [-0.7, 0.2], surprise: [0.2, 0.9], anger: [-0.7, 0.8], disgust: [-0.6, 0.5], fear: [-0.7, 0.85], neutral: [0, 0.1] };
  function valenceArousal(sc) {
    let v = 0, a = 0, tot = 0;
    for (const e of EMOTIONS) { v += sc[e] * VA[e][0]; a += sc[e] * VA[e][1]; tot += sc[e]; }
    return tot > 0 ? { valence: v / tot, arousal: a / tot } : { valence: 0, arousal: 0 };
  }
  function dominant(sc) { return EMOTIONS.reduce((m, e) => (sc[e] > sc[m] ? e : m), "neutral"); }

  /** Aggregate a recorded session: [{t, scores}] → profile */
  function profile(frames) {
    if (!frames.length) return null;
    const mean = {}, share = {};
    EMOTIONS.forEach((e) => { mean[e] = 0; share[e] = 0; });
    let v = 0, a = 0;
    frames.forEach((f) => { EMOTIONS.forEach((e) => (mean[e] += f.scores[e])); share[dominant(f.scores)]++; const va = valenceArousal(f.scores); v += va.valence; a += va.arousal; });
    EMOTIONS.forEach((e) => { mean[e] /= frames.length; share[e] /= frames.length; });
    return { n: frames.length, mean, share, valence: v / frames.length, arousal: a / frames.length };
  }

  return { EMOTIONS, scores, valenceArousal, dominant, profile };
});
