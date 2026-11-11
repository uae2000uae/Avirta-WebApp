/* Admin > API Settings: choose and configure one AI option. */
(function () {
  "use strict";
  const root = document.getElementById("ai-settings");
  if (!root) return;

  const ICONS = { openai: "fa-robot", anthropic: "fa-feather-pointed", custom: "fa-key" };
  const $ = (id) => document.getElementById(id);
  let state = null;     // server state
  let selected = null;  // option being edited

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function api(url, payload) {
    const opts = payload === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    };
    const res = await fetch(url, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { data = { ok: false, error: "Unexpected server response (" + res.status + ")" }; }
    if (res.status === 401) data.error = "Your admin session has expired. Reload the page and log in again.";
    return data;
  }

  function status(msg, kind) {
    const el = $("ai-detail-status");
    el.className = "ai-status" + (kind ? " " + kind : "");
    el.innerHTML = msg;
    el.classList.toggle("ai-hidden", !msg);
  }

  function keyBadge(k) {
    if (k && k.managed) {
      return k.configured
        ? '<span class="ai-badge ok"><i class="fas fa-lock"></i> Managed key</span>'
        : '<span class="ai-badge warn"><i class="fas fa-triangle-exclamation"></i> Key missing in Secret Manager</span>';
    }
    if (!k || !k.configured) return '<span class="ai-badge warn"><i class="fas fa-triangle-exclamation"></i> No key</span>';
    if (k.local) return '<span class="ai-badge ok"><i class="fas fa-house"></i> Local, no key needed</span>';
    return '<span class="ai-badge ok"><i class="fas fa-check"></i> Key set ' + esc(k.hint || "") + "</span>";
  }

  function optionCfg(oid) { return state.config.options[oid]; }

  // ------------------------------------------------------------------ render
  function renderSummary() {
    const s = state.active_summary;
    const q = state.catalog.quality_profiles[s.quality];
    const k = state.keys[s.option] || {};
    const pill = $("ai-active-summary");
    pill.className = "ai-onair " + (k.configured ? "is-live" : "is-idle");
    pill.innerHTML =
      '<span class="ai-onair-label"><span class="ai-dot" aria-hidden="true"></span>' + (k.configured ? "On air" : (k.managed ? "Key missing" : "No key")) + "</span>" +
      "<span><strong>" + esc(s.label) + "</strong> <span class='ai-sep'>·</span> " + esc(s.model || "no model") +
      " <span class='ai-sep'>·</span> " + esc(q ? q.label : s.quality) + "</span>";
  }

  // Quality dials: [accuracy, speed] on a 3-segment meter.
  const DIALS = { accurate: [3, 1], balanced: [2, 2], fast: [1, 3] };
  function meter(name, n, cls) {
    return '<span class="ai-meter ' + cls + '"><span>' + name + '</span><span class="ai-meter-bar" data-n="' + n + '" aria-hidden="true"><i></i><i></i><i></i></span></span>';
  }

  function renderCards() {
    const wrap = $("ai-option-cards");
    wrap.innerHTML = "";
    ["openai", "anthropic", "custom"].forEach((oid) => {
      const meta = state.catalog.options[oid];
      const cfg = optionCfg(oid);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ai-option" + (oid === selected ? " is-selected" : "") + (state.config.active === oid ? " is-live" : "");
      btn.setAttribute("role", "radio");
      btn.setAttribute("aria-checked", oid === selected ? "true" : "false");
      const subtitle = oid === "custom"
        ? (cfg.base_url ? esc(cfg.base_url.replace(/^https?:\/\//, "")) : "Any OpenAI- or Anthropic-format service")
        : esc(cfg.model);
      btn.innerHTML =
        (state.config.active === oid ? '<span class="ai-active-flag"><span class="ai-dot" aria-hidden="true"></span> On air</span>' : "") +
        '<span class="ai-radio" aria-hidden="true"></span>' +
        '<span class="ai-podium-icon" aria-hidden="true"><i class="fas ' + ICONS[oid] + '"></i></span>' +
        '<span class="ai-option-title">' + esc(meta.label) + "</span>" +
        '<span class="ai-option-sub">' + subtitle + "</span>" + keyBadge(state.keys[oid]) +
        '<span class="ai-editing">Editing below</span>';
      btn.addEventListener("click", () => { selected = oid; renderAll(); });
      wrap.appendChild(btn);
    });
  }

  function renderDetail() {
    const oid = selected;
    const meta = state.catalog.options[oid];
    const cfg = optionCfg(oid);
    const k = state.keys[oid];
    $("ai-detail-title").textContent = "Configure " + meta.label;
    $("ai-detail-badge").innerHTML = state.config.active === oid
      ? '<span class="ai-badge solid"><i class="fas fa-tower-broadcast"></i> On air</span>'
      : '<span class="ai-badge info">Off air</span>';

    // Key: ChatGPT and Claude keys live in Google Cloud Secret Manager (read-only here);
    // only "Your own AI key" takes a key on this page.
    $("ai-key").value = "";
    const managed = !!k.managed;
    $("ai-key-field").classList.toggle("ai-hidden", managed);
    const box = $("ai-key-managed");
    box.classList.toggle("ai-hidden", !managed);
    if (managed) {
      const secret = esc(k.secret_name || meta.secret_name || "the API key");
      box.className = "ai-keyrow " + (k.configured ? "ok" : "warn");
      box.innerHTML = '<span class="ai-keyrow-icon" aria-hidden="true"><i class="fas ' + (k.configured ? "fa-lock" : "fa-triangle-exclamation") + '"></i></span>' +
        "<span><strong>Key: managed in Google Cloud</strong><span class='ai-keyrow-text'>" +
        (k.configured
          ? "Connected to Secret Manager · <code>" + secret + "</code>"
          : "<code>" + secret + "</code> was not found in Google Cloud Secret Manager. Add it in the Cloud Console (Security → Secret Manager).") +
        "</span></span>";
    } else {
      let hint = "Saved to Google Secret Manager as <code>" + esc(k.secret_name || meta.secret_name) + "</code>; it is never shown again.";
      if (!state.on_cloud_run) hint = "Running locally: keys go to an untracked local file (contents/admin_controls/.local_ai_keys.json), never to Secret Manager.";
      if (k.configured) hint = "Current key " + esc(k.hint) + " (from " + esc(k.source) + "). " + hint;
      $("ai-key-hint").innerHTML = hint;
    }

    // Custom endpoint fields
    const isCustom = oid === "custom";
    $("ai-custom-fields").classList.toggle("ai-hidden", !isCustom);
    if (isCustom) {
      $("ai-base-url").value = cfg.base_url || "";
      (cfg.api_format === "anthropic" ? $("ai-format-anthropic") : $("ai-format-openai")).checked = true;
    }

    // Model
    $("ai-model").value = cfg.model || "";
    const list = $("ai-model-list");
    list.innerHTML = "";
    (meta.models || []).forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id;
      o.label = m.label + " - " + m.note;
      list.appendChild(o);
    });
    updateModelNote();

    // Quality
    const qwrap = $("ai-quality");
    qwrap.innerHTML = "";
    ["accurate", "balanced", "fast"].forEach((qid) => {
      const q = state.catalog.quality_profiles[qid];
      const id = "ai-q-" + qid;
      const dial = DIALS[qid] || [2, 2];
      qwrap.insertAdjacentHTML("beforeend",
        '<input type="radio" name="ai-quality" id="' + id + '" value="' + qid + '"' + (cfg.quality === qid ? " checked" : "") + ">" +
        '<label for="' + id + '"><span class="ai-dial-head"><span class="ai-dial-title">' + esc(q.label) + "</span>" +
        (qid === "accurate" ? '<span class="ai-badge info">Recommended</span>' : "") + "</span>" +
        meter("Accuracy", dial[0], "accuracy") + meter("Speed", dial[1], "speed") +
        "<small>" + esc(q.description) + "</small></label>");
    });

    // Advanced
    const adv = cfg.advanced || {};
    $("ai-adv-temperature").value = adv.temperature == null ? "" : adv.temperature;
    const effort = $("ai-adv-effort");
    if (effort.options.length === 1) {
      state.catalog.reasoning_efforts.forEach((e) => effort.insertAdjacentHTML("beforeend", '<option value="' + e + '">' + e + "</option>"));
    }
    effort.value = adv.reasoning_effort || "";
    $("ai-adv-tokens").value = adv.max_output_tokens || state.catalog.advanced_defaults.max_output_tokens;
    $("ai-adv-timeout").value = adv.timeout || state.catalog.advanced_defaults.timeout;

    $("ai-use-sources").checked = !!state.config.use_sources;
    status("");
  }

  function updateModelNote() {
    const meta = state.catalog.options[selected];
    const val = $("ai-model").value.trim();
    const m = (meta.models || []).find((x) => x.id === val);
    $("ai-model-note").textContent = m ? m.note : (val ? "Custom model name - use Test connection to check it." : "Type a model name or load the list from the service.");
  }

  function renderPresets() {
    const body = $("ai-presets");
    const names = Object.keys(state.presets || {});
    if (!names.length) {
      body.innerHTML = '<tr><td class="ai-muted">No presets yet.</td></tr>';
      return;
    }
    body.innerHTML = names.map((name) => {
      const p = state.presets[name];
      const label = (state.catalog.options[p.option] || {}).label || p.option;
      const q = state.catalog.quality_profiles[p.quality];
      return "<tr><td><div class='ai-row-title' dir='auto'>" + esc(name) + "</div><div class='ai-row-meta'>" + esc(label) + " · " + esc(p.model) + " · " +
        esc(q ? q.label : p.quality) + "</div>" + (p.note ? "<div class='ai-hint' dir='auto'>" + esc(p.note) + "</div>" : "") +
        "</td><td><div class='ai-row-actions'>" +
        "<button type='button' class='ai-btn small secondary' data-apply='" + esc(name) + "'><i class='fas fa-check'></i> Apply</button>" +
        "<button type='button' class='ai-btn small icon danger' data-delete='" + esc(name) + "' aria-label='Delete preset " + esc(name) + "' title='Delete preset'>" +
        "<i class='fas fa-trash'></i></button></div></td></tr>";
    }).join("");
  }

  // Make sure every key status says whether it is managed (Secret Manager) or entered here.
  function normalizeKeys() {
    Object.keys(state.keys || {}).forEach((oid) => {
      const k = state.keys[oid];
      if (k && k.managed === undefined) k.managed = !!(state.catalog.options[oid] || {}).key_managed;
    });
  }

  function renderAll() {
    normalizeKeys();
    renderSummary();
    renderCards();
    renderDetail();
    renderPresets();
  }

  // ------------------------------------------------------------------ collect
  function collectOption() {
    const oid = selected;
    const out = JSON.parse(JSON.stringify(optionCfg(oid)));
    out.model = $("ai-model").value.trim();
    const q = root.querySelector('input[name="ai-quality"]:checked');
    if (q) out.quality = q.value;
    const t = $("ai-adv-temperature").value.trim();
    out.advanced = {
      temperature: t === "" ? null : Number(t),
      reasoning_effort: $("ai-adv-effort").value || null,
      max_output_tokens: Number($("ai-adv-tokens").value) || null,
      timeout: Number($("ai-adv-timeout").value) || null,
    };
    if (oid === "custom") {
      out.base_url = $("ai-base-url").value.trim();
      const f = root.querySelector('input[name="ai-format"]:checked');
      out.api_format = f ? f.value : "openai";
    }
    return out;
  }

  function collectConfig(activate) {
    const cfg = JSON.parse(JSON.stringify(state.config));
    cfg.options[selected] = collectOption();
    cfg.use_sources = $("ai-use-sources").checked;
    if (activate) cfg.active = selected;
    return cfg;
  }

  // ------------------------------------------------------------------ actions
  async function save(activate) {
    const opt = collectOption();
    if (!opt.model) { status("Enter a model name first.", "bad"); return; }
    if (selected === "custom" && !opt.base_url) { status("Enter the service's base URL first.", "bad"); return; }
    const data = await api("/admin/ai/config", { config: collectConfig(activate) });
    if (!data.ok) { status(esc(data.error || "Could not save."), "bad"); return; }
    state = data;
    renderAll();
    status(activate ? "Saved. " + esc(state.catalog.options[selected].label) + " is now used for generating and validating questions." : "Saved.", "ok");
    const k = state.keys[selected] || {};
    if (activate && !k.configured) {
      status(k.managed
        ? "Saved and selected, but " + esc(k.secret_name || "its key") + " was not found in Google Cloud Secret Manager. Add it in the Cloud Console (Security → Secret Manager)."
        : "Saved and selected, but this option has no API key yet - add one above.", "warn");
    }
  }

  async function saveKey() {
    const key = $("ai-key").value.trim();
    if (!key) { status("Paste the API key first.", "bad"); return; }
    $("ai-key-save").disabled = true;
    const data = await api("/admin/ai/key", { option: selected, key });
    $("ai-key-save").disabled = false;
    if (data.status) state.keys[selected] = data.status;
    $("ai-key").value = "";
    normalizeKeys();
    renderSummary(); renderCards(); renderDetail();
    status(esc(data.message || data.error || ""), data.ok ? "ok" : "bad");
  }

  function overrides() {
    const o = collectOption();
    return { model: o.model, quality: o.quality, base_url: o.base_url, api_format: o.api_format, advanced: o.advanced };
  }

  async function test() {
    const btn = $("ai-test");
    btn.disabled = true;
    status('<i class="fas fa-spinner fa-spin"></i> Testing ' + esc($("ai-model").value) + "…");
    const data = await api("/admin/ai/test", { option: selected, overrides: overrides() });
    btn.disabled = false;
    status(esc(data.ok ? data.message : data.error), data.ok ? (data.sample_correct ? "ok" : "warn") : "bad");
  }

  async function loadModels() {
    const btn = $("ai-load-models");
    btn.disabled = true;
    status('<i class="fas fa-spinner fa-spin"></i> Asking the service for its models…');
    const data = await api("/admin/ai/models", { option: selected, overrides: overrides() });
    btn.disabled = false;
    if (!data.ok) { status(esc(data.error), "bad"); return; }
    const list = $("ai-model-list");
    const known = new Set(Array.from(list.options).map((o) => o.value));
    data.models.forEach((id) => { if (!known.has(id)) { const o = document.createElement("option"); o.value = id; list.appendChild(o); } });
    status("Found " + data.models.length + " models. Click the Model box to pick one.", "ok");
  }

  async function presetAction(action, name, preset) {
    const data = await api("/admin/ai/presets", { action, name, preset });
    if (data.config) { state = data; if (action === "apply") selected = state.config.active; renderAll(); }
    status(esc(data.message || data.error || ""), data.ok ? "ok" : "bad");
  }

  // ------------------------------------------------------------------ wiring
  $("ai-save").addEventListener("click", () => save(false));
  $("ai-save-activate").addEventListener("click", () => save(true));
  $("ai-key-save").addEventListener("click", saveKey);
  $("ai-key").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); saveKey(); } });
  $("ai-test").addEventListener("click", test);
  $("ai-load-models").addEventListener("click", loadModels);
  $("ai-model").addEventListener("input", updateModelNote);
  $("ai-preset-save").addEventListener("click", () => {
    const name = $("ai-preset-name").value.trim();
    if (!name) { status("Enter a preset name.", "bad"); return; }
    presetAction("save", name, Object.assign({ option: selected }, collectOption()));
    $("ai-preset-name").value = "";
  });
  $("ai-presets").addEventListener("click", (e) => {
    const a = e.target.closest("[data-apply]"), d = e.target.closest("[data-delete]");
    if (a) presetAction("apply", a.dataset.apply);
    if (d && confirm("Delete preset '" + d.dataset.delete + "'?")) presetAction("delete", d.dataset.delete);
  });
  $("ai-endpoint-preset").addEventListener("change", (e) => {
    const p = state.catalog.custom_presets[Number(e.target.value)];
    if (!p) return;
    $("ai-base-url").value = p.base_url;
    (p.api_format === "anthropic" ? $("ai-format-anthropic") : $("ai-format-openai")).checked = true;
    status("Filled in " + esc(p.label) + ". Add the key and model name, then test the connection.");
  });

  (async function init() {
    const data = await api("/admin/ai/state");
    if (!data.ok) { root.insertAdjacentHTML("afterbegin", '<div class="ai-status bad">' + esc(data.error || "Could not load AI settings.") + "</div>"); return; }
    state = data;
    selected = state.config.active;
    const sel = $("ai-endpoint-preset");
    state.catalog.custom_presets.forEach((p, i) => sel.insertAdjacentHTML("beforeend", '<option value="' + i + '">' + esc(p.label) + "</option>"));
    renderAll();
  })();
})();
