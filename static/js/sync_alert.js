/* GitHub sync failure pop-up.
 * Loaded only for admins and for a host who just ended a game. Polls
 * /api/sync/alerts and shows a pop-up the moment a sync fails.
 * Styles live in static/css/style.css (".sync-alert"). */
(function () {
  "use strict";
  if (window.__avirtaSyncAlert) return;
  window.__avirtaSyncAlert = true;

  const BUSY_MS = 4000, IDLE_MS = 20000;
  let shownId = null, timer = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function close(id) {
    const el = document.getElementById("sync-alert");
    if (el) el.remove();
    if (id) fetch("/api/sync/ack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }).catch(() => {});
  }

  function show(f, isAdmin) {
    close();
    const when = f.time ? new Date(f.time).toLocaleTimeString() : "";
    const what = (f.reasons || []).join(", ");
    const wrap = document.createElement("div");
    wrap.id = "sync-alert";
    wrap.className = "sync-alert-backdrop";
    wrap.innerHTML =
      '<div class="sync-alert" role="alertdialog" aria-modal="true" aria-labelledby="sync-alert-title">' +
      '<h3 id="sync-alert-title"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> GitHub sync failed</h3>' +
      '<p class="ar">فشلت مزامنة البيانات مع GitHub</p>' +
      '<div class="msg">' + esc(f.message) + "</div>" +
      '<div class="meta">' + esc(when) + (what ? " · " + esc(what) : "") +
      "<br>Nothing is lost: the data is still on the server and is sent with the next sync.</div>" +
      '<div class="row">' + (isAdmin ? '<button type="button" class="primary" data-act="retry">Retry now</button>' : "") +
      '<button type="button" data-act="ok">OK</button></div></div>';
    document.body.appendChild(wrap);
    wrap.addEventListener("click", async (e) => {
      const act = e.target.getAttribute("data-act");
      if (act === "ok") close(f.id);
      if (act === "retry") {
        e.target.disabled = true;
        e.target.textContent = "Retrying…";
        await fetch("/api/sync/retry", { method: "POST" }).catch(() => {});
        close(f.id);
        schedule(BUSY_MS);
      }
    });
    wrap.addEventListener("keydown", (e) => { if (e.key === "Escape") close(f.id); });
    const btn = wrap.querySelector("button");
    if (btn) btn.focus();
  }

  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(poll, ms);
  }

  async function poll() {
    let data;
    try {
      const res = await fetch("/api/sync/alerts", { headers: { Accept: "application/json" } });
      data = await res.json();
    } catch (e) {
      schedule(IDLE_MS);
      return;
    }
    if (!data.watch) return; // nothing to watch any more
    if (data.failure && data.failure.id !== shownId) {
      shownId = data.failure.id;
      show(data.failure, data.is_admin);
    }
    schedule(data.busy ? BUSY_MS : IDLE_MS);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => schedule(1500));
  else schedule(1500);
})();
