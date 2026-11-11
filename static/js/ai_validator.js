/* AI Question Validator: choose questions, run a review job, approve changes. */
(function () {
  "use strict";
  const root = document.getElementById("ai-validator");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const JOB_KEY = "avirtaReviewJob";

  const VERDICTS = {
    fix: { label: "Factual fix", cls: "bad", icon: "fa-triangle-exclamation", def: "update" },
    remove: { label: "Remove", cls: "bad", icon: "fa-ban", def: "keep" },
    attention: { label: "Needs attention", cls: "warn", icon: "fa-circle-exclamation", def: "keep" },
    improve: { label: "Improvement", cls: "info", icon: "fa-pen", def: "update" },
    ok: { label: "OK", cls: "ok", icon: "fa-circle-check", def: "keep" },
    not_reviewed: { label: "Not reviewed", cls: "warn", icon: "fa-circle-question", def: "keep" },
  };
  const ORDER = ["fix", "remove", "attention", "improve", "not_reviewed", "ok"];
  let results = null;
  let filter = "issues";
  const decisions = {}; // id -> keep | update | delete

  // ------------------------------------------------------------- setup
  const source = () => (root.querySelector('input[name="val-source"]:checked') || {}).value || "bank";
  root.querySelectorAll('input[name="val-source"]').forEach((r) => r.addEventListener("change", () => {
    $("src-bank-panel").classList.toggle("ai-hidden", source() !== "bank");
    $("src-file-panel").classList.toggle("ai-hidden", source() !== "upload");
    estimate();
  }));
  const catBoxes = () => Array.from($("cat-list").querySelectorAll("input[type=checkbox]"));
  function estimate() {
    if (source() !== "bank") { $("val-estimate").textContent = ""; return; }
    const sel = catBoxes().filter((b) => b.checked);
    const n = sel.reduce((a, b) => a + Number(b.dataset.count || 0), 0);
    $("val-estimate").textContent = sel.length ? n + " questions in " + sel.length + " categor" + (sel.length === 1 ? "y" : "ies") : "";
  }
  $("cat-list").addEventListener("change", estimate);
  $("cat-filter").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    $("cat-list").querySelectorAll("label").forEach((l) => l.classList.toggle("ai-hidden", q && !l.dataset.name.includes(q)));
  });
  $("cat-all").addEventListener("click", () => { catBoxes().forEach((b) => { if (!b.closest("label").classList.contains("ai-hidden")) b.checked = true; }); estimate(); });
  $("cat-none").addEventListener("click", () => { catBoxes().forEach((b) => (b.checked = false)); estimate(); });

  function options() {
    return {
      blind_check: $("opt-blind").checked, improve_wording: $("opt-wording").checked,
      add_explanations: $("opt-expl").checked, rescore_points: $("opt-points").checked,
      check_duplicates: $("opt-dups").checked,
    };
  }

  $("val-start").addEventListener("click", async () => {
    const err = $("val-error");
    err.textContent = "";
    let res;
    if (source() === "bank") {
      const cats = catBoxes().filter((b) => b.checked).map((b) => b.value);
      if (!cats.length) { err.textContent = "Choose at least one category."; return; }
      res = await fetch("/api/ai/validate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ categories: cats, options: options() }) });
    } else {
      const f = $("val-file").files[0];
      if (!f) { err.textContent = "Choose a JSON file."; return; }
      const fd = new FormData();
      fd.append("files", f);
      fd.append("options", JSON.stringify(options()));
      res = await fetch("/api/ai/validate", { method: "POST", body: fd });
    }
    const data = await res.json().catch(() => ({ ok: false, error: "Unexpected server response." }));
    if (!data.ok && !data.job_id) { err.textContent = data.error || "Could not start."; return; }
    sessionStorage.setItem(JOB_KEY, data.job_id);
    startProgress(data.job_id, data.ok ? "" : data.error);
  });

  // ------------------------------------------------------------- progress
  function msg(html, kind) {
    const el = $("val-progress-msg");
    el.className = "ai-status" + (kind ? " " + kind : "");
    el.innerHTML = html;
    el.classList.toggle("ai-hidden", !html);
  }
  // Timer ring around the percentage (decorative; the bar carries the same value).
  function setRing(percent, stopped) {
    const ring = $("val-ring");
    if (!ring) return;
    ring.style.setProperty("--p", Math.max(0, Math.min(100, percent)));
    ring.classList.toggle("is-stopped", !!stopped);
    $("val-ring-num").textContent = Math.round(percent) + "%";
  }
  function startProgress(jobId, note) {
    setRing(0, false);
    $("val-setup").classList.add("ai-hidden");
    $("val-results").classList.add("ai-hidden");
    $("val-progress").classList.remove("ai-hidden");
    msg(note ? esc(note) + " Showing its progress." : "", note ? "warn" : "");
    poll(jobId);
  }
  async function poll(jobId) {
    let data;
    try { data = await (await fetch("/api/ai/jobs/" + encodeURIComponent(jobId))).json(); } catch (e) { setTimeout(() => poll(jobId), 2500); return; }
    if (!data.ok) {
      // The job registry is in memory; finished results may still be on disk.
      if (await loadResults(jobId)) return;
      sessionStorage.removeItem(JOB_KEY);
      setRing(0, true);
      msg(esc(data.error), "bad"); backButton(); return;
    }
    const job = data.job;
    $("val-progress-bar").style.width = (job.percent || 0) + "%";
    setRing(job.percent || 0, job.status !== "running");
    $("val-progress-stage").textContent = job.stage || "";
    $("val-progress-model").textContent = (job.total ? job.total + " questions · " : "") + (job.model || "");
    if (job.warning) msg("<i class='fas fa-triangle-exclamation'></i> " + esc(job.warning), "warn");
    if (job.status === "running") { setTimeout(() => poll(jobId), 1500); return; }
    if (job.status === "done") { await loadResults(jobId); return; }
    sessionStorage.removeItem(JOB_KEY);
    $("val-progress-title").textContent = "Stopped";
    msg(esc(job.error || "The review failed."), "bad");
    backButton();
  }
  function backButton() {
    const el = $("val-progress-msg");
    if (el.querySelector("button")) return;
    el.insertAdjacentHTML("beforeend", '<br><button type="button" class="ai-btn secondary small"><i class="fas fa-arrow-left"></i> Back</button>');
    el.querySelector("button").addEventListener("click", reset);
  }
  function reset() {
    sessionStorage.removeItem(JOB_KEY);
    results = null;
    $("val-progress").classList.add("ai-hidden");
    $("val-results").classList.add("ai-hidden");
    $("val-setup").classList.remove("ai-hidden");
  }
  $("val-new").addEventListener("click", reset);

  // ------------------------------------------------------------- results
  async function loadResults(jobId) {
    const data = await (await fetch("/api/ai/validate/" + encodeURIComponent(jobId) + "/results")).json().catch(() => ({}));
    if (!data.ok) return false;
    results = data;
    Object.keys(decisions).forEach((k) => delete decisions[k]);
    results.results.forEach((r) => {
      decisions[r.id] = r.applied ? "done" : (r.proposed ? (VERDICTS[r.verdict] || VERDICTS.not_reviewed).def : "keep");
      if (!r.proposed && decisions[r.id] === "update") decisions[r.id] = "keep";
    });
    $("val-progress").classList.add("ai-hidden");
    $("val-setup").classList.add("ai-hidden");
    $("val-results").classList.remove("ai-hidden");
    const upload = results.source === "upload";
    $("val-apply").classList.toggle("ai-hidden", upload);
    $("val-download").classList.toggle("ai-hidden", !upload);
    const hasIssues = results.results.some((r) => r.verdict !== "ok" || r.duplicate_of);
    filter = hasIssues ? "issues" : "all";
    renderFilters();
    renderList();
    return true;
  }

  function counts() {
    const c = { all: results.results.length, issues: 0, duplicates: 0 };
    results.results.forEach((r) => {
      c[r.verdict] = (c[r.verdict] || 0) + 1;
      if (r.verdict !== "ok" || r.duplicate_of) c.issues++;
      if (r.duplicate_of) c.duplicates++;
    });
    return c;
  }
  function renderFilters() {
    const c = counts();
    const items = [["issues", "Needs a decision"], ...ORDER.map((v) => [v, VERDICTS[v].label]), ["duplicates", "Duplicates"], ["all", "All"]];
    $("val-filters").innerHTML = items.filter(([k]) => c[k] || k === "all" || k === "issues").map(([k, label]) =>
      '<button type="button" class="ai-chip' + (filter === k ? " is-on" : "") + '" data-filter="' + k + '" aria-pressed="' + (filter === k) + '">' +
      esc(label) + " <span class='ai-badge " + ((VERDICTS[k] || {}).cls || "info") + "'>" + (c[k] || 0) + "</span></button>").join("");
  }
  $("val-filters").addEventListener("click", (e) => {
    const b = e.target.closest("[data-filter]");
    if (!b) return;
    filter = b.dataset.filter;
    renderFilters(); renderList();
  });

  function field(label, before, after, key) {
    const changed = after !== undefined && JSON.stringify(before[key]) !== JSON.stringify(after[key]);
    const val = (o) => Array.isArray(o[key]) ? o[key].map((x) => esc(x)).join(" · ") : esc(o[key]);
    return {
      left: before[key] === undefined || before[key] === "" ? "" : "<div class='ai-kv'><b>" + label + "</b><span dir='auto'>" + val(before) + "</span></div>",
      right: after === undefined || after[key] === undefined || after[key] === "" ? "" :
        "<div class='ai-kv'><b>" + label + "</b><span dir='auto' class='" + (changed ? "changed" : "") + "'>" + val(after) + "</span></div>",
    };
  }

  function card(r, idx) {
    const v = VERDICTS[r.verdict] || VERDICTS.not_reviewed;
    const o = r.original, p = r.proposed || undefined;
    const keys = [["Question", "question"], ["Options", "options"], ["Answer", "correct_answer"], ["Explanation", "explanation"], ["Points", "points"]];
    const parts = keys.map(([l, k]) => field(l, o, p, k));
    const left = parts.map((x) => x.left).join("");
    const right = p ? parts.map((x) => x.right).join("") : "";
    const d = decisions[r.id];
    const choice = (val, label, icon) => {
      const id = "d-" + idx + "-" + val;
      return '<input type="radio" id="' + id + '" name="d-' + esc(r.id) + '" value="' + val + '"' + (d === val ? " checked" : "") + ">" +
        '<label for="' + id + '"><i class="fas ' + icon + '" aria-hidden="true"></i> ' + label + "</label>";
    };
    let actions;
    if (d === "done") actions = '<span class="ai-stamp ok" style="margin-inline-start:auto"><i class="fas fa-check"></i> ' + esc(r.applied || "applied") + "</span>";
    else actions = '<div class="ai-decide" role="radiogroup" aria-label="Decision for ' + esc(r.id) + '">' +
      choice("keep", "Keep", "fa-hand") + (p ? choice("update", "Apply", "fa-check") : "") + choice("delete", "Delete", "fa-trash") + "</div>";
    const contestant = r.contestant ? "<div class='ai-hint' dir='auto'><i class='fas fa-user-graduate'></i> Blind answer: <b>" + esc(r.contestant.answer || "-") + "</b> (" + esc(r.contestant.confidence || "") + ")" +
      (r.contestant.ambiguous ? " · flagged as ambiguous" + (r.contestant.note ? ": " + esc(r.contestant.note) : "") : "") + "</div>" : "";
    const dup = r.duplicate_of ? "<div class='ai-status warn'><i class='fas fa-clone'></i> Possible duplicate (" + esc(r.duplicate_of.reason) + ") of <b>" +
      esc(r.duplicate_of.id || "") + "</b> in " + esc(r.duplicate_of.category_id || "") + ": <span dir='auto'>" + esc(r.duplicate_of.question) + "</span></div>" : "";
    return '<article class="ai-q" data-id="' + esc(r.id) + '">' +
      '<div class="ai-q-head"><span class="ai-stamp ' + v.cls + '"><i class="fas ' + v.icon + '"></i> ' + v.label + "</span>" +
      "<span class='ai-muted' dir='auto'>" + esc(r.category_id) + " · " + esc(r.id) + "</span>" + actions + "</div>" +
      (r.issues && r.issues.length ? "<ul dir='auto'>" + r.issues.map((i) => "<li>" + esc(i) + "</li>").join("") + "</ul>" : "") +
      dup +
      (p ? "<div class='ai-diff'><div><h4>Current</h4>" + left + "</div><span class='ai-diff-arrow' aria-hidden='true'><i class='fas fa-arrow-right'></i></span><div class='is-proposed'><h4>Proposed</h4>" + right + "</div></div>"
         : "<div class='ai-diff single'><div>" + left + "</div></div>") +
      contestant + "</article>";
  }

  function matches(r) {
    if (filter === "all") return true;
    if (filter === "issues") return r.verdict !== "ok" || !!r.duplicate_of;
    if (filter === "duplicates") return !!r.duplicate_of;
    return r.verdict === filter;
  }

  function renderList() {
    const list = results.results.filter(matches).sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));
    $("val-list").innerHTML = list.length ? list.slice(0, 400).map(card).join("") :
      "<div class='ai-status ok'>Nothing to show here" + (filter === "issues" ? " - every reviewed question passed." : ".") + "</div>";
    updateSelection();
  }

  $("val-list").addEventListener("change", (e) => {
    if (e.target.type !== "radio") return;
    decisions[e.target.name.slice(2)] = e.target.value;
    updateSelection();
  });

  function selected() {
    return Object.entries(decisions).filter(([, a]) => a === "update" || a === "delete").map(([id, a]) => ({ id, action: a }));
  }
  function updateSelection() {
    const s = selected();
    const up = s.filter((d) => d.action === "update").length, del = s.length - up;
    $("val-selection").textContent = up + " change" + (up === 1 ? "" : "s") + " and " + del + " deletion" + (del === 1 ? "" : "s") + " selected";
    $("val-apply").disabled = !s.length;
  }

  $("val-apply").addEventListener("click", async () => {
    const s = selected();
    const del = s.filter((d) => d.action === "delete").length;
    if (!s.length) return;
    if (del && !confirm("Delete " + del + " question" + (del === 1 ? "" : "s") + " from the bank? This cannot be undone from this page.")) return;
    $("val-apply").disabled = true;
    const data = await (await fetch("/api/ai/validate/" + encodeURIComponent(results.job_id) + "/apply", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decisions: s }),
    })).json().catch(() => ({ ok: false, error: "Unexpected server response." }));
    if (!data.ok) { alert(data.error || "Could not apply the changes."); $("val-apply").disabled = false; return; }
    alert("Updated " + data.updated + ", deleted " + data.deleted + (data.skipped ? ", skipped " + data.skipped : "") + ". " + (data.github || ""));
    await loadResults(results.job_id);
  });

  $("val-download").addEventListener("click", async () => {
    const res = await fetch("/api/ai/validate/" + encodeURIComponent(results.job_id) + "/download", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decisions: selected() }),
    });
    if (!res.ok) { alert("Could not build the file."); return; }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "reviewed_questions.json";
    a.click();
    URL.revokeObjectURL(a.href);
  });

  // Resume a running or finished review after a reload.
  const pending = sessionStorage.getItem(JOB_KEY);
  if (pending) startProgress(pending);
  estimate();
})();
