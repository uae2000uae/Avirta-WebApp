/* Question Bank dashboard: chart tooltips and the Categories / Category tags tabs.
 *
 * Tooltips: any [data-tip] mark row shows its text on hover and on keyboard
 * focus (same content both ways). Tooltips only enhance - every value is also
 * printed on the chart or in its "Show as table" view. Text is inserted with
 * textContent, never as HTML.
 *
 * Tabs: WAI-ARIA tabs (arrow keys, Home/End). The URL hash #category-tags
 * opens the second tab, so redirects after tag edits land on it. */
(function () {
  'use strict';

  /* ---------------------------------------------------------- tooltip */
  var tip = null;
  function ensureTip() {
    if (tip) return tip;
    tip = document.createElement('div');
    tip.className = 'chart-tip';
    tip.setAttribute('role', 'tooltip');
    tip.hidden = true;
    document.body.appendChild(tip);
    return tip;
  }
  function show(el, x, y) {
    var t = ensureTip();
    var text = el.getAttribute('data-tip') || '';
    var parts = text.split(': ');
    t.textContent = '';
    if (parts.length > 1) {                       // value leads, label follows
      var v = document.createElement('strong');
      v.textContent = parts.slice(1).join(': ');
      var l = document.createElement('span');
      l.textContent = parts[0];
      t.appendChild(v); t.appendChild(l);
    } else {
      t.textContent = text;
    }
    t.hidden = false;
    if (x == null) {                              // keyboard focus: anchor to the mark
      var r = el.getBoundingClientRect();
      x = r.left + Math.min(r.width / 2, 160); y = r.top;
    }
    var w = t.offsetWidth, h = t.offsetHeight;
    var left = Math.max(8, Math.min(window.innerWidth - w - 8, x - w / 2));
    var top = y - h - 12;
    if (top < 8) top = y + 20;
    t.style.left = left + 'px';
    t.style.top = top + 'px';
  }
  function hide() { if (tip) tip.hidden = true; }

  document.addEventListener('pointermove', function (e) {
    var el = e.target.closest && e.target.closest('[data-tip]');
    if (el) show(el, e.clientX, e.clientY); else hide();
  });
  document.addEventListener('focusin', function (e) {
    var el = e.target.closest && e.target.closest('[data-tip]');
    if (el) show(el); else hide();
  });
  document.addEventListener('focusout', hide);
  window.addEventListener('scroll', hide, { passive: true });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') hide(); });

  /* ------------------------------------------------------------- tabs */
  function initTabs(root) {
    var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', String(on));
        t.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(t.getAttribute('aria-controls'));
        if (panel) panel.classList.toggle('active', on);
      });
      if (focus) tab.focus();
      var id = tab.getAttribute('aria-controls');
      var hash = id === 'category-tags' ? '#category-tags' : '';
      if (location.hash !== hash) history.replaceState(null, '', location.pathname + location.search + hash);
    }
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { select(t, false); });
      t.addEventListener('keydown', function (e) {
        var j = null;
        if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = tabs.length - 1;
        if (j !== null) { e.preventDefault(); select(tabs[j], true); }
      });
    });
    var fromHash = tabs.filter(function (t) { return '#' + t.getAttribute('aria-controls') === location.hash; })[0];
    if (fromHash) {
      select(fromHash, false);
      root.scrollIntoView({ block: 'start' });
    }
  }

  function init() { document.querySelectorAll('.qb-tabs').forEach(initTabs); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
