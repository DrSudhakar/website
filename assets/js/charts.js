/* Small dependency-free chart helpers for the demo pages. */
window.Charts = (function () {
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const PALETTE = ["#2b6cb0", "#c05621", "#2f855a", "#805ad5", "#b83280", "#718096"];

  /** groups = categories on the x axis (e.g. microstates A–D); series = [{name, values[], errors[]}] */
  function groupedBars(canvas, groups, series, opts) {
    opts = opts || {};
    const dpr = window.devicePixelRatio || 1, W = canvas.clientWidth || 600, H = opts.height || 220;
    canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.height = H + "px";
    const g = canvas.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const padL = 44, padB = 34, padT = 12, padR = 10, w = W - padL - padR, h = H - padT - padB;
    const all = series.flatMap((s) => s.values.map((v, i) => (v || 0) + ((s.errors || [])[i] || 0)));
    const max = opts.max || Math.max(1e-9, ...all) * 1.1;
    g.strokeStyle = css("--line"); g.fillStyle = css("--muted"); g.font = "11px system-ui"; g.textAlign = "right";
    for (let i = 0; i <= 4; i++) { const y = padT + h - (i / 4) * h; g.beginPath(); g.moveTo(padL, y); g.lineTo(W - padR, y); g.stroke(); g.fillText((max * i / 4).toFixed(max < 10 ? 1 : 0), padL - 6, y + 4); }
    const gw = w / groups.length, bw = Math.min(34, (gw * 0.8) / series.length);
    g.textAlign = "center";
    groups.forEach((lab, gi) => {
      const x0 = padL + gi * gw + (gw - bw * series.length) / 2;
      series.forEach((s, si) => {
        const v = s.values[gi] || 0, bh = (v / max) * h, x = x0 + si * bw, y = padT + h - bh;
        g.fillStyle = s.color || PALETTE[si % PALETTE.length]; g.fillRect(x + 1, y, bw - 2, bh);
        const e = (s.errors || [])[gi];
        if (e) { g.strokeStyle = css("--text"); g.beginPath(); g.moveTo(x + bw / 2, padT + h - ((v - e) / max) * h); g.lineTo(x + bw / 2, padT + h - ((v + e) / max) * h); g.stroke(); }
      });
      g.fillStyle = css("--text"); g.font = "12px system-ui"; g.fillText(lab, padL + gi * gw + gw / 2, H - 14);
    });
    if (opts.title) { g.fillStyle = css("--muted"); g.textAlign = "left"; g.font = "11px system-ui"; g.fillText(opts.title, padL, 10); }
    return series.map((s, i) => ({ name: s.name, color: s.color || PALETTE[i % PALETTE.length] }));
  }
  function legend(items) { return `<div class="legend">${items.map((i) => `<span><i style="background:${i.color}"></i>${i.name}</span>`).join("")}</div>`; }

  /** square matrix → heat table (values 0..1) */
  function heatTable(labels, M, fmt) {
    const rows = M.map((r, i) => `<tr><th>${labels[i]}</th>${r.map((v) => `<td style="background:color-mix(in srgb, var(--accent-2) ${Math.round(Math.min(1, v) * 85)}%, transparent);text-align:center">${(fmt || ((x) => x.toFixed(2)))(v)}</td>`).join("")}</tr>`).join("");
    return `<table style="width:auto"><thead><tr><th>from \\ to</th>${labels.map((l) => `<th style="text-align:center">${l}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  }
  return { groupedBars, legend, heatTable, PALETTE };
})();
