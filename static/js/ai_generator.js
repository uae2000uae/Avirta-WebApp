/* AI Question Generator: start a job, show live progress, then review/save. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------------------------------------------------------- form
  const form = $("gen-form");
  if (form) {
    const JOB_KEY = "avirtaGenJob";

    function checked(name) {
      return Array.from(form.querySelectorAll('input[name="' + name + '"]:checked')).map((i) => i.value);
    }

    function setStep(stage, done) {
      const order = ["bank", "write", "check", "done"];
      let cur = "write";
      if (/bank|repeat|Wikipedia|notes/i.test(stage)) cur = "bank";
      if (/check|review|blind/i.test(stage)) cur = "check";
      if (done) cur = "done";
      const idx = order.indexOf(cur);
      document.querySelectorAll("#gen-steps [data-step]").forEach((el) => {
        const i = order.indexOf(el.dataset.step);
        el.className = i < idx || done ? "done" : i === idx ? "current" : "";
        el.innerHTML = (i < idx || done ? '<i class="fas fa-check"></i> ' : i === idx ? '<i class="fas fa-spinner fa-spin"></i> ' : "") + el.textContent.replace(/^\s+/, "");
      });
    }

    // Timer ring around the percentage (decorative; the bar carries the same value).
    function setRing(percent, stopped) {
      const ring = $("gen-ring");
      if (!ring) return;
      ring.style.setProperty("--p", Math.max(0, Math.min(100, percent)));
      ring.classList.toggle("is-stopped", !!stopped);
      $("gen-ring-num").textContent = Math.round(percent) + "%";
    }

    function showProgress(on) {
      $("gen-progress").classList.toggle("ai-hidden", !on);
      form.classList.toggle("ai-hidden", on);
    }

    function message(html, kind) {
      const el = $("gen-progress-msg");
      el.className = "ai-status" + (kind ? " " + kind : "");
      el.innerHTML = html;
      el.classList.toggle("ai-hidden", !html);
    }

    async function poll(jobId) {
      let res;
      try { res = await fetch("/api/ai/jobs/" + encodeURIComponent(jobId)); } catch (e) { setTimeout(() => poll(jobId), 2500); return; }
      const data = await res.json().catch(() => ({}));
      if (!data.ok) {
        sessionStorage.removeItem(JOB_KEY);
        message(esc(data.error || "Lost track of the job."), "bad");
        if ($("gen-ring")) $("gen-ring").classList.add("is-stopped");
        $("gen-progress-title").textContent = "Stopped";
        addRetry();
        return;
      }
      const job = data.job;
      $("gen-progress-bar").style.width = (job.percent || 0) + "%";
      setRing(job.percent || 0, job.status !== "running");
      $("gen-progress-stage").textContent = job.stage || "";
      $("gen-progress-count").textContent = (job.generated || 0) + " / " + (job.target || "?") + " accepted · " + (job.model || "");
      setStep(job.stage || "", job.status === "done");
      if (job.warning && job.status === "running") message("<i class='fas fa-triangle-exclamation'></i> " + esc(job.warning) + " - retrying.", "warn");
      if (job.status === "running") { setTimeout(() => poll(jobId), 1500); return; }
      sessionStorage.removeItem(JOB_KEY);
      if (job.status === "done") {
        $("gen-progress-title").textContent = "Done";
        message("Opening the review…", "ok");
        window.location.href = "/ai_question_generator?batch_id=" + encodeURIComponent(job.batch_id);
      } else {
        $("gen-progress-title").textContent = "Stopped";
        message(esc(job.error || "Generation failed."), "bad");
        addRetry();
      }
    }

    function addRetry() {
      const el = $("gen-progress-msg");
      if (el.querySelector("button")) return;
      const b = document.createElement("button");
      b.type = "button"; b.className = "ai-btn secondary small"; b.style.marginTop = "8px";
      b.innerHTML = '<i class="fas fa-arrow-left"></i> Back to the form';
      b.addEventListener("click", () => { showProgress(false); message(""); });
      el.appendChild(document.createElement("br"));
      el.appendChild(b);
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const err = $("gen-form-error");
      err.textContent = "";
      const types = checked("types");
      const topic = $("gen-topic").value.trim();
      if (!topic) { err.textContent = "Enter a topic."; $("gen-topic").focus(); return; }
      if (!types.length) { err.textContent = "Choose at least one question type."; return; }
      const payload = {
        topic, focus: $("gen-focus").value.trim(), category: $("gen-category").value,
        count: Number(checked("count")[0] || 10), language: checked("language")[0] || "arabic",
        difficulty: checked("difficulty")[0] || "mixed", types,
        verify: $("gen-verify").checked, use_sources: $("gen-sources").checked, explanations: $("gen-explanations").checked,
      };
      $("gen-submit").disabled = true;
      const res = await fetch("/api/ai/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await res.json().catch(() => ({ ok: false, error: "Unexpected server response." }));
      $("gen-submit").disabled = false;
      if (!data.ok && !data.job_id) { err.textContent = data.error || "Could not start."; return; }
      sessionStorage.setItem(JOB_KEY, data.job_id);
      showProgress(true);
      message(data.ok ? "" : esc(data.error) + " Showing its progress.", data.ok ? "" : "warn");
      $("gen-progress-title").textContent = "Generating " + payload.count + " questions about “" + topic + "”";
      poll(data.job_id);
    });

    // Resume a job that was running when the page was reloaded.
    const pending = sessionStorage.getItem(JOB_KEY);
    if (pending) { showProgress(true); $("gen-progress-title").textContent = "Generating…"; poll(pending); }
  }

  // ---------------------------------------------------------------- review
  const save = $("save-form");
  if (save) {
    const boxes = () => Array.from(save.querySelectorAll(".include-box"));
    function refresh() {
      let n = 0;
      boxes().forEach((b) => { b.closest(".ai-q").classList.toggle("is-off", !b.checked); if (b.checked) n++; });
      $("selected-count").textContent = n + " of " + boxes().length + " selected";
    }
    save.addEventListener("change", (e) => { if (e.target.classList.contains("include-box")) refresh(); });
    $("select-all").addEventListener("click", () => { boxes().forEach((b) => (b.checked = true)); refresh(); });
    $("select-none").addEventListener("click", () => { boxes().forEach((b) => (b.checked = false)); refresh(); });

    // Keep the answer in sync when the correct option's text is edited.
    save.querySelectorAll("input[data-option-for]").forEach((inp) => {
      inp.dataset.prev = inp.value;
      inp.addEventListener("input", () => {
        const ans = $("answer_" + inp.dataset.optionFor);
        if (ans && ans.value === inp.dataset.prev) ans.value = inp.value;
        inp.dataset.prev = inp.value;
        markCorrect(inp.dataset.optionFor);
      });
    });
    function markCorrect(i) {
      const ans = $("answer_" + i);
      save.querySelectorAll('input[data-option-for="' + i + '"]').forEach((o) => o.classList.toggle("is-correct", ans && o.value.trim() === ans.value.trim()));
    }
    save.querySelectorAll('input[id^="answer_"]').forEach((a) => a.addEventListener("input", () => markCorrect(a.id.split("_")[1])));

    const cat = $("existing_category");
    const toggleNew = () => $("new-category-wrap").classList.toggle("ai-hidden", cat.value !== "__new__");
    cat.addEventListener("change", toggleNew);
    toggleNew();

    save.addEventListener("submit", (e) => {
      if (!boxes().some((b) => b.checked)) { e.preventDefault(); alert("Select at least one question."); return; }
      if (cat.value === "__new__" && !$("new_category").value.trim()) { e.preventDefault(); $("new_category").focus(); }
    });
    refresh();
  }
})();
