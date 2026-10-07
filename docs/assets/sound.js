// Optional sound design, made in the browser with the Web Audio API (no audio files):
// a quiet ambient hum with a little radio hiss, soft radio blips, and a gentle chime when the globe answers a question.
// Off until someone turns it on; the choice is remembered. Browsers only allow sound after a click or key press on
// each page, so when it's on but waiting, the speaker buttons show a pulsing dot and the next tap starts it.
(() => {
  // Pages shown inside the sound "shell" (see below) use the one audio engine that lives in the top page.
  let top = null; try { if (window !== window.top && window.top.HZNSound) top = window.top.HZNSound; } catch (e) {}
  if (top) {
    window.HZNSound = Object.assign({}, top, { subscribe: f => { const u = top.subscribe(f); addEventListener('pagehide', u); return u; } });
    return;
  }
  const KEY = 'hzn-sound';
  let on = false; try { on = localStorage.getItem(KEY) === 'on'; } catch (e) {}
  let ctx = null, master = null, hum = null;
  const listeners = new Set();
  const state = () => (!on ? 'off' : ctx && ctx.state === 'running' ? 'on' : 'waiting');
  const notify = () => listeners.forEach(f => { try { f(state()); } catch (e) { listeners.delete(f); } });

  function build() {
    if (ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    ctx = new AC();
    const comp = ctx.createDynamicsCompressor(); comp.connect(ctx.destination);
    master = ctx.createGain(); master.gain.value = 0; master.connect(comp);
    // hum: a low fifth, slightly detuned, through a soft low-pass, breathing slowly
    hum = ctx.createGain(); hum.gain.value = .045; hum.connect(master);
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 380; lp.connect(hum);
    [[55, 'sine', .9], [82.7, 'sine', .55], [110.3, 'triangle', .18]].forEach(([f, type, g]) => {
      const o = ctx.createOscillator(), v = ctx.createGain(); o.type = type; o.frequency.value = f; v.gain.value = g; o.connect(v); v.connect(lp); o.start(); });
    const lfo = ctx.createOscillator(), depth = ctx.createGain(); lfo.frequency.value = .07; depth.gain.value = .018; lfo.connect(depth); depth.connect(hum.gain); lfo.start();
    // faint radio air: filtered noise, very low
    const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate), d = buf.getChannelData(0);
    let last = 0; for (let i = 0; i < d.length; i++) { last = (last + .02 * (Math.random() * 2 - 1)) / 1.02; d[i] = last * 3.5; }
    const noise = ctx.createBufferSource(); noise.buffer = buf; noise.loop = true;
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 1400; bp.Q.value = .8;
    const ng = ctx.createGain(); ng.gain.value = .012; noise.connect(bp); bp.connect(ng); ng.connect(master); noise.start();
    ctx.onstatechange = notify;
  }
  function fadeTo(v, s) { if (!master) return; const t = ctx.currentTime; master.gain.cancelScheduledValues(t); master.gain.setTargetAtTime(v, t, s); }
  async function wake() { // needs a click or key press on this page
    if (!on) return; build(); if (!ctx) return;
    try { await ctx.resume(); } catch (e) {}
    if (ctx.state === 'running') fadeTo(.9, 1.2);
    notify();
  }
  function setOn(v) {
    on = v; try { localStorage.setItem(KEY, v ? 'on' : 'off'); } catch (e) {}
    if (v) wake(); else if (ctx) { fadeTo(0, .25); setTimeout(() => { if (!on && ctx) ctx.suspend(); notify(); }, 600); }
    notify();
  }
  ['pointerdown', 'keydown', 'touchstart'].forEach(ev => addEventListener(ev, () => { if (on && (!ctx || ctx.state !== 'running')) wake(); }, { passive: true }));

  const ready = () => on && ctx && ctx.state === 'running';
  function tone(freq, to, dur, gain, type = 'sine', delay = 0) {
    const t = ctx.currentTime + delay, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t); if (to) o.frequency.exponentialRampToValueAtTime(to, t + dur * .6);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + .006); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + dur + .05);
  }
  function click(delay = 0, gain = .05) { // a tiny burst of filtered noise, like a squelch
    const t = ctx.currentTime + delay, len = Math.floor(ctx.sampleRate * .03), b = ctx.createBuffer(1, len, ctx.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = b; f.type = 'bandpass'; f.frequency.value = 2600; f.Q.value = 1.2; g.gain.value = gain; s.connect(f); f.connect(g); g.connect(master); s.start(t);
  }
  const sounds = {
    blip: (n = 0) => { const f = 1180 + (n % 6) * 70; click(0, .035); tone(f, f * .74, .16, .06); },     // a radio blip
    step: () => { tone(880, 860, .22, .035); },                                                          // a tour caption changes
    answer: () => { click(0, .03); tone(660, 0, .55, .05, 'sine', .02); tone(990, 0, .7, .045, 'sine', .11); tone(1320, 0, .5, .02, 'triangle', .2); },
    sweep: () => { tone(220, 880, .9, .035, 'sine'); click(.05, .02); },                                 // the replay starts
  };

  // Browsers silence every newly loaded page until it's clicked. So while sound is on, site links open the next page
  // in a full-window frame on top of this page instead of replacing it: the audio keeps playing, and the address bar,
  // title and back button follow the page inside. Links inside that frame then move it along as usual.
  const SITE = new URL('../', document.currentScript.src);
  let shell = null;
  function sync() {
    try { const w = shell.contentWindow, href = w.location.href;
      if (href.startsWith('http') && href !== location.href) history.replaceState(null, '', href);
      if (w.document.title) document.title = w.document.title; } catch (e) {}
  }
  function go(url) {
    if (shell) { shell.contentWindow.location.href = url; return; }
    window.__hznCovered = true;
    for (const el of document.body.children) el.style.visibility = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    shell = document.createElement('iframe');
    shell.title = document.title; shell.setAttribute('allow', 'autoplay; fullscreen; clipboard-write');
    shell.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;border:0;z-index:2147483647;background:#04070b;visibility:visible';
    shell.addEventListener('load', () => { sync(); try { shell.contentWindow.focus(); } catch (e) {} });
    setInterval(sync, 700);
    shell.src = url; document.body.appendChild(shell);
  }
  document.addEventListener('click', e => {
    if (!on || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
    const u = new URL(a.href, location.href);
    if (u.origin !== location.origin || !u.pathname.startsWith(SITE.pathname)) return;
    if (u.pathname === location.pathname && u.search === location.search) return;  // a link within this page
    e.preventDefault(); wake(); go(u.href);
  }, true);

  window.HZNSound = {
    go: url => { if (!on) return false; wake(); go(new URL(url, location.href).href); return true; },
    play: (name, arg) => { if (ready() && sounds[name]) try { sounds[name](arg); } catch (e) {} },
    toggle: () => { if (on && ctx && ctx.state !== 'running') wake(); else setOn(!on); },
    state, subscribe: f => { listeners.add(f); f(state()); return () => listeners.delete(f); },
  };
})();
