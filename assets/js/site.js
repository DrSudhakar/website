/* ==========================================================================
   site.js — shared by every page.
   1. Builds the header (navigation tabs) and footer.
   2. Fills any element that has  data-render="..."  from the JSON files in /data.

   TO ADD A NEW TAB: add one line to NAV below, then create the page file
   (copy templates/page-template.html). That's all.
   ========================================================================== */
(function () {
  "use strict";

  // ---- 1. Navigation: edit this list to add / remove / reorder tabs --------
  const NAV = [
    { label: "Home", href: "index.html" },
    { label: "Research", href: "research.html" },
    { label: "Publications", href: "publications.html" },
    { label: "Teaching", href: "teaching.html" },
    { label: "Lab", href: "lab.html" },
    { label: "Vacancies", href: "vacancies.html" },
    { label: "Work at a Glance", href: "glance.html", match: ["glance.html", "demos/"] },
    { label: "Talks & Videos", href: "videos.html" },
    { label: "CV", href: "cv.html" },
  ];

  // ---- helpers ------------------------------------------------------------
  const script = document.currentScript;
  const ROOT = new URL("../../", script.src).href; // site root, whatever the page depth
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => {
    u = String(u || "").trim();
    if (!u) return "";
    if (/^(https?:|mailto:)/i.test(u)) return u;
    if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return ""; // blocks javascript:, data:, etc.
    return ROOT + u.replace(/^\//, "");
  };
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtDate(d) {
    const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$/.exec(String(d || ""));
    if (!m) return esc(d || "");
    const [, y, mo, da] = m;
    return [da ? Number(da) : "", mo ? MONTHS[Number(mo) - 1] : "", y].filter(Boolean).join(" ");
  }
  const cache = {};
  async function loadJSON(path, fallback) {
    if (cache[path]) return cache[path];
    cache[path] = fetch(ROOT + path, { cache: "no-cache" })
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch((e) => { console.warn("Could not load", path, e); return fallback; });
    return cache[path];
  }
  function ytId(url) {
    const m = /(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/|v\/))([A-Za-z0-9_-]{11})/.exec(url || "");
    return m ? m[1] : "";
  }
  const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
  const empty = (msg) => `<div class="empty">${msg}</div>`;

  // ---- header / footer ----------------------------------------------------
  async function buildChrome() {
    const site = await loadJSON("data/site.json", { name: "Your Name" });
    const here = location.pathname.replace(/\/+$/, "");
    const rel = here.startsWith(new URL(ROOT).pathname.replace(/\/+$/, "")) ? here.slice(new URL(ROOT).pathname.replace(/\/+$/, "").length) : here;
    const cur = rel.replace(/^\//, "") || "index.html";
    const links = NAV.map((n) => {
      const matches = n.match || [n.href];
      const active = matches.some((m) => (m.endsWith("/") ? cur.startsWith(m) : cur === m)) || (cur === "" && n.href === "index.html");
      return `<a href="${ROOT}${n.href}"${active ? ' aria-current="page"' : ""}>${esc(n.label)}</a>`;
    }).join("");
    const header = el(`<header class="site-header"><div class="wrap">
        <a class="brand" href="${ROOT}index.html">${esc(site.name)}</a>
        <nav class="nav" id="nav" aria-label="Main">${links}</nav>
        <button class="theme-btn" id="theme-btn" title="Toggle dark / light" aria-label="Toggle dark or light theme">◐</button>
        <button class="nav-toggle" id="nav-toggle" aria-expanded="false" aria-controls="nav">Menu</button>
      </div></header>`);
    document.body.prepend(header);
    document.body.prepend(el('<a class="skip" href="#main">Skip to content</a>'));
    const social = site.social || {};
    const foot = el(`<footer class="site-footer"><div class="wrap">
        <div>© ${new Date().getFullYear()} ${esc(site.name)} · ${esc(site.institute || "")}</div>
        <div>${[["scholar", "Google Scholar"], ["orcid", "ORCID"], ["linkedin", "LinkedIn"], ["x", "X"], ["youtube", "YouTube"], ["github", "GitHub"]]
          .filter(([k]) => social[k]).map(([k, l]) => `<a href="${esc(safeUrl(social[k]))}" rel="me noopener" target="_blank">${l}</a>`).join(" · ")}</div>
      </div></footer>`);
    document.body.append(foot);
    document.getElementById("nav-toggle").addEventListener("click", (e) => {
      const open = document.getElementById("nav").classList.toggle("open");
      e.currentTarget.setAttribute("aria-expanded", open);
    });
    const root = document.documentElement;
    try { const t = localStorage.getItem("theme"); if (t) root.dataset.theme = t; } catch (_) {}
    document.getElementById("theme-btn").addEventListener("click", () => {
      const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (_) {}
    });
  }

  // ---- renderers ----------------------------------------------------------
  const R = {};

  R.hero = async (node) => {
    const s = await loadJSON("data/site.json", {});
    const social = s.social || {};
    const btn = (k, label) => (social[k] ? `<a class="btn" href="${esc(safeUrl(social[k]))}" target="_blank" rel="me noopener">${label}</a>` : "");
    node.innerHTML = `<div class="hero">
      <img src="${esc(safeUrl(s.photo))}" alt="Portrait of ${esc(s.name)}" width="240" height="300">
      <div>
        <h1>${esc(s.name)}</h1>
        <div class="role">${esc(s.title)}, ${esc(s.department)}</div>
        <div class="affil">${esc(s.institute)}${s.location ? " · " + esc(s.location) : ""}</div>
        <p class="lede" style="margin-bottom:0">${esc(s.tagline)}</p>
        <div class="links">
          ${s.email ? `<a class="btn primary" href="mailto:${esc(s.email)}">✉ Email</a>` : ""}
          ${btn("scholar", "Google Scholar")}${btn("orcid", "ORCID")}${btn("linkedin", "LinkedIn")}${btn("x", "X / Twitter")}${btn("youtube", "YouTube")}${btn("github", "GitHub")}
        </div>
      </div></div>`;
  };

  R.bio = async (node) => {
    const s = await loadJSON("data/site.json", {});
    node.innerHTML = (s.bio || []).map((p) => `<p>${esc(p)}</p>`).join("");
  };

  R.interests = async (node) => {
    const s = await loadJSON("data/site.json", {});
    node.innerHTML = `<ul class="chips">${(s.interests || []).map((i) => `<li class="chip">${esc(i)}</li>`).join("")}</ul>`;
  };

  R.news = async (node) => {
    const limit = Number(node.dataset.limit) || 99;
    const items = (await loadJSON("data/news.json", [])).slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, limit);
    node.innerHTML = items.length
      ? `<ul class="news">${items.map((n) => `<li><time>${fmtDate(n.date)}</time><div>${esc(n.text)}${n.link ? ` <a href="${esc(safeUrl(n.link))}">More →</a>` : ""}</div></li>`).join("")}</ul>`
      : empty("No news yet.");
  };

  R.metrics = async (node) => {
    const m = await loadJSON("data/metrics.json", null);
    if (!m) { node.innerHTML = ""; return; }
    const years = Object.keys(m.per_year || {}).sort();
    const max = Math.max(1, ...years.map((y) => m.per_year[y]));
    node.innerHTML = `<div class="metrics">
        <div class="card metric"><b>${esc(m.citations)}</b><span>Citations</span></div>
        <div class="card metric"><b>${esc(m.h_index)}</b><span>h-index</span></div>
        <div class="card metric"><b>${esc(m.i10_index)}</b><span>i10-index</span></div>
      </div>
      ${years.length ? `<div class="bars" style="margin-bottom:30px" aria-label="Citations per year">${years.map((y) => `<div class="bar" style="height:${Math.max(3, (m.per_year[y] / max) * 100)}%" title="${y}: ${m.per_year[y]}"><i>${m.per_year[y]}</i><em>${y.slice(2)}</em></div>`).join("")}</div>` : ""}
      <p class="note">Source: Google Scholar${m.updated ? ", updated " + fmtDate(m.updated) : ""}. Refreshed automatically every week.</p>`;
  };

  function pubHTML(p, me) {
    const authors = (p.authors || []).map((a) => (me && a.trim().toLowerCase() === me.toLowerCase() ? `<b>${esc(a)}</b>` : esc(a))).join(", ");
    const status = p.status === "under-review" ? '<span class="chip warn">Under review</span>' : p.status === "in-progress" ? '<span class="chip">In preparation</span>' : "";
    const doi = p.doi ? `<a class="btn small" href="${esc(safeUrl(/^https?:/.test(p.doi) ? p.doi : "https://doi.org/" + p.doi))}" target="_blank" rel="noopener">DOI</a>` : "";
    const url = p.url ? `<a class="btn small" href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener">Link</a>` : "";
    const pdf = p.pdf ? `<a class="btn small" href="${esc(safeUrl(p.pdf))}" target="_blank" rel="noopener">PDF</a>` : "";
    const code = p.code ? `<a class="btn small" href="${esc(safeUrl(p.code))}" target="_blank" rel="noopener">Code</a>` : "";
    const cites = p.citations ? `<span class="chip">Cited by ${esc(p.citations)}</span>` : "";
    return `<li class="pub"><div class="t">${esc(p.title)}</div><div class="a">${authors}</div>
      <div class="v">${esc(p.venue || "")}${p.year ? " (" + esc(p.year) + ")" : ""}</div>
      <div class="tags">${status}${cites}${doi}${url}${pdf}${code}</div></li>`;
  }

  R.publications = async (node) => {
    const [pubs, site] = await Promise.all([loadJSON("data/publications.json", []), loadJSON("data/site.json", {})]);
    const me = site.name;
    const onlyFeatured = node.dataset.featured === "true";
    const limit = Number(node.dataset.limit) || 0;
    if (onlyFeatured || limit) {
      let list = pubs.filter((p) => !onlyFeatured || p.featured);
      list = list.sort((a, b) => (b.year || 0) - (a.year || 0)).slice(0, limit || 99);
      node.innerHTML = list.length ? `<ul class="pub-list">${list.map((p) => pubHTML(p, me)).join("")}</ul>` : empty("No publications yet.");
      return;
    }
    const types = { journal: "Journal papers", conference: "Conference papers", preprint: "Preprints & under review", dataset: "Datasets", inprogress: "In preparation", other: "Other" };
    const typeKeys = Object.keys(types).filter((t) => pubs.some((p) => (p.type || "other") === t));
    node.innerHTML = `<div class="toolbar">
        <input type="search" id="pub-q" placeholder="Search title, author, venue…" aria-label="Search publications" style="min-width:240px">
        <select id="pub-type" aria-label="Filter by type"><option value="">All types</option>${typeKeys.map((t) => `<option value="${t}">${types[t]}</option>`).join("")}</select>
        <span class="note" id="pub-count"></span></div><div id="pub-out"></div>`;
    const out = node.querySelector("#pub-out");
    function draw() {
      const q = node.querySelector("#pub-q").value.toLowerCase();
      const t = node.querySelector("#pub-type").value;
      const list = pubs.filter((p) => (!t || (p.type || "other") === t) && (!q || [p.title, p.venue, (p.authors || []).join(" ")].join(" ").toLowerCase().includes(q)))
        .sort((a, b) => (b.year || 0) - (a.year || 0) || String(a.title).localeCompare(b.title));
      node.querySelector("#pub-count").textContent = `${list.length} of ${pubs.length}`;
      const byYear = {};
      list.forEach((p) => (byYear[p.year || "n.d."] = byYear[p.year || "n.d."] || []).push(p));
      out.innerHTML = list.length ? Object.keys(byYear).sort((a, b) => b - a).map((y) => `<h3 class="year-head">${esc(y)}</h3><ul class="pub-list">${byYear[y].map((p) => pubHTML(p, me)).join("")}</ul>`).join("") : empty("No matching publications.");
    }
    node.querySelector("#pub-q").addEventListener("input", draw);
    node.querySelector("#pub-type").addEventListener("change", draw);
    draw();
  };

  R.projects = async (node) => {
    const items = await loadJSON("data/projects.json", []);
    node.innerHTML = items.length ? `<div class="grid cols-2">${items.map((p) => `<div class="card">
        <div class="meta">${esc(p.area || "")}</div><h3>${esc(p.title)}</h3>
        <p>${esc(p.summary || "")}</p>
        <div class="tags"><span class="chip ${/ongoing|active/i.test(p.status) ? "ok" : /review/i.test(p.status) ? "warn" : ""}">${esc(p.status || "")}</span></div>
        ${p.people && p.people.length ? `<p class="note" style="margin:10px 0 0">${p.people.map(esc).join(", ")}</p>` : ""}
        ${p.link ? `<p style="margin:8px 0 0"><a href="${esc(safeUrl(p.link))}">Read more →</a></p>` : ""}</div>`).join("")}</div>` : empty("No projects yet.");
  };

  R.grants = async (node) => {
    const items = (await loadJSON("data/grants.json", [])).slice().sort((a, b) => String(b.year).localeCompare(String(a.year)));
    node.innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th>Year</th><th>Grant</th><th>Role</th><th>Agency</th></tr></thead><tbody>${items.map((g) =>
      `<tr><td>${esc(g.year)}</td><td><b>${esc(g.title)}</b>${g.note ? `<div class="note">${esc(g.note)}</div>` : ""}</td><td>${esc(g.role || "")}</td><td>${esc(g.agency || "")}</td></tr>`).join("")}</tbody></table></div>` : empty("No grants listed yet.");
  };

  R.teaching = async (node) => {
    const t = await loadJSON("data/teaching.json", { current: [], past: [] });
    node.innerHTML = `<div class="grid cols-2">${t.current.map((c) => `<div class="card"><div class="meta">${esc(c.level || "")} · ${esc(c.institute || "")} · ${esc(c.period || "")}</div>
        <h3>${esc(c.code ? c.code + " — " : "")}${esc(c.title)}</h3><p>${esc(c.desc || "")}</p>
        ${(c.materials || []).length ? `<div class="links" style="margin-top:0">${c.materials.map((m) => `<a class="btn small" href="${esc(safeUrl(m.url))}">${esc(m.label)}</a>`).join("")}</div>` : ""}</div>`).join("")}</div>
      ${(t.past || []).length ? `<h2 style="margin-top:36px">Earlier teaching</h2><div class="table-wrap"><table><thead><tr><th>Course / module</th><th>Institute</th><th>Period</th><th>Role</th></tr></thead><tbody>${t.past.map((c) =>
        `<tr><td>${esc(c.title)}</td><td>${esc(c.institute)}</td><td>${esc(c.period)}</td><td>${esc(c.role)}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
  };

  function memberCard(m) {
    const initials = m.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("");
    const links = Object.entries(m.links || {}).map(([k, u]) => `<a class="btn small" href="${esc(safeUrl(u))}" target="_blank" rel="noopener">${esc(k)}</a>`).join(" ");
    const work = (m.work || []).map((w) => `<li>${w.link ? `<a href="${esc(safeUrl(w.link))}">${esc(w.title)}</a>` : esc(w.title)}</li>`).join("");
    return `<div class="card member">${m.photo ? `<img src="${esc(safeUrl(m.photo))}" alt="${esc(m.name)}" loading="lazy">` : `<div class="avatar">${esc(initials)}</div>`}
      <div><h3 style="margin-bottom:2px">${esc(m.name)}</h3><div class="meta">${esc(m.role || "")}${m.period ? " · " + esc(m.period) : ""}</div>
      ${m.bio ? `<p style="margin-bottom:6px">${esc(m.bio)}</p>` : ""}
      ${work ? `<div class="note"><b>Work:</b><ul style="margin:4px 0 6px;padding-left:18px">${work}</ul></div>` : ""}
      <div class="links" style="margin-top:6px">${links}</div></div></div>`;
  }
  R.members = async (node) => {
    const m = await loadJSON("data/members.json", { current: [], alumni: [] });
    // group current members by role so PhD students, interns etc. get their own headings
    const groups = {};
    m.current.forEach((p) => (groups[p.role || "Members"] = groups[p.role || "Members"] || []).push(p));
    const order = Object.keys(groups).sort((a, b) => (/principal/i.test(b) ? 1 : 0) - (/principal/i.test(a) ? 1 : 0));
    node.innerHTML = order.map((r) => `<h3 style="margin-top:22px">${esc(r)}</h3><div class="grid cols-2">${groups[r].map(memberCard).join("")}</div>`).join("") +
      (m.alumni.length ? `<h2 style="margin-top:40px">Alumni</h2><div class="grid cols-2">${m.alumni.map(memberCard).join("")}</div>` : "") +
      (m.current.length <= 1 ? `<div class="empty" style="margin-top:24px">The lab is growing — see <a href="${ROOT}vacancies.html">Vacancies</a> to join.</div>` : "");
  };

  R.vacancies = async (node) => {
    const [v, s] = await Promise.all([loadJSON("data/vacancies.json", { openings: [] }), loadJSON("data/site.json", {})]);
    const mail = (subject) => (s.email ? `mailto:${esc(s.email)}?subject=${encodeURIComponent(subject)}` : esc(safeUrl((s.social || {}).linkedin || (s.social || {}).x || "")) || "#");
    node.innerHTML = `${v.intro ? `<p class="lede">${esc(v.intro)}</p>` : ""}` + v.openings.map((o) => `<section class="panel" id="${esc(o.id)}">
        <div class="toolbar" style="justify-content:space-between"><h2 style="margin:0">${esc(o.title)}</h2>
          <span class="chip ${o.status === "open" ? "ok" : ""}">${o.status === "open" ? "Open" : "Closed"}</span></div>
        <p class="note">${esc(o.type)}${o.when ? " · " + esc(o.when) : ""}${o.deadline ? " · Deadline: " + fmtDate(o.deadline) : ""}</p>
        <div class="grid cols-2"><div><h3>Topics</h3><ul>${(o.topics || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>
        <div><h3>Who should apply</h3><ul>${(o.requirements || []).map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div></div>
        ${o.status === "open" ? `<a class="btn primary" href="${mail("Application: " + o.title)}">Apply / enquire</a>` : ""}</section>`).join("");
  };

  function videoCard(v) {
    const id = ytId(v.url);
    const href = esc(safeUrl(v.url));
    const meta = [v.type, v.course, v.date ? fmtDate(v.date) : "", v.venue].filter(Boolean).map(esc).join(" · ");
    if (!id) return `<div class="video"><div class="info"><h3>${esc(v.title)}</h3><div class="meta">${meta}</div>${v.description ? `<p class="note">${esc(v.description)}</p>` : ""}<a class="btn small" href="${href}" target="_blank" rel="noopener">Watch ↗</a></div></div>`;
    return `<div class="video" data-yt="${id}"><div class="frame"><img src="https://i.ytimg.com/vi/${id}/hqdefault.jpg" alt="" loading="lazy">
        <button class="play" aria-label="Play: ${esc(v.title)}"><span>▶</span></button></div>
        <div class="info"><h3>${esc(v.title)}</h3><div class="meta">${meta}</div>${v.description ? `<p class="note" style="margin:6px 0 0">${esc(v.description)}</p>` : ""}</div></div>`;
  }
  R.videos = async (node) => {
    const [manual, yt] = await Promise.all([loadJSON("data/videos.json", []), loadJSON("data/youtube.json", { videos: [] })]);
    const have = new Set(manual.map((v) => ytId(v.url)).filter(Boolean));
    const auto = (yt.videos || []).filter((v) => !have.has(v.id)).map((v) => ({ title: v.title, url: "https://www.youtube.com/watch?v=" + v.id, date: (v.published || "").slice(0, 10), type: "YouTube" }));
    const groups = {};
    manual.forEach((v) => (groups[v.type || "Videos"] = groups[v.type || "Videos"] || []).push(v));
    let html = Object.keys(groups).map((g) => `<h2 style="margin-top:30px">${esc(g)}s</h2><div class="grid cols-3">${groups[g].sort((a, b) => String(b.date).localeCompare(String(a.date))).map(videoCard).join("")}</div>`).join("");
    if (auto.length) html += `<h2 style="margin-top:36px">Latest from the HCIA YouTube channel</h2><div class="grid cols-3">${auto.map(videoCard).join("")}</div>`;
    if (!html) html = empty("No videos yet. Add links in <code>data/videos.json</code>.");
    node.innerHTML = html;
    node.addEventListener("click", (e) => {
      const b = e.target.closest(".play"); if (!b) return;
      const box = b.closest(".video"); const frame = box.querySelector(".frame");
      frame.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${box.dataset.yt}?autoplay=1&rel=0" title="Video player" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>`;
    });
  };

  R.talks = async (node) => {
    const items = (await loadJSON("data/talks.json", [])).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
    node.innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Talk</th><th>Venue</th><th></th></tr></thead><tbody>${items.map((t) =>
      `<tr><td style="white-space:nowrap">${fmtDate(t.date)}</td><td><b>${esc(t.title)}</b></td><td>${esc(t.venue || "")}</td><td>${t.video ? `<a class="btn small" href="${esc(safeUrl(t.video))}" target="_blank" rel="noopener">Video</a> ` : ""}${t.slides ? `<a class="btn small" href="${esc(safeUrl(t.slides))}" target="_blank" rel="noopener">Slides</a>` : ""}</td></tr>`).join("")}</tbody></table></div>` : empty("No talks listed.");
  };

  R.contact = async (node) => {
    const s = await loadJSON("data/site.json", {});
    const social = s.social || {};
    const rows = [["scholar", "Google Scholar"], ["orcid", "ORCID"], ["linkedin", "LinkedIn"], ["x", "X"], ["youtube", "YouTube"], ["github", "GitHub"]].filter(([k]) => social[k]);
    node.innerHTML = `<p>${esc(s.institute)}<br>${esc(s.department)}${s.location ? "<br>" + esc(s.location) : ""}</p>
      <ul>${s.email ? `<li>Email: <a href="mailto:${esc(s.email)}">${esc(s.email)}</a></li>` : ""}${rows.map(([k, l]) => `<li>${l}: <a href="${esc(safeUrl(social[k]))}" target="_blank" rel="me noopener">${esc(social[k].replace(/^https?:\/\//, ""))}</a></li>`).join("")}</ul>`;
  };

  R.cv = async (node) => {
    const s = await loadJSON("data/site.json", {});
    if (!s.cv_file) return;
    try {
      const r = await fetch(ROOT + s.cv_file, { method: "HEAD" });
      if (r.ok) node.innerHTML = `<a class="btn primary" href="${esc(safeUrl(s.cv_file))}" download>⬇ Download full CV (PDF)</a>`;
      else node.innerHTML = "";
    } catch (_) { node.innerHTML = ""; }
  };

  // ---- boot ---------------------------------------------------------------
  async function boot() {
    await buildChrome();
    const nodes = [...document.querySelectorAll("[data-render]")];
    await Promise.all(nodes.map((n) => (R[n.dataset.render] ? R[n.dataset.render](n) : Promise.resolve(console.warn("Unknown data-render:", n.dataset.render)))));
    document.dispatchEvent(new CustomEvent("site:ready"));
  }
  // expose helpers for the demo pages
  window.Site = { ROOT, esc, safeUrl, loadJSON, fmtDate, ytId };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
