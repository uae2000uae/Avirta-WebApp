/* Avirta sound effects: soft UI ticks and chimes, synthesised with the Web
 * Audio API (no audio files). On by default, quiet, and remembered when
 * muted (localStorage "avirta-sound" = "off").
 *
 *   AvirtaSFX.play('tick' | 'timerLow' | 'timerTick' | 'timerEnd' | 'start' |
 *                  'correct' | 'wrong' | 'noAnswer' | 'complete' | 'win')
 *   AvirtaSFX.setMuted(bool) / AvirtaSFX.isMuted()
 *
 * Browsers only allow audio after a user gesture, so the context is created
 * lazily and resumed on the first pointer/key press. Sounds requested while
 * audio is still locked are dropped (never queued), so nothing plays late.
 */
(function () {
  'use strict';
  if (window.AvirtaSFX) return;

  var KEY = 'avirta-sound';
  var MASTER = 0.22;                 // overall volume: deliberately low
  var ctx = null, master = null;
  var muted = false;
  try { muted = localStorage.getItem(KEY) === 'off'; } catch (e) {}

  function context() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try {
      ctx = new AC();
      master = ctx.createGain();
      master.gain.value = MASTER;
      master.connect(ctx.destination);
    } catch (e) { ctx = null; }
    return ctx;
  }

  function unlock() {
    var c = context();
    if (c && c.state === 'suspended') c.resume().catch(function () {});
  }
  ['pointerdown', 'keydown', 'touchstart'].forEach(function (type) {
    window.addEventListener(type, unlock, { capture: true, passive: true });
  });

  /* One soft note: sine/triangle body with a fast attack and an exponential
   * release. `at` is seconds from now. */
  function note(freq, at, dur, gain, type, partial) {
    var c = ctx, t = c.currentTime + (at || 0);
    var o = c.createOscillator(), g = c.createGain();
    o.type = type || 'sine';
    o.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(master);
    o.start(t); o.stop(t + dur + 0.02);
    if (partial) note(freq * 2.01, at, dur * 0.6, gain * 0.18, 'sine');   // bell shimmer
  }

  var C5 = 523.25, D5 = 587.33, E5 = 659.25, G5 = 783.99, A5 = 880, B5 = 987.77, C6 = 1046.5, E6 = 1318.5;

  var SOUNDS = {
    tick:      function () { note(1760, 0, 0.035, 0.18, 'sine'); },
    timerLow:  function () { note(440, 0, 0.07, 0.26, 'triangle'); },          // each second while time remains
    timerTick: function () { note(1320, 0, 0.06, 0.32, 'triangle'); },        // last 5 seconds
    noAnswer:  function () { note(392, 0, 0.16, 0.26, 'sine'); note(349.23, 0.13, 0.32, 0.24, 'sine'); },
    timerEnd:  function () { note(A5, 0, 0.22, 0.4, 'sine', true); note(E5, 0.16, 0.42, 0.4, 'sine', true); },
    start:     function () { note(C5, 0, 0.18, 0.32, 'sine', true); note(E5, 0.08, 0.18, 0.32, 'sine', true); note(G5, 0.16, 0.32, 0.34, 'sine', true); },
    correct:   function () { note(E5, 0, 0.16, 0.36, 'sine', true); note(B5, 0.09, 0.42, 0.36, 'sine', true); },
    wrong:     function () { note(311.13, 0, 0.2, 0.3, 'triangle'); note(261.63, 0.12, 0.34, 0.28, 'triangle'); },
    complete:  function () { note(G5, 0, 0.16, 0.3, 'sine', true); note(C6, 0.1, 0.4, 0.32, 'sine', true); },
    win:       function () {
      [C5, E5, G5, C6].forEach(function (f, i) { note(f, i * 0.09, 0.3, 0.32, 'sine', true); });
      note(E6, 0.4, 0.7, 0.2, 'sine', true); note(G5, 0.4, 0.8, 0.22, 'sine'); note(D5, 0.4, 0.8, 0.12, 'sine');
    }
  };

  function play(name) {
    if (muted || !SOUNDS[name]) return;
    var c = context();
    if (!c) return;
    if (c.state === 'suspended') {
      // Allowed when the page was reached by a click (sticky activation);
      // otherwise the browser keeps it locked and we stay silent.
      var asked = Date.now();
      c.resume().then(function () {
        if (c.state === 'running' && Date.now() - asked < 400) SOUNDS[name]();
      }).catch(function () {});
      return;
    }
    try { SOUNDS[name](); } catch (e) {}
  }

  function setMuted(m) {
    muted = !!m;
    try { localStorage.setItem(KEY, muted ? 'off' : 'on'); } catch (e) {}
    if (muted) document.documentElement.setAttribute('data-sound', 'off');
    else document.documentElement.removeAttribute('data-sound');
  }

  window.AvirtaSFX = {
    play: play,
    setMuted: setMuted,
    isMuted: function () { return muted; },
    state: function () { return ctx ? ctx.state : 'idle'; }   // 'running' once unlocked
  };
})();
