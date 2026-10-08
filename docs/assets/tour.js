// Guided tour: a narrated walk through the site, page by page.
// A voice reads each step (the browser's own speech, no audio files) while the words light up as they're spoken,
// and a glowing ring glides to whatever is being talked about. Speed, pause, back/next and voice on/off are in the bar.
// Start it from any element with [data-tour-start], or open a page with ?tour (or ?tour=N for step N).
(() => {
  const root = new URL('../', document.currentScript.src);   // the site's home, wherever it's hosted
  const path = location.pathname;
  const page = /\/globe\/?$/.test(path) ? 'globe' : /\/stats\/?$/.test(path) ? 'stats' : /\/(chip|model|silicon|drivers)\/?$/.test(path) ? 'other' : 'home';
  const PAGE_URL = { home: '', globe: 'globe/', stats: 'stats/' };
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = s => document.querySelector(s);
  const store = {
    get: (k, d) => { try { const v = localStorage.getItem('hzn-tour-' + k); return v == null ? d : v; } catch (e) { return d; } },
    set: (k, v) => { try { localStorage.setItem('hzn-tour-' + k, v); } catch (e) {} },
  };
  const SPEEDS = [.75, 1, 1.25, 1.5], RATE = { .75: .8, 1: .98, 1.25: 1.18, 1.5: 1.38 };
  let speed = +store.get('speed', '1'); if (!SPEEDS.includes(speed)) speed = 1;
  let voiceOn = store.get('voice', 'on') !== 'off';

  // ---------- the voice: lives in the top window, so it keeps talking while pages change underneath ----------
  function makeVoice() {
    const ss = window.speechSynthesis; if (!ss || !window.SpeechSynthesisUtterance) return null;
    const PREF = [/Samantha/i, /\bAva\b/i, /Allison/i, /Microsoft (Aria|Jenny|Guy).*Natural/i, /Google US English/i, /Microsoft (Aria|Jenny|Zira)/i, /Daniel/i, /Karen/i];
    let voice = null;
    const pick = () => { const vs = ss.getVoices().filter(v => /^en([-_]|$)/i.test(v.lang)); for (const re of PREF) { const v = vs.find(x => re.test(x.name)); if (v) return v; }
      return vs.find(v => /en[-_]US/i.test(v.lang)) || vs[0] || null; };
    voice = pick(); if (ss.addEventListener) ss.addEventListener('voiceschanged', () => { voice = pick(); });
    const V = {
      cur: null,  // kept so the browser doesn't drop the utterance (and its end event) early
      speak(text, rate, on) {
        ss.cancel(); const u = new SpeechSynthesisUtterance(text); V.cur = u;
        if (voice) { u.voice = voice; u.lang = voice.lang; } else u.lang = 'en-US';
        u.rate = rate; u.pitch = 1;
        const safe = f => (...a) => { try { f && f(...a); } catch (e) {} };
        u.onstart = safe(on.start); u.onboundary = safe(e => on.boundary && on.boundary(e.charIndex)); u.onend = u.onerror = safe(on.end);
        ss.speak(u);
      },
      cancel() { ss.cancel(); }, pause() { ss.pause(); }, resume() { ss.resume(); },
    };
    return V;
  }
  let voice = null; try { if (window !== window.top && window.top.__hznVoice) voice = window.top.__hznVoice; } catch (e) {}
  if (!voice) { voice = makeVoice(); if (window === window.top) window.__hznVoice = voice; }

  // ---------- moving between pages without losing the voice ----------
  // Browsers only let a page speak after a click on that page. So while the voice is on, the next page opens in a
  // full-window frame on top of this one; the voice keeps going here, and the address bar follows the page inside.
  const inShell = (() => { try { return window !== window.top && !!window.top.__hznShell; } catch (e) { return false; } })();
  function openShell(url) {
    window.__hznShell = true; window.__hznCovered = true;
    for (const el of document.body.children) el.style.visibility = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    const f = document.createElement('iframe'); f.title = document.title; f.setAttribute('allow', 'fullscreen; clipboard-write; geolocation');
    f.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;border:0;z-index:2147483647;background:#04070b;visibility:visible';
    const sync = () => { try { const w = f.contentWindow, href = w.location.href; if (href.startsWith('http') && href !== location.href) history.replaceState(null, '', href); if (w.document.title) document.title = w.document.title; } catch (e) {} };
    f.addEventListener('load', () => { sync(); try { f.contentWindow.focus(); } catch (e) {} }); setInterval(sync, 700);
    f.src = url; document.body.appendChild(f);
  }
  const goTo = url => {
    if (inShell) { location.href = url; return; }
    if (voiceOn && voice && window === window.top) { openShell(url); return; }
    location.href = url;
  };

  // ---------- look ----------
  const css = document.createElement('style');
  css.textContent = `
.tour{position:fixed;left:50%;bottom:calc(22px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);z-index:960;width:min(640px,calc(100vw - 24px));
  display:flex;flex-direction:column;gap:12px;padding:14px 16px 14px;border-radius:20px;background:rgba(9,14,21,.84);border:1px solid rgba(124,196,255,.24);
  backdrop-filter:blur(20px) saturate(1.3);-webkit-backdrop-filter:blur(20px) saturate(1.3);box-shadow:0 24px 60px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.03) inset;
  font-family:Geist,ui-sans-serif,system-ui,sans-serif;color:#e8eef5;animation:trIn .45s cubic-bezier(.3,.7,.2,1)}
@keyframes trIn{from{opacity:0;transform:translate(-50%,14px)}}
/* on the globe: centred in the gap between the flight card (left) and the colour key (right) */
.tour.at-top{bottom:auto;top:calc(112px + env(safe-area-inset-top,0px));left:calc(50% + 56px);width:max(360px,min(560px,calc(100vw - 640px)))}
.tour.at-right{left:auto;right:28px;transform:none;width:min(560px,calc(100vw - 24px));animation-name:trInR}
@keyframes trInR{from{opacity:0;transform:translateY(14px)}}
.tr-top{display:flex;align-items:center;gap:10px}
.tr-eq{display:flex;align-items:flex-end;gap:2px;height:14px;width:16px}
.tr-eq i{flex:1;height:30%;border-radius:2px;background:linear-gradient(#7cc4ff,#4fd1c5);opacity:.5;transition:height .2s}
.tour.talking .tr-eq i{opacity:1;animation:trEq .9s ease-in-out infinite}
.tour.talking .tr-eq i:nth-child(2){animation-delay:-.3s}.tour.talking .tr-eq i:nth-child(3){animation-delay:-.6s}.tour.talking .tr-eq i:nth-child(4){animation-delay:-.15s}
@keyframes trEq{0%,100%{height:25%}50%{height:100%}}
.tr-k{font:500 11px/1 "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#7cc4ff;margin-right:auto;white-space:nowrap}
.tr-ctl{display:flex;align-items:center;gap:4px}
.tr-ctl button{all:unset;cursor:pointer;height:30px;min-width:30px;padding:0 8px;box-sizing:border-box;border-radius:999px;display:grid;place-items:center;color:#9aa8b8;font:500 12.5px/1 "Geist Mono",ui-monospace,monospace;transition:background .15s,color .15s}
.tr-ctl button:hover{color:#e8eef5;background:rgba(255,255,255,.07)}
.tr-ctl button:focus-visible{outline:2px solid #7cc4ff;outline-offset:1px}
.tr-ctl button[disabled]{opacity:.35;pointer-events:none}
.tr-ctl svg{width:15px;height:15px}
.tr-ctl .sep{width:1px;height:16px;background:rgba(160,190,225,.18);margin:0 3px}
.tr-ctl [data-a="voice"][aria-pressed="true"]{color:#7cc4ff}
.tr-ctl [data-a="voice"].blocked{color:#f5b041;animation:trPulse 1.4s ease-in-out infinite}
@keyframes trPulse{50%{background:rgba(245,176,65,.16)}}
.tr-say{margin:0;font-size:17.5px;line-height:1.45;font-weight:500;letter-spacing:-.005em;min-height:26px}
.tr-say .w{color:rgba(232,238,245,.34);transition:color .18s,text-shadow .18s}
.tr-say .w.on{color:#e8eef5}
.tr-say .w.cur{color:#fff;text-shadow:0 0 14px rgba(124,196,255,.65)}
.tr-prog{display:flex;gap:3px}
.tr-prog i{flex:1;height:3px;border-radius:2px;background:rgba(255,255,255,.09);overflow:hidden;position:relative}
.tr-prog i.done{background:linear-gradient(90deg,#7cc4ff,#4fd1c5)}
.tr-prog i b{position:absolute;inset:0;width:0;background:linear-gradient(90deg,#7cc4ff,#4fd1c5)}
.tr-end{display:flex;gap:8px;flex-wrap:wrap}
.tr-end a{font-size:13.5px;font-weight:500;text-decoration:none;padding:8px 14px;border-radius:999px;background:#e8eef5;color:#06121c}
.tr-end a.ghost{background:none;color:#e8eef5;border:1px solid rgba(160,190,225,.25)}
.tr-ring{position:fixed;left:0;top:0;z-index:955;pointer-events:none;border-radius:16px;border:2px solid rgba(150,210,255,.95);opacity:0;transition:opacity .35s;
  box-shadow:0 0 0 5px rgba(124,196,255,.14),0 0 34px rgba(124,196,255,.45),inset 0 0 22px rgba(124,196,255,.12)}
.tr-ring.on{opacity:1}
.tr-ring.dim{box-shadow:0 0 0 5px rgba(124,196,255,.14),0 0 34px rgba(124,196,255,.45),0 0 0 200vmax rgba(3,6,10,.38)}
.tr-ring::after{content:"";position:absolute;inset:-9px;border-radius:22px;border:1px solid rgba(124,196,255,.45);animation:trRing 2s ease-out infinite}
@keyframes trRing{from{opacity:.9;transform:scale(.97)}to{opacity:0;transform:scale(1.06)}}
.tr-link{position:fixed;inset:0;width:100vw;height:100vh;z-index:958;pointer-events:none;overflow:visible}
.tr-link path{fill:none;stroke:url(#trGrad);stroke-width:1.6;stroke-linecap:round;transition:opacity .3s}
.tr-link circle{fill:#9fd4ff;transition:opacity .3s}
@media (max-width:760px){.tour{padding:12px 13px 12px;gap:10px;border-radius:18px}.tr-say{font-size:15.5px}.tour.at-top{top:calc(150px + env(safe-area-inset-top,0px));left:50%;width:calc(100vw - 24px)}.tr-ctl button{min-width:28px;padding:0 6px}}
@media (prefers-reduced-motion:reduce){.tour,.tr-ring::after{animation:none}.tour.talking .tr-eq i{animation:none}}`;
  document.head.appendChild(css);

  const ICON = {
    back: '<path d="M15 6l-6 6 6 6"/>', next: '<path d="M9 6l6 6-6 6"/>',
    pause: '<path d="M8 5v14M16 5v14"/>', play: '<path d="M7 5l12 7-12 7z" fill="currentColor" stroke="none"/>',
    voice: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    mute: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="m16 9.5 5 5M21 9.5l-5 5"/>', exit: '<path d="M6 6l12 12M18 6 6 18"/>',
  };
  const svg = k => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICON[k] + '</svg>';

  // ---------- small helpers that stop instantly when the step changes ----------
  let token = 0, paused = false, idx = -1, hud = null, ring = null, link = null, target = null, dim = false;
  const alive = my => my === token;
  const wait = (ms, my) => new Promise((ok, no) => { let left = ms / speed, t0 = performance.now();
    const tick = () => { if (!alive(my)) return no('stopped'); const now = performance.now(); if (!paused) left -= now - t0; t0 = now; left <= 0 ? ok() : setTimeout(tick, 60); }; tick(); });
  const until = async (test, ms, my) => { const t0 = performance.now(); while (!test() && performance.now() - t0 < ms) await wait(150 * speed, my); };
  function scrollTo(y, ms, my) {  // eased scroll the story's 3D scene follows; a timer rather than frames, so it keeps time in background tabs
    return new Promise((ok, no) => { const y0 = scrollY, d = reduce ? 0 : ms / speed; let prev = performance.now(), done = 0;
      const f = () => { if (!alive(my)) return no('stopped'); const now = performance.now(); if (!paused) done += now - prev; prev = now;
        const k = d ? Math.min(1, done / d) : 1, e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        window.scrollTo({ top: y0 + (y - y0) * e, behavior: 'instant' }); k < 1 ? setTimeout(f, 16) : ok(); }; f(); });
  }
  const sec = (key, f) => { const s = $('section[data-key="' + key + '"]'); return s ? s.offsetTop + s.offsetHeight * f - innerHeight * .5 : 0; };
  const copy = key => () => $('section[data-key="' + key + '"] .copy');
  async function typeInto(text, my) {  // types a question into the globe's search box, letter by letter
    const q = document.getElementById('q'); if (!q) return;
    q.value = '';
    for (const ch of text) { q.value += ch; if (!reduce) await wait(55, my); }
    await wait(350, my);
  }
  const clearSearch = () => { const q = document.getElementById('q'); if (q) q.value = ''; };
  const FH = () => window.FH;
  const globeReady = my => until(() => FH() && FH().ready(), 15000, my);

  // ---------- the script ----------
  const STEPS = [
    { page: 'home', target: copy('hero'), say: 'This is HZN-1: a concept chip that listens to the radio broadcasts every airliner sends, and estimates how much fuel each plane has left.',
      run: my => scrollTo(0, 600, my) },
    { page: 'home', target: copy('lid'), say: 'Under the lid is a slab of silicon about three millimeters across, wired to its package with hair-thin gold.',
      run: my => scrollTo(sec('lid', .4), 1600, my) },
    { page: 'home', target: copy('floor'), say: 'Inside, eight areas each do one job: listen, decode, remember every plane, and estimate its fuel.',
      run: my => scrollTo(sec('floor', .4), 1600, my) },
    { page: 'home', target: copy('msg'), say: 'Now follow one real message from a KLM flight as it travels through the chip.',
      run: async my => { await scrollTo(sec('msg', .05), 1400, my); await scrollTo(sec('msg', .9), 9000, my); } },
    { page: 'home', target: copy('layers'), say: 'Pulled apart, the chip is a stack: switches at the bottom, and five layers of wiring above them.',
      run: my => scrollTo(sec('layers', .4), 1800, my) },
    { page: 'home', target: copy('fe'), say: 'At the very bottom are about a million tiny on-off switches, each far thinner than a human hair.',
      run: my => scrollTo(sec('fe', .4), 1600, my) },
    { page: 'home', target: copy('globe'), say: 'All of it feeds Fuel Horizon: every plane in the sky, colored by how much fuel it has left.',
      run: my => scrollTo(sec('globe', .4), 1800, my) },
    { page: 'home', say: 'Let’s open the live globe.', after: 200 },

    { page: 'globe', say: 'Loading every flight in the air.', run: async my => { await globeReady(my); const F = FH(); if (F) { F.deselect(); F.clearAsk(); F.clearArea(); F.mode('fuel'); } }, after: 100 },
    { page: 'globe', target: () => $('#key'), say: 'These are real flights, refreshed every hour. Red planes are close to their fuel reserve; teal ones still have plenty.',
      run: async my => { await globeReady(my); const F = FH(); F.deselect(); F.clearAsk(); F.mode('fuel'); F.fly(48, -25, 2.6); } },
    { page: 'globe', target: () => $('.search'), say: 'You can ask the globe questions in plain English. Let’s try: flights to London.',
      run: async my => { await globeReady(my); const F = FH(); F.deselect(); F.mode('fuel'); await wait(1400, my); await typeInto('flights to London', my); F.ask('flights to London'); clearSearch(); await wait(1800, my); } },
    { page: 'globe', target: () => { const c = $('#card'); return c && !c.hidden ? c : $('.search'); }, say: 'Or: the longest flight right now. Here are the top ten, with the longest one selected.',
      run: async my => { await globeReady(my); const F = FH(); await typeInto('longest flight', my); F.ask('longest flight right now'); clearSearch(); await wait(2600, my); } },
    { page: 'globe', target: () => $('#mElec'), dim: false, say: 'What if every plane ran on batteries? The dark red ones would run out of charge before they land.',
      run: async my => { await globeReady(my); const F = FH(); F.clearAsk(); F.deselect(); F.mode('elec'); F.fly(40, -95, 2.4); await wait(2200, my); },
      leave: () => { const F = FH(); if (F) F.mode('fuel'); } },
    { page: 'globe', target: () => $('.replay'), say: 'You can also replay the last twenty-four hours, and watch night sweep around the world.',
      run: async my => { await globeReady(my); const F = FH(); F.mode('fuel'); F.fly(30, 20, 3.2); await F.openReplay(); await wait(6500, my); },
      leave: () => { const F = FH(); if (F) F.closeReplay(); } },
    { page: 'globe', say: 'Next, the numbers behind it all.', after: 200 },

    { page: 'stats', target: () => $('#tiles'), say: 'Every hour, the dashboard counts how many planes are flying and how much jet fuel they burn.',
      run: async my => { await until(() => $('#tiles .tile'), 6000, my); await scrollTo(0, 400, my); } },
    { page: 'stats', target: () => { const h = $('#h-air'); return h && (h.closest('section') || h); }, say: 'Here’s which airlines burn the most fuel right now, and which use the least per seat.',
      run: my => { const h = $('#h-air'); return scrollTo(h ? h.getBoundingClientRect().top + scrollY - 90 : 0, 1600, my); } },
    { page: 'stats', target: () => { const h = $('#h-what'); return h && (h.closest('section') || h); }, say: 'And what could change it: sustainable fuel, batteries, hybrids, or hydrogen.',
      run: my => { const h = $('#h-what'); return scrollTo(h ? h.getBoundingClientRect().top + scrollY - 90 : 0, 1600, my); } },
    { page: 'stats', target: () => { const r = $('#safBlend'); return r && (r.closest('.panel, .card, .scen, label, div') || r); },
      say: 'For example, a fifty percent sustainable fuel blend would cut lifecycle carbon emissions by about forty-two percent.',
      run: async my => { const r = $('#safBlend'); if (!r) return; r.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' }); await wait(700, my);
        for (let v = +r.value; v <= 50; v += 2) { r.value = v; r.dispatchEvent(new Event('input')); await wait(70, my); } } },
    { page: 'stats', say: 'That’s HZN-1 and Fuel Horizon. Explore it yourself.', end: true },
  ];

  // ---------- the bar ----------
  function build() {
    if (hud) return;
    hud = document.createElement('div'); hud.className = 'tour' + (page === 'globe' ? ' at-top' : page === 'home' && innerWidth >= 1000 ? ' at-right' : ''); hud.setAttribute('role', 'region'); hud.setAttribute('aria-label', 'Guided tour');
    hud.innerHTML = '<div class="tr-top"><span class="tr-eq" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span class="tr-k"></span><div class="tr-ctl">' +
      '<button type="button" data-a="back" aria-label="Previous step">' + svg('back') + '</button>' +
      '<button type="button" data-a="pause" aria-label="Pause">' + svg('pause') + '</button>' +
      '<button type="button" data-a="next" aria-label="Next step">' + svg('next') + '</button><span class="sep"></span>' +
      '<button type="button" data-a="speed" aria-label="Speed"></button>' +
      '<button type="button" data-a="voice"></button><span class="sep"></span>' +
      '<button type="button" data-a="exit" aria-label="Exit tour">' + svg('exit') + '</button></div></div>' +
      '<p class="tr-say" aria-live="polite"></p><div class="tr-prog">' + STEPS.map(() => '<i><b></b></i>').join('') + '</div>';
    document.body.appendChild(hud);
    ring = document.createElement('div'); ring.className = 'tr-ring'; document.body.appendChild(ring);
    link = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); link.setAttribute('class', 'tr-link'); link.setAttribute('aria-hidden', 'true');
    link.innerHTML = '<defs><linearGradient id="trGrad" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#7cc4ff" stop-opacity=".15"/><stop offset="1" stop-color="#9fd4ff" stop-opacity=".9"/></linearGradient></defs><path/><circle r="3.5"/>';
    document.body.appendChild(link);
    hud.addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; const a = b.dataset.a;
      if (a === 'exit') stop(true); else if (a === 'next') step(idx + 1); else if (a === 'back') step(Math.max(0, idx - 1));
      else if (a === 'pause') setPaused(!paused); else if (a === 'speed') { speed = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]; store.set('speed', speed); controls(); }
      else if (a === 'voice') { if (blocked) { blocked = false; voiceOn = true; } else voiceOn = !voiceOn; store.set('voice', voiceOn ? 'on' : 'off'); controls();
        if (voiceOn) step(idx); else if (voice) voice.cancel(); } });
    requestAnimationFrame(follow);
  }
  let blocked = false;
  function controls() {
    if (!hud) return;
    hud.querySelector('[data-a="speed"]').textContent = speed + '×';
    const v = hud.querySelector('[data-a="voice"]');
    if (v) {
      if (!voice) v.remove();
      else { v.innerHTML = svg(voiceOn && !blocked ? 'voice' : 'mute'); v.setAttribute('aria-pressed', String(voiceOn && !blocked)); v.classList.toggle('blocked', blocked);
        const t = blocked ? 'Tap to hear the narration' : voiceOn ? 'Voice on' : 'Voice off'; v.setAttribute('aria-label', t); v.title = t; }
    }
    const p = hud.querySelector('[data-a="pause"]'); if (p) { p.innerHTML = svg(paused ? 'play' : 'pause'); p.setAttribute('aria-label', paused ? 'Resume' : 'Pause'); }
    const bk = hud.querySelector('[data-a="back"]'); if (bk) bk.disabled = idx <= 0;
  }
  function setPaused(v) { paused = v; if (voice) { try { v ? voice.pause() : voice.resume(); } catch (e) {} } hud.classList.toggle('talking', !v && talking); controls(); }

  // ---------- the ring that points at things ----------
  const rr = { x: 0, y: 0, w: 0, h: 0, on: false };
  function follow() {
    if (!hud) return;
    const el = target && target(), r = el && el.getBoundingClientRect && el.getBoundingClientRect();
    const vis = !!(r && r.width > 4 && r.height > 4 && r.bottom > 40 && r.top < innerHeight - 40 && getComputedStyle(el).visibility !== 'hidden');
    if (vis) {
      const pad = 8, x = Math.max(4, r.left - pad), y = Math.max(4, r.top - pad), w = Math.min(innerWidth - 8, r.right + pad) - x, h = Math.min(innerHeight - 8, r.bottom + pad) - y;
      const k = rr.on && !reduce ? .2 : 1; rr.x += (x - rr.x) * k; rr.y += (y - rr.y) * k; rr.w += (w - rr.w) * k; rr.h += (h - rr.h) * k; rr.on = true;
      ring.style.transform = `translate(${rr.x}px,${rr.y}px)`; ring.style.width = rr.w + 'px'; ring.style.height = rr.h + 'px';
    } else rr.on = false;
    ring.classList.toggle('on', vis); ring.classList.toggle('dim', vis && dim);
    // a curved line from the caption to the ring
    const hb = hud.getBoundingClientRect(), path = link.querySelector('path'), dot = link.querySelector('circle');
    let show = false;
    if (vis) {
      // from the edge of the caption nearest the ring, to the edge of the ring nearest the caption
      const cl = (v, a, b) => Math.max(a, Math.min(b, v)), rcx = rr.x + rr.w / 2, rcy = rr.y + rr.h / 2;
      const sx = cl(rcx, hb.left + 18, hb.right - 18), sy = cl(rcy, hb.top, hb.bottom);
      const ex = cl(sx, rr.x, rr.x + rr.w), ey = cl(sy, rr.y, rr.y + rr.h);
      const overlap = !(rr.x + rr.w < hb.left || rr.x > hb.right || rr.y + rr.h < hb.top || rr.y > hb.bottom);
      if (!overlap && Math.hypot(ex - sx, ey - sy) > 50) {
        show = true; const dx = ex - sx, dy = ey - sy, horiz = Math.abs(dx) > Math.abs(dy);
        const c1 = horiz ? `${sx + dx / 2},${sy}` : `${sx},${sy + dy / 2}`, c2 = horiz ? `${ex - dx / 2},${ey}` : `${ex},${ey - dy / 2}`;
        path.setAttribute('d', `M${sx},${sy} C${c1} ${c2} ${ex},${ey}`); dot.setAttribute('cx', ex); dot.setAttribute('cy', ey);
        const g = link.querySelector('linearGradient'); g.setAttribute('x1', sx); g.setAttribute('y1', sy); g.setAttribute('x2', ex); g.setAttribute('y2', ey);
      }
    }
    path.style.opacity = dot.style.opacity = show ? 1 : 0;
    requestAnimationFrame(follow);
  }

  // ---------- narration: the voice, plus the words lighting up as they're said ----------
  let talking = false;
  function narrate(text, my) {
    const box = hud.querySelector('.tr-say'), bar = hud.querySelectorAll('.tr-prog b')[idx];
    const words = []; let html = '', m, last = 0; const re = /\S+/g;
    while ((m = re.exec(text))) { html += text.slice(last, m.index) + '<span class="w">' + m[0].replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]) + '</span>'; words.push(m.index); last = m.index + m[0].length; }
    box.innerHTML = html; const spans = box.querySelectorAll('.w');
    const light = n => spans.forEach((s, i) => { s.classList.toggle('on', i < n); s.classList.toggle('cur', i === n - 1); });
    const est = Math.max(2200, text.length * 66 / RATE[speed]);  // about how long the voice takes
    const useVoice = !!(voiceOn && !blocked && voice);
    return new Promise(done => {
      let finished = false, gotBoundary = false, started = false, t0 = performance.now(), held = 0, pausedAt = 0;
      const finish = () => { if (finished) return; finished = true; talking = false; if (hud) hud.classList.remove('talking'); light(spans.length); if (bar) bar.style.width = '100%'; done(); };
      const timed = () => {  // highlight by time when the voice is off or doesn't report word positions
        if (finished || !alive(my)) return;
        const now = performance.now(); if (paused) { if (!pausedAt) pausedAt = now; } else if (pausedAt) { held += now - pausedAt; pausedAt = 0; }
        const k = Math.min(1, (now - t0 - held) / (useVoice ? est : est * 1.15));
        if (!gotBoundary) light(Math.ceil(k * spans.length)); if (bar) bar.style.width = (k * 100) + '%';
        if (!useVoice && k >= 1) return finish();
        setTimeout(timed, 50);
      };
      if (useVoice) {
        talking = true; hud.classList.add('talking');
        voice.speak(text, RATE[speed], {
          start: () => { started = true; t0 = performance.now(); },
          boundary: ci => { if (!alive(my)) return; gotBoundary = true; let n = 0; while (n < words.length && words[n] <= ci) n++; light(n); },
          end: () => { if (alive(my)) finish(); },
        });
        // a page opened by a link (not a click here) may not be allowed to speak: carry on silently and offer a tap
        setTimeout(() => { if (alive(my) && !started && !finished && !paused) { blocked = true; controls(); voice.cancel(); talking = false; if (hud) hud.classList.remove('talking'); setTimeout(() => { if (alive(my)) finish(); }, Math.max(0, est * 1.15 - 1200)); } }, 1200);
        // and never hang if the voice forgets to say it's done
        const guard = () => { if (!alive(my) || finished) return; if (paused) return setTimeout(guard, 500); finish(); };
        setTimeout(guard, est * 1.8 + 1500);
      }
      timed();
    });
  }

  // ---------- running the steps ----------
  let leaveFn = null;
  async function step(i) {
    if (leaveFn) { try { leaveFn(); } catch (e) {} leaveFn = null; }
    if (voice) voice.cancel();
    const st = STEPS[i]; if (!st) return;
    if (st.page !== page) { token++; goTo(new URL(PAGE_URL[st.page] + '?tour=' + (i + 1), root).href); return; }
    build(); idx = i; const my = ++token; paused = false;
    target = st.target || null; dim = st.dim !== false && page !== 'home'; rr.on = false;
    hud.querySelector('.tr-k').textContent = 'Tour · ' + (i + 1) + ' of ' + STEPS.length;
    hud.querySelectorAll('.tr-prog i').forEach((x, j) => { x.classList.toggle('done', j < i); x.querySelector('b').style.width = j < i ? '100%' : '0'; });
    const end = hud.querySelector('.tr-end'); if (end) end.remove();
    hud.querySelectorAll('[data-a="pause"],[data-a="next"]').forEach(b => { b.style.display = ''; });
    controls();
    if (st.end) return finale(st, my);
    leaveFn = st.leave || null;
    try {
      await Promise.all([narrate(st.say, my), st.run ? Promise.resolve().then(() => st.run(my)) : null]);
      await wait(st.after != null ? st.after : 450, my);
    } catch (e) { return; }
    if (!alive(my)) return;
    step(i + 1);
  }
  async function finale(st, my) {
    target = null;
    const e = document.createElement('div'); e.className = 'tr-end';
    e.innerHTML = '<a href="' + new URL('globe/', root).href + '" target="_top">Open the globe</a><a class="ghost" href="' + new URL('silicon/', root).href + '" target="_top">See the real silicon</a>' +
      '<a class="ghost" href="' + new URL('?tour', root).href + '" target="_top">Watch again</a>';
    hud.insertBefore(e, hud.querySelector('.tr-prog'));
    hud.querySelectorAll('[data-a="pause"],[data-a="next"]').forEach(b => { b.style.display = 'none'; });
    hud.querySelectorAll('.tr-prog i').forEach(x => { x.classList.add('done'); x.querySelector('b').style.width = '100%'; });
    try { await narrate(st.say, my); } catch (e2) {}
  }
  function stop(exit) {
    token++; paused = false; target = null; if (voice) voice.cancel(); if (leaveFn) { try { leaveFn(); } catch (e) {} leaveFn = null; }
    [hud, ring, link].forEach(x => x && x.remove()); hud = ring = link = null; idx = -1;
    // leaving the tour from inside the narration frame: open this page normally, outside the frame
    if (exit && inShell) { try { window.top.location.href = location.href.replace(/[?&]tour(=\d+)?/, ''); } catch (e) {} }
  }
  addEventListener('keydown', e => {
    if (!hud || (e.target.closest && e.target.closest('input, textarea, select'))) return;
    if (e.key === 'Escape') stop(true);
    else if (e.key === 'ArrowRight') step(idx + 1);
    else if (e.key === 'ArrowLeft' && idx > 0) step(idx - 1);
  });

  // ---------- starting ----------
  const firstOf = p => STEPS.findIndex(s => s.page === p);
  function start(at) {
    if (page === 'other') { goTo(new URL('?tour', root).href); return; }
    step(at != null ? at : firstOf(page));
  }
  document.addEventListener('click', e => { const b = e.target.closest('[data-tour-start]'); if (!b) return; e.preventDefault();
    if (page === 'home') start(0); else goTo(new URL('?tour', root).href); });
  const q = new URLSearchParams(location.search);
  if (q.has('tour')) {
    const n = parseInt(q.get('tour'), 10), at = n > 0 && STEPS[n - 1] && STEPS[n - 1].page === page ? n - 1 : null;
    history.replaceState(null, '', location.pathname + location.hash);  // keep shared links clean
    addEventListener('load', () => setTimeout(() => start(at), 500));
  }
})();
