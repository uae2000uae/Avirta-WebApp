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

  /* ------------------------------------------------------------ players
   * "Add player" adds a row named "Player N" (N = its number; the host is
   * player 1) with the name selected, so typing replaces it. The list never
   * goes past data-max-players including the host. Removing a row renumbers
   * the rows after it; names still at their default follow the new number. */
  var DEFAULT_NAME = /^Player \d+$/;

  function initPlayers(box) {
    var list = box.querySelector('.player-rows');
    var add = box.querySelector('[data-add-player]');
    var tpl = box.querySelector('[data-player-template]');
    var countEl = box.querySelector('[data-player-count]');
    var max = parseInt(box.getAttribute('data-max-players'), 10) || 10;
    if (!list || !add || !tpl) return;

    function rows() { return list.querySelectorAll('.player-row'); }

    function sync() {
      rows().forEach(function (row, i) {
        var n = i + 2;
        var input = row.querySelector('input');
        if (DEFAULT_NAME.test(input.value.trim())) input.value = 'Player ' + n;
        input.setAttribute('aria-label', 'Player ' + n);
        row.querySelector('[data-remove-player]').setAttribute('aria-label', 'Remove player ' + n);
      });
      var total = rows().length + 1;                 // + the host
      if (countEl) countEl.textContent = total;
      var full = total >= max;
      add.disabled = full;
      add.title = full ? 'Player limit reached (' + max + ' including the host)' : '';
    }

    function addPlayer() {
      if (rows().length + 1 >= max) return;
      var row = tpl.content.firstElementChild.cloneNode(true);
      var input = row.querySelector('input');
      input.value = 'Player ' + (rows().length + 2);
      list.appendChild(row);
      sync();
      input.focus();
      input.select();                                // type to replace the default name
    }

    add.addEventListener('click', addPlayer);

    list.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-remove-player]');
      if (!btn) return;
      var row = btn.closest('.player-row');
      var next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      sync();
      (next ? next.querySelector('input') : add).focus();
    });

    list.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || !e.target.matches('input')) return;
      e.preventDefault();                            // Enter adds the next player, never submits
      if (!add.disabled) addPlayer(); else add.focus();
    });

    // Clicking into a default name selects it, ready to overwrite.
    list.addEventListener('focusin', function (e) {
      if (e.target.matches('input') && DEFAULT_NAME.test(e.target.value.trim())) e.target.select();
    });

    sync();
  }

  function initAllPlayers() {
    document.querySelectorAll('[data-player-list]').forEach(initPlayers);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAllPlayers);
  else initAllPlayers();

  window.AvirtaSetup = { refresh: refresh };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
