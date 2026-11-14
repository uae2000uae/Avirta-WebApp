/* Avirta UI layer: light/dark mode, sound toggle, gentle motion and the
 * phone-landscape fit. It only observes the existing game markup and adds
 * classes for a moment; it never changes layout, sizes or game logic. */
(function () {
  'use strict';
  var html = document.documentElement;
  var reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var sfx = function (name) { if (window.AvirtaSFX) window.AvirtaSFX.play(name); };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
    once: function (k) {                     // true the first time per tab session
      try { if (sessionStorage.getItem(k)) return false; sessionStorage.setItem(k, '1'); } catch (e) {}
      return true;
    }
  };

  /* ---------------------------------------------------------------- mode */
  function currentTheme() { return html.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }
  function paintThemeButtons() {
    var dark = currentTheme() === 'dark';
    document.querySelectorAll('[data-action="toggle-theme"]').forEach(function (b) {
      var label = dark ? 'Switch to light mode' : 'Switch to dark mode';
      b.title = label; b.setAttribute('aria-label', label);
      var i = b.querySelector('i'); if (i) i.className = 'fas ' + (dark ? 'fa-sun' : 'fa-moon');
    });
    document.querySelectorAll('.mode-card[data-mode]').forEach(function (c) {
      c.classList.toggle('is-current', c.getAttribute('data-mode') === currentTheme());
    });
  }
  function setTheme(t, remember) {
    html.setAttribute('data-theme', t);
    if (remember) store.set('avirta-theme', t);
    paintThemeButtons();
  }
  if (window.matchMedia) {
    var mq = matchMedia('(prefers-color-scheme: dark)');
    var follow = function (e) {
      var saved = store.get('avirta-theme');
      if (saved !== 'light' && saved !== 'dark') setTheme(e.matches ? 'dark' : 'light', false);
    };
    if (mq.addEventListener) mq.addEventListener('change', follow); else if (mq.addListener) mq.addListener(follow);
  }

  /* --------------------------------------------------------------- sound */
  function paintSoundButtons() {
    var on = !(window.AvirtaSFX && window.AvirtaSFX.isMuted());
    document.querySelectorAll('[data-action="toggle-sound"]').forEach(function (b) {
      var label = on ? 'Mute sounds' : 'Turn sounds on';
      b.title = label; b.setAttribute('aria-label', label); b.setAttribute('aria-pressed', String(on));
      var i = b.querySelector('i'); if (i) i.className = 'fas ' + (on ? 'fa-volume-high' : 'fa-volume-xmark');
    });
  }

  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-action]');
    var action = t && t.getAttribute('data-action');
    if (action === 'toggle-theme') { setTheme(currentTheme() === 'dark' ? 'light' : 'dark', true); sfx('tick'); return; }
    if (action === 'set-theme') { setTheme(t.getAttribute('data-mode'), true); sfx('tick'); return; }
    if (action === 'follow-device') {
      try { localStorage.removeItem('avirta-theme'); } catch (err) {}
      setTheme(matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light', false); sfx('tick'); return;
    }
    if (action === 'toggle-sound') {
      if (window.AvirtaSFX) { window.AvirtaSFX.setMuted(!window.AvirtaSFX.isMuted()); sfx('tick'); }
      paintSoundButtons(); return;
    }
    // A very soft tick for ordinary controls (answer buttons have their own chimes).
    var ctl = e.target.closest && e.target.closest('button, .button, .cell, .tab-button, .ai-seg > label, .ai-board > label, .ai-dials > label');
    if (ctl && !ctl.disabled && !ctl.matches('.answer-option, [data-sfx]')) sfx('tick');
  }, true);

  /* Who is the fastest: the host's "who answered first" choice reloads the
   * page at once, which would cut any sound off. Play the result sound first,
   * then submit a moment later. */
  var SUBMIT_SOUNDS = [
    { action: /\/fastest\/award_points/, sound: 'correct' },
    { action: /\/fastest\/next_question/, sound: 'noAnswer', submitter: '[data-sfx="noAnswer"]' }
  ];
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.dataset.sfxSent) return;
    var rule = SUBMIT_SOUNDS.find(function (r) {
      return r.action.test(form.action) && (!r.submitter || (e.submitter && e.submitter.matches(r.submitter)));
    });
    if (!rule || !window.AvirtaSFX || window.AvirtaSFX.isMuted()) return;
    e.preventDefault();
    form.dataset.sfxSent = '1';
    sfx(rule.sound);
    if (e.submitter && e.submitter.name) {       // keep the clicked button's value
      var hidden = document.createElement('input');
      hidden.type = 'hidden'; hidden.name = e.submitter.name; hidden.value = e.submitter.value;
      form.appendChild(hidden);
    }
    setTimeout(function () { HTMLFormElement.prototype.submit.call(form); }, 420);
  }, true);

  /* -------------------------------------------------------------- motion */
  function cascade(nodes, step) {
    if (reduceMotion || document.visibilityState !== 'visible') return;
    nodes = Array.prototype.slice.call(nodes);
    if (!nodes.length) return;
    var longest = 0;
    nodes.forEach(function (el, n) {
      var i = typeof step === 'function' ? step(el, n) : n;
      longest = Math.max(longest, i);
      el.style.setProperty('--i', i);
      el.classList.add('enter');
    });
    // Remove the class afterwards so nothing lingers on the element.
    setTimeout(function () {
      nodes.forEach(function (el) { el.classList.remove('enter'); el.style.removeProperty('--i'); });
    }, 360 + longest * 24 + 80);
  }

  function sweep(el) {
    if (!el || reduceMotion || document.visibilityState !== 'visible') return;
    el.classList.add('win-sweep');
    setTimeout(function () { el.classList.remove('win-sweep'); }, 1250);
  }

  /* Count a score cell up from 0. The real text stays in place (transparent)
   * so the table never re-measures; the moving number is an overlay. */
  function countUp(cell) {
    var target = parseInt((cell.textContent || '').trim(), 10);
    if (reduceMotion || isNaN(target) || target <= 0 || document.visibilityState !== 'visible') return;
    var overlay = document.createElement('span');
    overlay.className = 'count-up-value';
    overlay.setAttribute('aria-hidden', 'true');
    cell.classList.add('count-up');
    cell.appendChild(overlay);
    var t0 = performance.now(), dur = 700;
    function frame(now) {
      var p = Math.min(1, (now - t0) / dur), eased = 1 - Math.pow(1 - p, 3);
      overlay.textContent = Math.round(target * eased);
      if (p < 1 && cell.isConnected) requestAnimationFrame(frame);
      else done();
    }
    function done() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      cell.classList.remove('count-up');
    }
    requestAnimationFrame(frame);
    setTimeout(done, dur + 400);              // safety net for background tabs
  }

  /* Brief two-colour confetti on a non-interactive canvas overlay. */
  function confetti() {
    if (reduceMotion || document.visibilityState !== 'visible') return;
    var cs = getComputedStyle(html);
    var colours = [cs.getPropertyValue('--confetti-1').trim() || '#d9b26a', cs.getPropertyValue('--confetti-2').trim() || '#b8863b'];
    var canvas = document.createElement('canvas');
    canvas.className = 'confetti-layer';
    canvas.setAttribute('aria-hidden', 'true');
    var dpr = Math.min(window.devicePixelRatio || 1, 2), W = innerWidth, H = innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    document.body.appendChild(canvas);
    var g = canvas.getContext('2d'); g.scale(dpr, dpr);
    var bits = [];
    for (var k = 0; k < 90; k++) {
      var fromLeft = k % 2 === 0;
      bits.push({
        x: fromLeft ? W * 0.18 : W * 0.82, y: H * 0.42,
        vx: (fromLeft ? 1 : -1) * (2 + Math.random() * 5), vy: -6 - Math.random() * 7,
        w: 5 + Math.random() * 5, h: 3 + Math.random() * 4,
        r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.3,
        c: colours[k % 2]
      });
    }
    var t0 = performance.now(), dur = 1800;
    function frame(now) {
      var t = now - t0;
      g.clearRect(0, 0, W, H);
      g.globalAlpha = t > dur - 450 ? Math.max(0, (dur - t) / 450) : 1;
      bits.forEach(function (b) {
        b.vy += 0.28; b.vx *= 0.99; b.x += b.vx; b.y += b.vy; b.r += b.vr;
        g.save(); g.translate(b.x, b.y); g.rotate(b.r); g.fillStyle = b.c;
        g.fillRect(-b.w / 2, -b.h / 2, b.w, b.h * Math.abs(Math.cos(b.r * 2)) + 1);
        g.restore();
      });
      if (t < dur) requestAnimationFrame(frame); else canvas.remove();
    }
    requestAnimationFrame(frame);
    setTimeout(function () { if (canvas.isConnected) canvas.remove(); }, dur + 500);
  }

  /* ------------------------------------------------------------ timers */
  function watchTimer(el, isLastSecond) {
    var last = null;
    new MutationObserver(function () {
      var n = parseInt(el.textContent, 10);
      if (isNaN(n) || n === last) return;
      last = n;
      if (n === 0) sfx('timerEnd');
      else if (n <= 5) sfx('timerTick');   // high tone for the final seconds
      else sfx('timerLow');                // low tone every second before that
    }).observe(el, { childList: true, characterData: true, subtree: true });
  }

  /* Fastest: a bar under the countdown drains with it, and screen readers
   * hear the time only at 10 and 5 seconds (not every tick). */
  function watchTimerBar(el) {
    var bar = document.querySelector('.timer-bar');
    var fill = bar && bar.querySelector('.timer-bar-fill');
    var say = document.querySelector('[data-timer-announcer]');
    var max = parseInt(el.textContent, 10) || 15;
    function paint() {
      var n = parseInt(el.textContent, 10);
      if (isNaN(n)) return;
      if (n > max) max = n;                         // timer restarted higher
      if (fill) fill.style.transform = 'scaleX(' + Math.max(0, n / max) + ')';
      if (bar) bar.classList.toggle('is-low', n <= 5);
      if (say && (n === 10 || n === 5)) say.textContent = n + ' seconds left';
      if (say && n === 0) say.textContent = 'Time is up';
    }
    paint();
    new MutationObserver(paint).observe(el, { childList: true, characterData: true, subtree: true });
  }

  /* ------------------------------------------------ flash messages */
  /* Errors stay until dismissed; other messages leave after a few seconds.
   * Timed here (not with an animation delay) so prefers-reduced-motion
   * never makes them vanish instantly. Hover or focus pauses the timer. */
  function initFlashes() {
    document.querySelectorAll('.flash-message').forEach(function (msg) {
      var timer = null;
      function leave() {
        if (!msg.isConnected) return;
        msg.classList.add('is-leaving');
        setTimeout(function () { msg.remove(); }, reduceMotion ? 0 : 340);
      }
      function arm() { if (msg.dataset.kind !== 'error') timer = setTimeout(leave, 6000); }
      function disarm() { clearTimeout(timer); }
      var close = msg.querySelector('.flash-close');
      if (close) close.addEventListener('click', leave);
      msg.addEventListener('mouseenter', disarm);
      msg.addEventListener('mouseleave', arm);
      msg.addEventListener('focusin', disarm);
      msg.addEventListener('focusout', arm);
      arm();
    });
  }

  /* ------------------------------------------------ confirm dialog */
  /* Any <form data-confirm="..."> asks first, in a real modal dialog with
   * Cancel focused, so one stray tap can't wipe a game. */
  function confirmDialog(form, onYes) {
    var opener = document.activeElement;
    var wrap = document.createElement('div');
    wrap.className = 'modal confirm-dialog';
    wrap.style.display = 'block';
    var titleId = 'confirm-title-' + Date.now();
    wrap.innerHTML =
      '<div class="modal-content" role="alertdialog" aria-modal="true" aria-labelledby="' + titleId + '">' +
        '<h2 class="confirm-title" id="' + titleId + '"></h2>' +
        '<p class="confirm-en"></p><p class="confirm-ar" lang="ar" dir="rtl"></p>' +
        '<div class="form-actions">' +
          '<button type="button" class="button secondary" data-confirm-no>Cancel | <span lang="ar" dir="rtl">إلغاء</span></button>' +
          '<button type="button" class="button red-button" data-confirm-yes></button>' +
        '</div>' +
      '</div>';
    var okEn = form.getAttribute('data-confirm-ok') || 'Confirm';
    var okAr = form.getAttribute('data-confirm-ok-ar');
    wrap.querySelector('.confirm-title').textContent = okEn + '?';
    wrap.querySelector('.confirm-en').textContent = form.getAttribute('data-confirm');
    var ar = wrap.querySelector('.confirm-ar');
    if (form.getAttribute('data-confirm-ar')) ar.textContent = form.getAttribute('data-confirm-ar'); else ar.remove();
    var yes = wrap.querySelector('[data-confirm-yes]');
    yes.textContent = okEn;
    if (okAr) {
      var s = document.createElement('span'); s.lang = 'ar'; s.dir = 'rtl'; s.textContent = okAr;
      yes.appendChild(document.createTextNode(' | ')); yes.appendChild(s);
    }
    var no = wrap.querySelector('[data-confirm-no]');
    function close() {
      document.removeEventListener('keydown', onKey, true);
      wrap.remove();
      if (opener && opener.focus) opener.focus();
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      if (e.key === 'Tab') {                       // keep focus inside the dialog
        e.preventDefault();
        (document.activeElement === no ? yes : no).focus();
      }
    }
    no.addEventListener('click', close);
    yes.addEventListener('click', function () { yes.disabled = true; onYes(); });
    wrap.addEventListener('click', function (e) { if (e.target === wrap) close(); });
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(wrap);
    no.focus();
  }
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || !form.hasAttribute || !form.hasAttribute('data-confirm') || form.dataset.confirmed) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    confirmDialog(form, function () {
      form.dataset.confirmed = '1';
      HTMLFormElement.prototype.submit.call(form);   // csrf.js already added the token on load
    });
  }, true);

  /* Display settings menu: close on an outside click or Escape. */
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details.settings-menu[open]').forEach(function (d) {
      if (!d.contains(e.target)) d.open = false;
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    document.querySelectorAll('details.settings-menu[open]').forEach(function (d) {
      d.open = false; var s = d.querySelector('summary'); if (s) s.focus();
    });
  });

  /* ------------------------------------------------- invite links */
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-invite]');
    if (!btn) return;
    var url = btn.getAttribute('data-invite');
    var label = btn.innerHTML;
    function done(text) {
      btn.classList.add('is-copied');
      btn.textContent = text;
      setTimeout(function () { btn.classList.remove('is-copied'); btn.innerHTML = label; }, 2200);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(function () { done('Link copied'); }, function () { window.prompt('Copy this invite link:', url); });
    } else {
      window.prompt('Copy this invite link:', url);
    }
  });

  /* --------------------------------------------- phone landscape fit */
  var fitQuery = window.matchMedia && matchMedia('(orientation: landscape) and (max-height: 500px)');
  var MIN_FIT = 0.6;
  function fitStage() {
    var stage = document.querySelector('body.game > .container');
    if (!stage || !fitQuery) return;
    var on = fitQuery.matches && store.get('avirta-nofit') !== '1';
    html.classList.toggle('fit-stage', on);
    if (!on) {
      html.classList.remove('fit-scroll');
      stage.style.removeProperty('--fit'); stage.style.removeProperty('--fit-h'); return;
    }
    var zoom = parseFloat(getComputedStyle(html).zoom) || 1;
    var h = stage.offsetHeight;                     // layout height, unaffected by the transform
    var needed = Math.min(1, Math.floor(((window.innerHeight / zoom) / h) * 10000) / 10000);
    // Never shrink below MIN_FIT (text and tap targets get too small); the few
    // screens that would need more shrinking scroll a little instead.
    var s = Math.max(MIN_FIT, needed);
    html.classList.toggle('fit-scroll', needed < MIN_FIT);
    stage.style.setProperty('--fit', s.toFixed(4));
    stage.style.setProperty('--fit-h', h + 'px');
  }

  /* --------------------------------------------------------------- init */
  function init() {
    paintThemeButtons();
    paintSoundButtons();
    initFlashes();
    var path = location.pathname;

    // Pages that reload on every turn: fill their status line after load so
    // screen readers announce it (e.g. "It is Sara's turn.").
    document.querySelectorAll('[data-announce]').forEach(function (el) {
      setTimeout(function () { el.textContent = el.getAttribute('data-announce'); }, 400);
    });

    // Remember a player's name between visits (join form).
    document.querySelectorAll('input[data-remember]').forEach(function (input) {
      var key = input.getAttribute('data-remember');
      if (!input.value) { var v = store.get(key); if (v) input.value = v; }
      if (input.form) input.form.addEventListener('submit', function () { if (input.value.trim()) store.set(key, input.value.trim()); });
    });

    var fastestTimer = document.getElementById('timer');
    if (fastestTimer && document.querySelector('.timer-bar')) watchTimerBar(fastestTimer);

    // Phone landscape: keep the whole game on screen.
    if (document.body.classList.contains('game')) {
      fitStage();
      window.addEventListener('resize', fitStage);
      if (fitQuery && fitQuery.addEventListener) fitQuery.addEventListener('change', fitStage);
      var stage = document.querySelector('body.game > .container');
      if (stage && window.ResizeObserver) new ResizeObserver(fitStage).observe(stage);
      // Late layout changes (web fonts, live updates) also trigger a refit.
      window.addEventListener('load', fitStage);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitStage);
      setTimeout(fitStage, 600);
    }

    // Timers (Fastest: #timer, Columns question: #time-left).
    ['timer', 'time-left'].forEach(function (id) { var el = document.getElementById(id); if (el) watchTimer(el); });
    var lateTimer = new MutationObserver(function () {
      var el = document.getElementById('time-left');
      if (el && !el.dataset.watched) { el.dataset.watched = '1'; watchTimer(el); lateTimer.disconnect(); }
    });
    if (document.querySelector('.question-display') && !document.getElementById('time-left')) {
      lateTimer.observe(document.querySelector('.question-display'), { childList: true, subtree: true });
    }

    // Knowledge Columns board: cascade on the first view of a room.
    var board = document.querySelector('.game-board');
    if (board && store.once('avirta-entered:' + path)) {
      sfx('start');
      cascade(board.querySelectorAll('.category-header-grid, .question-item'), function (el) {
        var col = Array.prototype.indexOf.call(board.children, el.closest('.category'));
        var row = el.classList.contains('question-item') ? Array.prototype.indexOf.call(el.parentNode.children, el) + 1 : 0;
        return col + row;
      });
    }

    // The Hive: cells cascade on first view; answers chime.
    var hive = document.getElementById('board');
    if (hive && document.getElementById('hex_root')) {
      if (store.once('avirta-entered:' + path)) {
        sfx('start');
        cascade(hive.querySelectorAll('.cell'), function (el, n) { return Math.floor(n / 5) + (n % 5); });
      }
      var opts = document.getElementById('options_container');
      if (opts) {
        new MutationObserver(function (list) {
          list.forEach(function (m) {
            if (m.type === 'childList' && m.addedNodes.length && opts.querySelector('.answer-option')) {
              cascade(opts.querySelectorAll('.answer-option'));
            }
            if (m.type === 'attributes' && m.target.classList) {
              if (m.target.classList.contains('wrong') && !(m.oldValue || '').includes('wrong')) sfx('wrong');
              else if (m.target.classList.contains('correct') && !(m.oldValue || '').includes('correct') && !opts.querySelector('.wrong')) sfx('correct');
            }
          });
        }).observe(opts, { childList: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true, subtree: true });
      }
    }

    // Columns question page: question area settles in.
    var qd = document.querySelector('.question-display');
    if (qd && document.querySelector('.answer-form, #show-answer-btn')) {
      cascade(qd.querySelectorAll('.question-text, .option-button, #show-answer-btn'));
    }

    // Who is the fastest: start chime once per room, cascade a newly revealed question.
    if (/\/fastest\/play\//.test(path)) {
      if (store.once('avirta-entered:' + path)) sfx('start');
      var qt = document.querySelector('#question-container .question-text');
      if (qt) {
        var key = 'avirta-lastq:' + path, seen = null;
        try { seen = sessionStorage.getItem(key); sessionStorage.setItem(key, qt.textContent); } catch (e) {}
        if (seen !== qt.textContent) cascade(document.querySelectorAll('#question-container .question-text, #question-container .button-no-hover'));
      }
      var players = document.querySelectorAll('.player-button');
      if (players.length && store.once('avirta-answer:' + path + ':' + (qt ? qt.textContent : ''))) cascade(players);
    }

    // Result page: chime + settle + sweep on a correct answer.
    var result = document.querySelector('.result');
    if (result) {
      var good = result.classList.contains('correct');
      sfx(good ? 'correct' : 'wrong');
      cascade([result]);
      if (good) setTimeout(function () { sweep(result); }, 260);
      document.querySelectorAll('.leaderboard-table tbody tr td:last-child').forEach(countUp);
    }

    // Leaderboards: rows settle, winner row sweeps, scores count up.
    var lb = document.querySelector('.leaderboard-section .leaderboard-table, .leaderboard-display .leaderboard-table');
    if (lb && !result) {
      var rows = lb.querySelectorAll('tbody tr');
      cascade(rows);
      setTimeout(function () { sweep(rows[0]); }, 200);
      lb.querySelectorAll('tbody tr td:last-child').forEach(countUp);
      var winnerPoints = document.querySelector('.winner-banner .winner-points');
      if (winnerPoints) setTimeout(function () { countUp(winnerPoints); }, 300);
      var section = document.querySelector('[data-final="true"]');
      if (section && store.once('avirta-win:' + path)) {
        setTimeout(function () { sfx('win'); confetti(); }, 250);
      }
    }

    // Game over pop-up on the board.
    new MutationObserver(function (list) {
      list.forEach(function (m) {
        m.addedNodes.forEach(function (n) { if (n.id === 'game-over-modal') sfx('complete'); });
      });
    }).observe(document.body, { childList: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.AvirtaUI = { cascade: cascade, sweep: sweep, confetti: confetti, countUp: countUp, fit: fitStage, setTheme: setTheme };
})();
