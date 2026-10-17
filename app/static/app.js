"use strict";
const $ = (s) => document.querySelector(s);
const state = { source: "committed", stage: 1, status: null, cache: {} };

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
async function get(url) {
  if (state.cache[url]) return state.cache[url];
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return (state.cache[url] = await r.json());
}
function md(text) {
  const d = el("div", { class: "md" });
  d.innerHTML = DOMPurify.sanitize(marked.parse(text));
  return d;
}
const gbp = (n) => typeof n === "number" ? "£" + Math.round(n).toLocaleString("en-GB") : String(n);
function table(rows, cols) {
  cols = cols || (rows[0] ? Object.keys(rows[0]).slice(0, 9) : []);
  const fmt = (v) => v == null ? "" : typeof v === "object" ? JSON.stringify(v).slice(0, 80) : typeof v === "number" && Math.abs(v) >= 1000 ? v.toLocaleString("en-GB") : v;
  return el("table", {}, el("thead", {}, el("tr", {}, cols.map((c) => el("th", {}, c)))),
    el("tbody", {}, rows.map((r) => el("tr", {}, cols.map((c) => el("td", {}, fmt(r[c])))))));
}
const base = () => `/api/${state.source}`;
const codeBox = () => $("#code");
try { codeBox().value = sessionStorage.getItem("ac") || ""; } catch (e) {}
codeBox().addEventListener("input", () => { try { sessionStorage.setItem("ac", codeBox().value); } catch (e) {} });
async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Access-Code": codeBox().value }, body: body ? JSON.stringify(body) : undefined });
  let data = {}; try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}
const formSource = () => (state.status.sources.live.available ? "live" : "committed");

/* ---------- live job panel ---------- */
let es = null;
function showJob(job) {
  const box = $("#job"); box.hidden = false; box.replaceChildren();
  const title = el("h3", {}, `Live run · stage ${job.stage} · ${job.label}`);
  const status = el("div", { class: "q" }, "Starting… (the server has little CPU; the first message can take a minute)");
  const log = el("pre", {}, "");
  box.append(title, status, log);
  if (es) es.close();
  es = new EventSource("/api/jobs/current/stream");
  es.onmessage = (m) => {
    const e = JSON.parse(m.data);
    const tag = { text: "agent", tool: "tool ", status: "info ", error: "ERROR", stderr: "cli  ", notice: "NOTE " }[e.kind] || e.kind;
    if (e.kind === "notice" && !box.querySelector(".note")) box.insertBefore(el("div", { class: "note" }, e.text), log);
    log.append(document.createTextNode(`[${String(e.t).padStart(5)}s] ${tag} ${e.text}\n`));
    log.scrollTop = log.scrollHeight;
    if (e.kind !== "stderr") status.textContent = "Running… " + e.text.slice(0, 90);
  };
  es.addEventListener("end", async (m) => {
    es.close(); es = null;
    const j = JSON.parse(m.data);
    status.className = j.status === "done" ? "okc" : "err";
    status.textContent = j.status === "done" ? `Finished. Cost of this run: $${j.cost_usd.toFixed(3)}. Showing the revised result in the Live run view.` : j.error;
    await refreshStatus();
    if (j.status === "done") { state.source = "live"; state.stage = Math.max(3, Math.min(j.stage, 4)); state.cache = {}; renderNav(); renderPanel(); }
  });
  es.onerror = () => { if (es && es.readyState === 2) { status.className = "err"; status.textContent = "Lost the connection to the server."; } };
}
async function refreshStatus() { state.status = await (await fetch("/api/status")).json(); state.cache = {}; renderNav(); }

/* ---------- header + stage nav ---------- */
function renderNav() {
  const nav = $("#stages"); nav.replaceChildren();
  const stages = state.status.sources[state.source].stages;
  for (const s of stages) {
    nav.append(el("button", { class: "st" + (s.n === state.stage ? " sel" : ""), onclick: () => { state.stage = s.n; location.hash = s.n; renderNav(); renderPanel(); } },
      el("b", {}, `${s.n}. ${s.title}`), el("small", {}, s.agent), el("span", { class: "pill " + s.state }, s.state)));
  }
  $("#src-committed").className = state.source === "committed" ? "on" : "";
  $("#src-live").className = state.source === "live" ? "on" : "";
  $("#src-live").disabled = !state.status.sources.live.available;
  $("#banner").textContent = (state.source === "committed"
    ? "Viewing the committed run shipped with the project. Browsing makes no model call."
    : "Viewing the last live run since the server started (lost on restart).") +
    (state.status.isolation === "hook-only" ? " Note: on this server the agent's subprocess isolation (bubblewrap) is unavailable, so live runs rely on the guard hook alone to keep the API key out of reach." : "");
}

/* ---------- stage panels ---------- */
const WHY_DISABLED = {
  1: "Extracting rules reads the whole 15-page PDF and writes 73 rules with verbatim quotes, which is the most token-heavy stage.",
  2: "The analysis stage runs two agents and loads three spreadsheets (about 11,000 payments) with pandas on a server with 0.1 CPU.",
  5: "The agent team runs a planner, a challenger and a QA reviewer, each a separate agent run, plus rebuilds. Here it would run in sequence, not as a live team.",
};
function head(title, sub, n) {
  const on = n === 3 && state.status.live_runs_enabled && !state.status.busy;
  const label = n === 3 ? "Rerun stage" : (n === 4 || n === 6) ? "Use the form below" : "Live rerun disabled";
  const btn = el("button", { class: "btn", ...(on ? {} : { disabled: "" }), title: n === 3 ? "Rebuild the register from scratch with the risk-assessor (access code needed)" : "",
    onclick: async () => {
      if (!confirm(`Rebuild the risk register from scratch with the risk-assessor agent? Real model cost, capped at $${state.status.live_stage_caps_usd["3"]}. Later stages in the live copy will be cleared.`)) return;
      try { const job = await post("/api/jobs/3"); await refreshStatus(); showJob(job); } catch (e) { alert(e.message); }
    } }, label);
  const ledger = el("span", { class: "q" }, `Demo budget used: $${state.status.spent_usd.toFixed(2)} of $${state.status.ledger_cap_usd.toFixed(2)}`);
  const out = [el("h2", {}, title), el("div", { class: "q" }, sub), el("div", { class: "bar" }, btn, ledger)];
  if (WHY_DISABLED[n]) out.push(el("div", { class: "note" }, el("b", {}, "Live rerun is switched off for this stage. "), WHY_DISABLED[n],
    " It would cost far more than stages 3 and 4 (each about $0.10 to $0.17 in testing; this stage was not measured) and would probably run out of memory on the 512 MB free server, where one agent process alone used about 240 MB in testing. ",
    "The complete output of the original run is committed and shown below, and you can browse it freely. To see agents run live, use stage 3 (rerun) or stage 4 (change a decision)."));
  return out;
}
async function mdTabs(items) {
  const wrap = el("div"), body = el("div");
  const tabs = el("div", { class: "tabs" });
  async function show(i) {
    [...tabs.children].forEach((b, j) => b.className = i === j ? "on" : "");
    body.replaceChildren(el("p", {}, "Loading…"));
    try { body.replaceChildren(md((await get(`${base()}/doc/${items[i][0]}`)).markdown)); }
    catch (e) { body.replaceChildren(el("p", { class: "note" }, "Not available in this run.")); }
  }
  items.forEach(([, label], i) => tabs.append(el("button", { onclick: () => show(i) }, label)));
  wrap.append(tabs, body); await show(0); return wrap;
}

async function stage1() {
  const d = await get(`${base()}/digest/rules`);
  const root = el("div");
  root.append(...head("1 · Extract rules", `${d.source.file} · ${d.source.pages} pages · skill: extract-rules`, 1));
  root.append(el("div", { class: "chips" }, el("span", {}, `${d.rule_count} testable rules`), el("span", {}, `${d.excluded_count} excluded clauses`),
    el("span", {}, `${d.notes.length} notes`), Object.entries(d.by_type).map(([k, v]) => el("span", {}, `${k}: ${v}`))));
  root.append(el("h3", {}, "Parameters (named in the PDF, value left null, never filled in from memory)"),
    table(Object.entries(d.parameters).map(([k, v]) => ({ parameter: k, value: v.value, printed_as: v.printed_as, defined_in: v.defined_in, page: v.page }))));
  root.append(el("h3", {}, "Drafting gaps and contradictions found in the PDF"));
  d.notes.forEach((n) => root.append(el("div", { class: "note" }, el("b", {}, `${n.kind} · clauses ${(n.clauses || []).join(", ")} · p${n.page}: `), n.note)));
  root.append(el("h3", {}, "Rules"));
  const q = el("input", { type: "search", placeholder: "Filter by id, clause, type or text" });
  const out = el("div");
  const draw = () => {
    const f = q.value.toLowerCase();
    const rows = d.rules.filter((r) => !f || JSON.stringify(r).toLowerCase().includes(f));
    out.replaceChildren(el("div", { class: "q" }, `${rows.length} shown`), el("table", {}, el("thead", {}, el("tr", {}, ["rule", "clause", "p", "type", "required action / verbatim quote"].map((c) => el("th", {}, c)))),
      el("tbody", {}, rows.map((r) => el("tr", {}, el("td", {}, r.rule_id), el("td", {}, r.clause), el("td", {}, r.page), el("td", {}, r.type),
        el("td", {}, r.required_action || "", el("div", { class: "q" }, "“" + (r.verbatim_quote || "") + "”")))))));
  };
  q.addEventListener("input", draw); draw(); root.append(q, out); return root;
}

async function stage2() {
  const [a, h] = await Promise.all([get(`${base()}/digest/analytics`), get(`${base()}/digest/history`)]);
  const root = el("div");
  root.append(...head("2 · Analysis", "spend-analyst (Python computes every number) + findings-analyst (committee papers)", 2));
  root.append(el("div", { class: "note" }, `Window ${a.window.first_payment.slice(0, 10)} to ${a.window.last_payment.slice(0, 10)} (${a.window.months} months). ${a.window.label}.`));
  a.limitations.forEach((l) => root.append(el("div", { class: "q" }, "Limitation: " + l)));
  root.append(el("h3", {}, "Spend tests (click a card for its top 20)"));
  const detail = el("div"), cards = el("div", { class: "cards" });
  Object.entries(a.tests).forEach(([k, t]) => {
    const c = t.counts || {};
    const first = Object.keys(c)[0];
    const money = t.totals_gbp ? Object.entries(t.totals_gbp).filter(([, v]) => typeof v === "number")[0] : null;
    const card = el("button", { class: "card", onclick: () => {
      cards.querySelectorAll(".card").forEach((x) => x.classList.remove("sel")); card.classList.add("sel");
      detail.replaceChildren(el("h3", {}, k), el("p", { class: "q" }, t.interpretation), t.top20.length ? table(t.top20) : el("p", {}, "No flagged items."));
    } }, el("small", {}, k), el("div", { class: "n" }, c[first] != null ? Number(c[first]).toLocaleString("en-GB") : "–"),
      el("small", {}, first ? first.replaceAll("_", " ") : ""), money ? el("div", {}, el("small", {}, `${money[0].replaceAll("_", " ")}: ${gbp(money[1])}`)) : null);
    cards.append(card);
  });
  root.append(cards, detail);
  root.append(el("h3", {}, "Audit history (Governance Committee papers)"),
    el("div", { class: "chips" }, Object.entries(h.counts).map(([k, v]) => el("span", {}, `${k.replaceAll("_", " ")}: ${v}`))));
  if (h.audits.length) root.append(table(h.audits.map((x) => Object.fromEntries(Object.entries(x).filter(([, v]) => typeof v !== "object").slice(0, 7)))));
  if (h.risk_themes.length) root.append(el("h3", {}, "Risk themes referenced"), table(h.risk_themes.map((x) => Object.fromEntries(Object.entries(x).filter(([, v]) => typeof v !== "object").slice(0, 5)))));
  if (h.gaps.length) root.append(el("h3", {}, "Gaps (not in the public papers)"), table(h.gaps.map((x) => typeof x === "object" ? Object.fromEntries(Object.entries(x).filter(([, v]) => typeof v !== "object").slice(0, 4)) : { gap: x })));
  return root;
}

async function stage3() {
  const root = el("div");
  root.append(...head("3 · Risk register", "risk-assessor · skill: risk-assessment · build_register.py computes every score", 3));
  root.append(await mdTabs([["register", "Risk register"]])); return root;
}
async function stage4() {
  const root = el("div");
  root.append(...head("4 · Auditor gate", "The auditor approves, rejects or overrides each risk; the risk-assessor then revises the register", 4));
  const fs = formSource(), g = await get(`/api/${fs}/gate`);
  root.append(el("div", { class: "note" }, `Decision form for register ${g.version} (${fs === "live" ? "your live run" : "the committed run"}). Change at least one decision and submit: the risk-assessor reruns live (needs the access code; one run at a time; cost capped at $${state.status.live_stage_caps_usd["4"]}). OVERRIDE needs likelihood=N and/or impact=N in the comment; REVISE needs a comment saying what to change.`));
  const rows = g.rows.map((r) => {
    const sel = el("select", {}, ["APPROVE", "REJECT", "REVISE", "OVERRIDE"].map((o) => el("option", { value: o, ...(o === r.decision ? { selected: "" } : {}) }, o)));
    const com = el("input", { type: "text", value: r.comment, maxlength: "600", placeholder: "comment" });
    return { r, sel, com };
  });
  const msg = el("div", { class: "msg" });
  const submit = el("button", { class: "btn primary", type: "button", onclick: async () => {
    msg.className = "msg"; msg.textContent = "Submitting…";
    try {
      const job = await post("/api/gate", { decisions: rows.map((x) => ({ risk: x.r.risk, decision: x.sel.value, comment: x.com.value.trim() })) });
      msg.className = "msg good"; msg.textContent = "Accepted. The risk-assessor is running; progress appears above.";
      await refreshStatus(); showJob(job); window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { msg.className = "msg bad"; msg.textContent = e.message; }
  } }, "Submit decisions and rerun the risk-assessor");
  if (!state.status.live_runs_enabled) submit.disabled = true;
  root.append(el("form", { class: "gate", onsubmit: (e) => e.preventDefault() },
    el("table", {}, el("thead", {}, el("tr", {}, ["Risk", "Title", "Rating", "Decision", "Comment"].map((c) => el("th", {}, c)))),
      el("tbody", {}, rows.map((x) => el("tr", {}, el("td", {}, x.r.risk), el("td", {}, x.r.title), el("td", {}, x.r.rating), el("td", {}, x.sel), el("td", {}, x.com))))),
    submit, msg));
  root.append(el("h3", {}, "auditor-comments.md as recorded (" + state.source + " run)"), await mdTabs([["auditor-comments", "Auditor decisions"]]));
  return root;
}
async function stage5() {
  const root = el("div");
  root.append(...head("5 · Agent team", "planner → challenger → qa-reviewer", 5));
  root.append(el("div", { class: "note" }, "Live runs of this stage use a sequential fallback with the same message protocol (PACK READY, CHALLENGE, QA PASS/FAIL, DONE). A local test of true agent teams through the SDK did not finish a trivial two-message task within a $0.20 cap. The committed run was produced by the original team in Claude Code."));
  root.append(await mdTabs([["planning-memo", "Planning memo"], ["risk-control-matrix", "Risk-control matrix"], ["audit-program", "Audit program"], ["challenges", "Challenges"], ["review", "QA review"]]));
  return root;
}
async function stage6() {
  const root = el("div");
  root.append(...head("6 · Sign-off", "The auditor signs off the pack; review.md holds the QA verdict and the sign-off block", 6));
  const fs = formSource(), info = await get(`/api/${fs}/signoff`);
  root.append(el("div", { class: "note" }, `QA verdict: ${info.verdict}. Pack version ${info.pack_version}. Currently recorded: ${info.signed || "not signed"}. ` +
    (info.stale ? "The register changed after this pack was built, so SIGNED OFF is blocked until stage 5 is rerun (RETURNED TO TEAM is still allowed). " : "") +
    "Submitting writes the sign-off block of review.md in the live copy (access code needed); the committed review.md is never changed."));
  const dec = el("select", {}, el("option", { value: "SIGNED OFF" }, "SIGNED OFF"), el("option", { value: "RETURNED TO TEAM" }, "RETURNED TO TEAM"));
  const name = el("input", { type: "text", maxlength: "80", placeholder: "Auditor name" });
  const com = el("textarea", { rows: "2", maxlength: "500", placeholder: "Comments (one line, no | character)" });
  const msg = el("div", { class: "msg" });
  const btn = el("button", { class: "btn primary", type: "button", onclick: async () => {
    msg.className = "msg"; msg.textContent = "Saving…";
    try {
      await post("/api/signoff", { decision: dec.value, name: name.value, comments: com.value.replace(/\n/g, " ") });
      await refreshStatus(); state.source = "live"; renderNav(); await renderPanel();
    } catch (e) { msg.className = "msg bad"; msg.textContent = e.message; }
  } }, "Record sign-off");
  if (!state.status.live_runs_enabled) btn.disabled = true;
  root.append(el("form", { class: "so", onsubmit: (e) => e.preventDefault() }, el("div", { class: "bar" }, dec, name), com, el("div", { class: "bar" }, btn), msg));
  root.append(await mdTabs([["review", "review.md (" + state.source + " run)"]])); return root;
}
const PANELS = [null, stage1, stage2, stage3, stage4, stage5, stage6];

async function renderPanel() {
  const p = $("#panel"); p.replaceChildren(el("p", {}, "Loading…"));
  try { p.replaceChildren(await PANELS[state.stage]()); }
  catch (e) { p.replaceChildren(el("div", { class: "note" }, "Could not load this stage: " + e.message)); }
}
async function init() {
  state.status = await (await fetch("/api/status")).json();
  $("#src-committed").addEventListener("click", () => { state.source = "committed"; state.cache = {}; renderNav(); renderPanel(); });
  $("#src-live").addEventListener("click", () => { state.source = "live"; state.cache = {}; renderNav(); renderPanel(); });
  const h = parseInt(location.hash.slice(1), 10); if (h >= 1 && h <= 6) state.stage = h;
  renderNav(); renderPanel();
  if (state.status.busy && state.status.job) showJob(state.status.job);
}
init();
