/* ==========================================================================
   Sign-in and pay-per-minute access for the LLM empathy checker and EEG lab.
   Uses Firebase Authentication (Google sign-in). The backend (functions/billing.py)
   decides who may run; this file only shows the account bar and the payment box.

   Access.mount(el)                 draw the account bar into `el`
   Access.call(url, init, metered)  fetch with the user's sign-in token; metered
                                    calls open the payment box when minutes run out
   Access.account(body)             POST an action to the account service
   Access.onChange(fn)              fn(status, user) after every refresh
   ========================================================================== */
(function () {
  const SDK = "https://www.gstatic.com/firebasejs/10.12.2/";
  const cfg = () => window.SITE_CONFIG || {};
  let auth = null, user = null, status = null, bar = null, dlg = null, booted = null;
  const listeners = [];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const root = () => (window.Site && Site.ROOT) || "";
  const configured = () => !!(cfg().ACCOUNT_URL && cfg().FIREBASE && cfg().FIREBASE.apiKey);

  function dur(s) {
    s = Math.max(0, Math.round(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    if (h) return `${h} h ${m} min`;
    if (m) return sec ? `${m} min ${sec} s` : `${m} min`;
    return `${sec} s`;
  }
  const day = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
  const rupees = (n) => "₹" + (Number.isInteger(n) ? n : n.toFixed(2));

  function load(src) {
    return new Promise((ok, bad) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => bad(new Error("could not load " + src)); document.head.append(s); });
  }

  function boot() {
    if (booted) return booted;
    booted = (async () => {
      if (!configured()) return false;
      await load(SDK + "firebase-app-compat.js");
      await load(SDK + "firebase-auth-compat.js");
      if (!firebase.apps.length) firebase.initializeApp(cfg().FIREBASE);
      auth = firebase.auth();
      await new Promise((ok) => { let first = true; auth.onAuthStateChanged(async (u) => { user = u; await refresh(); if (first) { first = false; ok(); } }); });
      return true;
    })();
    return booted;
  }

  async function headers(extra) {
    const h = new Headers(extra || {});
    if (user) h.set("Authorization", "Bearer " + (await user.getIdToken()));
    return h;
  }

  async function refresh() {
    try { const r = await fetch(cfg().ACCOUNT_URL, { headers: await headers() }); status = await r.json(); }
    catch (_) { status = { error: "Could not reach the account service." }; }
    draw(); listeners.forEach((f) => f(status, user));
    return status;
  }

  async function signIn() {
    if (!(await boot())) { alert("Sign-in is not set up on this website yet."); return; }
    try { await auth.signInWithPopup(new firebase.auth.GoogleAuthProvider()); await refresh(); }
    catch (e) { if (e.code !== "auth/popup-closed-by-user" && e.code !== "auth/cancelled-popup-request") alert("Sign-in failed: " + e.message); }
  }

  // ------------------------------------------------------------------ account bar
  function draw() {
    if (!bar) return;
    if (!configured()) { bar.className = "callout warn"; bar.innerHTML = "🔒 <b>Sign-in not set up yet.</b> Fill in <code>ACCOUNT_URL</code> and <code>FIREBASE</code> in <code>assets/js/config.js</code> (GUIDE.md → Part 5B)."; return; }
    const s = status || {};
    bar.className = "callout access-bar";
    if (s.error && !("signed_in" in s)) { bar.className = "callout bad"; bar.textContent = s.error; return; }
    const price = rupees(s.price_per_minute ?? 1), free = s.free_minutes_per_user ?? 5, cap = s.daily_cap_minutes ?? 120;
    const poolNote = s.pool_exhausted ? `<div class="note">⚠️ This month's quota of free use on this website has been used up. Free minutes return on <b>${esc(day(s.free_resets_on))}</b>; paid minutes still work.</div>` : "";
    if (!user) {
      bar.innerHTML = `<div class="access-row"><div>🔒 <b>Sign in to use this tool.</b> Every user gets <b>${free} free minutes</b> a month; after that it costs <b>${price} per minute</b> (at most ${cap} minutes a day). Charges only recover the cloud computing cost.</div>
        <button class="btn primary small" data-act="signin">Sign in with Google</button></div>${poolNote}`;
      return;
    }
    const pend = (s.pending || []).length ? `<div class="note">⏳ ${s.pending.map((p) => `${p.minutes} min (${rupees(p.amount_inr)}, ref ${esc(p.upi_ref)})`).join(", ")} — waiting for the owner to confirm your payment.</div>` : "";
    const admin = s.is_admin ? ` <a class="btn small" href="${root()}admin.html">Approve payments</a>` : "";
    bar.innerHTML = `<div class="access-row"><div>Signed in as <b>${esc(user.email || user.displayName || "you")}</b></div>
        <div class="access-actions"><button class="btn small" data-act="buy">Buy minutes</button>${admin} <button class="btn small" data-act="signout">Sign out</button></div></div>
      <div class="access-stats"><span>Free left this month: <b>${dur(s.free_left_s)}</b></span><span>Paid balance: <b>${dur(s.paid_balance_s)}</b></span><span>Left today: <b>${dur(s.day_left_s)}</b></span></div>
      ${s.code && s.code !== "ok" ? `<div class="note">${esc(s.message)}</div>` : ""}${poolNote}${pend}`;
  }

  // ------------------------------------------------------------------ payment box
  function payDialog(reason) {
    const s = status || {}, p = cfg().PAYMENT || {}, price = s.price_per_minute ?? 1, max = s.max_purchase_minutes ?? 600;
    if (!dlg) {
      dlg = document.createElement("dialog"); dlg.className = "pay-dialog"; document.body.append(dlg);
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
    }
    const upi = (amt) => p.UPI_ID ? `upi://pay?pa=${encodeURIComponent(p.UPI_ID)}&pn=${encodeURIComponent(p.PAYEE_NAME || "")}&am=${amt}&cu=INR&tn=${encodeURIComponent("Website minutes")}` : "";
    dlg.innerHTML = `<form method="dialog" class="pay-form">
      <h3 style="margin-top:0">Continue with paid minutes</h3>
      ${reason ? `<p class="callout warn" style="margin-top:0">${esc(reason)}</p>` : ""}
      <p>Price: <b>${rupees(price)} per minute</b>, only to recover the cloud computing cost. You can use at most ${s.daily_cap_minutes ?? 120} minutes per day; unused paid minutes carry over.</p>
      <ol class="pay-steps">
        <li><label>How many minutes? <input type="number" id="payMin" min="1" max="${max}" value="30" style="width:90px"></label> → pay <b id="payAmt"></b></li>
        <li>Pay that amount to the QR code${p.UPI_ID ? ` or UPI ID <code>${esc(p.UPI_ID)}</code>` : ""}:
          <div class="pay-qr"><img src="${esc(root() + (p.QR_IMAGE || "assets/img/upi-qr.png"))}" alt="UPI QR code for payment" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'note',textContent:'(QR code image not added yet)'}))"></div>
          ${p.UPI_ID ? `<a class="btn small" id="payUpi" href="#">Pay with a UPI app (phone)</a>` : ""}</li>
        <li><label>UPI transaction ID / UTR (from your payment app) <input type="text" id="payRef" maxlength="40" autocomplete="off" placeholder="e.g. 431234567890"></label></li>
      </ol>
      <p class="note">The site owner checks the payment and adds your minutes, usually within a day. Your balance appears in the bar above the tool.</p>
      <p id="payMsg" class="note" aria-live="polite"></p>
      <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" value="close">Close</button><button class="btn primary" id="paySend" type="button">Send payment details</button></div>
    </form>`;
    const amt = () => Math.ceil(Math.max(1, Math.min(max, parseInt(dlg.querySelector("#payMin").value, 10) || 1)) * price);
    const upd = () => { dlg.querySelector("#payAmt").textContent = rupees(amt()); const a = dlg.querySelector("#payUpi"); if (a) a.href = upi(amt()); };
    dlg.querySelector("#payMin").addEventListener("input", upd); upd();
    dlg.querySelector("#paySend").addEventListener("click", async () => {
      const msg = dlg.querySelector("#payMsg"), btn = dlg.querySelector("#paySend");
      btn.disabled = true; msg.textContent = "Sending…";
      try {
        const r = await account({ action: "request", minutes: parseInt(dlg.querySelector("#payMin").value, 10), upi_ref: dlg.querySelector("#payRef").value.trim() });
        msg.innerHTML = `✅ Sent: ${r.minutes} minutes for ${rupees(r.amount_inr)}. You can close this box; the minutes appear once the payment is confirmed.`;
        refresh();
      } catch (e) { msg.textContent = "❌ " + e.message; btn.disabled = false; }
    });
    dlg.showModal();
  }

  // ------------------------------------------------------------------ calls
  async function call(url, init, metered) {
    if (!(await boot())) throw new Error("Sign-in is not set up on this website yet (GUIDE.md → Part 5B).");
    if (!user) { await signIn(); if (!user) throw new Error("Please sign in first."); }
    if (metered && status && status.can_run === false && status.code !== "daily_cap") { payDialog(status.message); throw new Error(status.message); }
    if (metered && status && status.code === "daily_cap") throw new Error(status.message);
    init = init || {};
    const r = await fetch(url, { ...init, headers: await headers(init.headers) });
    let j; try { j = await r.json(); } catch (_) { j = { error: `Unexpected response from the server (${r.status}).` }; }
    if (metered) refresh();
    if (!r.ok) {
      if (j.code === "need_payment" || j.code === "pool_exhausted") payDialog(j.error);
      const e = new Error(j.error || `Request failed (${r.status})`); e.code = j.code; throw e;
    }
    return j;
  }

  function account(body) {
    return call(cfg().ACCOUNT_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, false);
  }

  function mount(el) {
    bar = el; draw();
    if (!configured()) return;
    bar.innerHTML = '<span class="spinner"></span>Checking your account…';
    bar.addEventListener("click", async (e) => {
      const act = e.target.dataset && e.target.dataset.act; if (!act) return;
      if (act === "signin") signIn();
      if (act === "signout") { await auth.signOut(); await refresh(); }
      if (act === "buy") payDialog("");
    });
    boot().catch((e) => { bar.className = "callout bad"; bar.textContent = "Could not load sign-in: " + e.message; });
  }

  window.Access = { mount, call, account, refresh, signIn, onChange: (f) => listeners.push(f), get status() { return status; }, get user() { return user; }, configured };
})();
