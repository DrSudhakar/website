/* Remote photoplethysmography (rPPG) signal processing. Pure maths, no DOM → testable in Node.
   Pipeline: mean RGB of a skin ROI per frame → POS projection (Wang et al., 2017, IEEE TBME)
             → detrend + band-pass 0.7–3.5 Hz → heart rate (spectral peak) → beat detection → HRV (RMSSD, SDNN).
   node tests/test_rppg.js */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RPPG = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const mean = (a) => a.reduce((s, v) => s + v, 0) / (a.length || 1);
  const std = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((v) => (v - m) ** 2))); };

  /** Resample irregular (t, v) samples onto a uniform grid at fs Hz. t in seconds. */
  function resample(t, v, fs) {
    const out = [], t0 = t[0], t1 = t[t.length - 1];
    let j = 0;
    for (let x = t0; x <= t1; x += 1 / fs) {
      while (j < t.length - 2 && t[j + 1] < x) j++;
      const f = (x - t[j]) / (t[j + 1] - t[j] || 1);
      out.push(v[j] + f * (v[j + 1] - v[j]));
    }
    return out;
  }

  /** Moving-average detrend (removes slow drift) */
  function detrend(x, win) {
    const out = new Array(x.length); let acc = 0; const q = [];
    for (let i = 0; i < x.length; i++) { q.push(x[i]); acc += x[i]; if (q.length > win) acc -= q.shift(); out[i] = x[i] - acc / q.length; }
    return out;
  }

  /** 2nd-order Butterworth band-pass applied forward+backward (zero phase). */
  function bandpass(x, fs, lo, hi) {
    function biquad(x, fc, type) {
      const w0 = 2 * Math.PI * fc / fs, cos = Math.cos(w0), alpha = Math.sin(w0) / (2 * Math.SQRT1_2);
      let b0, b1, b2; const a0 = 1 + alpha, a1 = -2 * cos, a2 = 1 - alpha;
      if (type === "lp") { b0 = (1 - cos) / 2; b1 = 1 - cos; b2 = (1 - cos) / 2; } else { b0 = (1 + cos) / 2; b1 = -(1 + cos); b2 = (1 + cos) / 2; }
      const run = (s) => { const y = new Array(s.length).fill(0); let x1 = s[0], x2 = s[0], y1 = s[0] * 0, y2 = 0;
        for (let n = 0; n < s.length; n++) { y[n] = (b0 * s[n] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0; x2 = x1; x1 = s[n]; y2 = y1; y1 = y[n]; } return y; };
      const f = run(x); return run(f.reverse()).reverse();
    }
    return biquad(biquad(x, hi, "lp"), lo, "hp");
  }

  /** POS algorithm. rgb = [[r,g,b], ...] at uniform fs. Returns pulse signal (same length). */
  function pos(rgb, fs) {
    const N = rgb.length, L = Math.max(10, Math.round(1.6 * fs)), H = new Array(N).fill(0);
    for (let n = L - 1; n < N; n++) {
      const seg = rgb.slice(n - L + 1, n + 1);
      const m = [0, 1, 2].map((c) => mean(seg.map((p) => p[c])) || 1);
      const C = seg.map((p) => [p[0] / m[0], p[1] / m[1], p[2] / m[2]]);
      const S1 = C.map((c) => c[1] - c[2]), S2 = C.map((c) => c[1] + c[2] - 2 * c[0]);
      const alpha = std(S1) / (std(S2) || 1);
      const h = S1.map((v, i) => v + alpha * S2[i]); const hm = mean(h);
      for (let i = 0; i < L; i++) H[n - L + 1 + i] += h[i] - hm; // overlap-add
    }
    return H;
  }

  /** Spectral estimate of heart rate: DFT power over 0.7–3.5 Hz with parabolic interpolation. Returns {bpm, snr, freqs, power} */
  function spectrum(x, fs) {
    const N = x.length, win = x.map((v, i) => v * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (N - 1))));
    const fmin = 0.7, fmax = 3.5, df = 0.01, freqs = [], power = [];
    for (let f = fmin; f <= fmax + 1e-9; f += df) {
      let re = 0, im = 0; const w = 2 * Math.PI * f / fs;
      for (let n = 0; n < N; n++) { re += win[n] * Math.cos(w * n); im -= win[n] * Math.sin(w * n); }
      freqs.push(f); power.push(re * re + im * im);
    }
    let k = 0; for (let i = 1; i < power.length; i++) if (power[i] > power[k]) k = i;
    let f0 = freqs[k];
    if (k > 0 && k < power.length - 1) { const a = power[k - 1], b = power[k], c = power[k + 1], d = a - 2 * b + c; if (d !== 0) f0 += (0.5 * (a - c) / d) * df; }
    // SNR: power within ±0.1 Hz of peak and its 2nd harmonic vs rest
    let sig = 0, tot = 0;
    for (let i = 0; i < freqs.length; i++) { tot += power[i]; if (Math.abs(freqs[i] - f0) <= 0.1 || Math.abs(freqs[i] - 2 * f0) <= 0.1) sig += power[i]; }
    const snr = 10 * Math.log10(sig / Math.max(tot - sig, 1e-12));
    return { bpm: f0 * 60, snr, freqs, power };
  }

  /** Peak detection on band-passed pulse (fs Hz). Returns peak times (s). */
  function beats(x, fs) {
    const minDist = Math.round(fs * 0.33), thr = 0.1 * Math.max(...x.map(Math.abs)), peaks = [];
    for (let i = 1; i < x.length - 1; i++) {
      if (x[i] > x[i - 1] && x[i] >= x[i + 1] && x[i] > thr) {
        if (peaks.length && i - peaks[peaks.length - 1] < minDist) { if (x[i] > x[peaks[peaks.length - 1]]) peaks[peaks.length - 1] = i; } else peaks.push(i);
      }
    }
    // parabolic sub-sample refinement
    return peaks.map((i) => { const a = x[i - 1], b = x[i], c = x[i + 1], d = a - 2 * b + c; return (i + (d ? 0.5 * (a - c) / d : 0)) / fs; });
  }

  /** HRV from beat times: IBIs in ms with outlier rejection. */
  function hrv(peakTimes) {
    const ibi = []; for (let i = 1; i < peakTimes.length; i++) ibi.push((peakTimes[i] - peakTimes[i - 1]) * 1000);
    if (ibi.length < 4) return null;
    const med = ibi.slice().sort((a, b) => a - b)[Math.floor(ibi.length / 2)];
    const clean = ibi.filter((v) => v > 0.7 * med && v < 1.3 * med);
    if (clean.length < 4) return null;
    const diffs = []; for (let i = 1; i < clean.length; i++) diffs.push(clean[i] - clean[i - 1]);
    return { meanIBI: mean(clean), sdnn: std(clean), rmssd: Math.sqrt(mean(diffs.map((d) => d * d))), n: clean.length, ibi: clean };
  }

  /** Full analysis: samples = [{t (s), r, g, b}] */
  function analyze(samples, opts) {
    opts = Object.assign({ fs: 30 }, opts || {});
    if (samples.length < opts.fs * 8) return { ok: false, reason: "Need at least ~8 seconds of video." };
    const t = samples.map((s) => s.t), fs = opts.fs;
    const rgb = [0, 1, 2].map((c) => resample(t, samples.map((s) => [s.r, s.g, s.b][c]), fs));
    const frames = rgb[0].map((_, i) => [rgb[0][i], rgb[1][i], rgb[2][i]]);
    const raw = pos(frames, fs);
    const sig = bandpass(detrend(raw, Math.round(fs)), fs, 0.7, 3.5);
    const trim = Math.round(fs * 1.5); const core = sig.slice(trim, sig.length - trim);
    const sp = spectrum(core, fs), f0 = sp.bpm / 60;
    // narrow the band around the dominant rate before peak picking, so the dicrotic notch / 2nd harmonic is not counted as a beat
    const narrow = bandpass(core, fs, Math.max(0.6, f0 - 0.4), Math.min(3.6, f0 + 0.4));
    const pk = beats(narrow, fs), v = hrv(pk);
    return { ok: true, bpm: sp.bpm, snr: sp.snr, signal: narrow, fs, peaks: pk, hrv: v, spectrum: sp,
      quality: sp.snr > 3 ? "good" : sp.snr > 0 ? "fair" : "poor" };
  }

  return { analyze, pos, bandpass, detrend, spectrum, beats, hrv, resample };
});
