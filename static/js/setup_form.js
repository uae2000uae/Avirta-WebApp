/* Create-room forms: a live "x / max selected" counter and tag chips that
 * filter the category grid. The page's own script still enforces the limit
 * (it calls AvirtaSetup.refresh after every change); this file only shows
 * the state.
 *
 * Tag filter: chips in the same group (Language, Topic) widen the filter
 * (any of them), different groups narrow it (all groups must match).
 * "All" clears the filter. Ticked categories always stay visible. */
(function () {
  'use strict';

  function refresh(form) {
    form = form || document.querySelector('form[data-max-categories]');
    if (!form) return;
    var max = parseInt(form.getAttribute('data-max-categories'), 10) || 7;
    var n = form.querySelectorAll('input[name="categories"]:checked').length;
    var out = form.querySelector('.category-count');
    if (!out) return;
    var num = out.querySelector('[data-count]');
    if (num) num.textContent = n;
    out.classList.toggle('is-full', n >= max);
    out.title = n >= max ? 'Limit reached: untick a category to choose another.' : '';
  }

  function activeByGroup(form) {
    var groups = {};
    form.querySelectorAll('.tag-chip[data-tag]:not([data-tag=""])[aria-pressed="true"]').forEach(function (chip) {
      var g = chip.getAttribute('data-group') || 'topic';
      (groups[g] = groups[g] || []).push(chip.getAttribute('data-tag'));
    });
    return groups;
  }

  function applyFilter(form) {
    var groups = activeByGroup(form);
    var names = Object.keys(groups);
    var shown = 0;
    form.querySelectorAll('.categories-grid .category-checkbox').forEach(function (tile) {
      var tags = (tile.getAttribute('data-tags') || '').split(/\s+/);
      var ticked = tile.querySelector('input:checked');
      var match = names.every(function (g) {
        return groups[g].some(function (t) { return tags.indexOf(t) !== -1; });
      });
      var visible = match || !!ticked;
      tile.classList.toggle('is-filtered-out', !visible);
      if (match) shown++;
    });
    var all = form.querySelector('.tag-chip[data-tag=""]');
    if (all) all.setAttribute('aria-pressed', String(names.length === 0));
    var empty = form.querySelector('.category-empty');
    if (empty) empty.hidden = shown > 0;
  }

  function init() {
    var form = document.querySelector('form[data-max-categories]');
    if (!form) return;
    form.addEventListener('change', function (e) {
      if (e.target && e.target.name === 'categories') { refresh(form); applyFilter(form); }
    });
    form.querySelectorAll('.tag-chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        if (!chip.getAttribute('data-tag')) {          // "All": clear every tag
          form.querySelectorAll('.tag-chip').forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
        } else {
          chip.setAttribute('aria-pressed', String(chip.getAttribute('aria-pressed') !== 'true'));
        }
        applyFilter(form);
      });
    });
    refresh(form);
    applyFilter(form);
  }

  window.AvirtaSetup = { refresh: refresh };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
