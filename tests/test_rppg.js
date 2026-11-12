// Run with:  node tests/test_rppg.js
// Synthesises a skin-colour video trace whose colour oscillates at a known heart rate, adds noise + motion drift + jittered timestamps,
// and checks that the pipeline recovers the heart rate and a plausible HRV.
const assert = require("assert");
const RPPG = require("../assets/js/rppg.js");

function rng(seed) { let a = seed; return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function synth(bpm, seconds, fs, noise, seed) {
  const r = rng(seed), out = [], f = bpm / 60;
  for (let i = 0; i < seconds * fs; i++) {
    const t = i / fs + (r() - 0.5) * 0.004;              // timestamp jitter
    const pulse = Math.sin(2 * Math.PI * f * t) + 0.25 * Math.sin(4 * Math.PI * f * t + 1);
    const drift = 4 * Math.sin(2 * Math.PI * 0.05 * t);   // slow illumination drift
    // haemoglobin absorbs green most strongly; pulse modulates G more than R and B
    out.push({ t, r: 180 + drift + 0.25 * pulse + (r() - .5) * noise, g: 120 + drift + 0.9 * pulse + (r() - .5) * noise, b: 100 + drift + 0.45 * pulse + (r() - .5) * noise });
  }
  return out;
}

for (const bpm of [52, 72, 96, 130]) {
  const res = RPPG.analyze(synth(bpm, 30, 30, 1.2, bpm), { fs: 30 });
  assert(res.ok);
  assert(Math.abs(res.bpm - bpm) < 2.5, `expected ~${bpm} bpm, got ${res.bpm.toFixed(1)}`);
  const beatBpm = 60 / (res.hrv.meanIBI / 1000);
  assert(Math.abs(beatBpm - bpm) < 4, `beat-derived rate ${beatBpm.toFixed(1)} should match ${bpm}`);
  console.log(`ok ${bpm} bpm → spectral ${res.bpm.toFixed(1)}, beats ${beatBpm.toFixed(1)}, SNR ${res.snr.toFixed(1)} dB, RMSSD ${res.hrv.rmssd.toFixed(1)} ms (synthetic metronome ⇒ should be small)`);
}
assert(RPPG.analyze(synth(70, 3, 30, 1, 1), { fs: 30 }).ok === false, "short clips must be rejected");
// pure noise must not report good quality
const noise = Array.from({ length: 900 }, (_, i) => ({ t: i / 30, r: 150 + Math.random() * 5, g: 110 + Math.random() * 5, b: 90 + Math.random() * 5 }));
const nres = RPPG.analyze(noise, { fs: 30 });
assert(nres.quality !== "good", "noise should not be rated good, SNR=" + nres.snr);
console.log("ok noise quality:", nres.quality, nres.snr.toFixed(1), "dB");
console.log("ALL rPPG TESTS PASSED");
