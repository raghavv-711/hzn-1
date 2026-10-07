// Guided tour: drives the site by itself for about a minute and a half, page by page, with a caption bar.
// Start it from any element with [data-tour-start], or by opening a page with ?tour in the address.
// Home (the chip story) → Globe (flights, Ask the globe, electric what-if, replay) → Dashboard → the end.
(() => {
  const root = new URL('../', document.currentScript.src);   // the site's home, wherever it's hosted
  const path = location.pathname;
  const page = /\/globe\/?$/.test(path) ? 'globe' : /\/stats\/?$/.test(path) ? 'stats' : /\/(chip|model)\/?$/.test(path) ? 'other' : 'home';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = s => document.querySelector(s);
  const next = p => { location.href = new URL(p + '?tour', root).href; };

  // ---------- caption bar ----------
  const css = document.createElement('style');
  css.textContent = `
.tour{position:fixed;left:50%;top:calc(74px + env(safe-area-inset-top,0px));transform:translateX(-50%);z-index:70;width:min(560px,calc(100vw - 32px));
  display:flex;flex-direction:column;gap:10px;padding:14px 16px 12px;border-radius:16px;background:rgba(10,16,24,.9);border:1px solid rgba(124,196,255,.3);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:0 18px 40px rgba(0,0,0,.45);font-family:Geist,ui-sans-serif,system-ui,sans-serif;color:#e8eef5}
.tour .say{font-size:16px;line-height:1.4;font-weight:500;min-height:22px}
.tour .row{display:flex;align-items:center;gap:8px}
.tour .k{font:500 11px/1 "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#7cc4ff;margin-right:auto}
.tour button{all:unset;cursor:pointer;font-size:12.5px;color:#8a98aa;padding:5px 10px;border-radius:999px;border:1px solid rgba(160,190,225,.18)}
.tour button:hover{color:#e8eef5;background:rgba(255,255,255,.06)}
.tour button:focus-visible{outline:2px solid #7cc4ff;outline-offset:2px}
.tour .bar{height:3px;border-radius:2px;background:rgba(255,255,255,.08);overflow:hidden}
.tour .bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#7cc4ff,#4fd1c5);transition:width .4s}
.tour .end{display:flex;gap:8px;flex-wrap:wrap}
.tour .end a{font-size:13.5px;font-weight:500;text-decoration:none;padding:8px 14px;border-radius:999px;background:#e8eef5;color:#06121c}
.tour .end a.ghost{background:none;color:#e8eef5;border:1px solid rgba(160,190,225,.25)}
@media (max-width:760px){.tour{top:calc(64px + env(safe-area-inset-top,0px));padding:12px 14px 10px}.tour.p-globe{top:auto;bottom:calc(150px + env(safe-area-inset-bottom,0px))}.tour .say{font-size:14.5px}}`;
  document.head.appendChild(css);

  let hud, run = 0, paused = false;
  const OFFSET = { home: 0, globe: 8, stats: 16 }, TOTAL = 21;
  function show(text, n) {
    if (!hud) {
      hud = document.createElement('div'); hud.className = 'tour p-' + page; hud.setAttribute('role', 'status'); hud.setAttribute('aria-live', 'polite');
      hud.innerHTML = '<div class="row"><span class="k">Tour</span><button type="button" data-a="pause">Pause</button><button type="button" data-a="skip">Skip ›</button><button type="button" data-a="exit" aria-label="Exit tour">✕</button></div>' +
        '<div class="say"></div><div class="bar"><i></i></div>';
      hud.addEventListener('click', e => { const a = e.target.closest('button')?.dataset.a; if (!a) return;
        if (a === 'exit') stop(); else if (a === 'skip') skipTo(); else { paused = !paused; e.target.textContent = paused ? 'Resume' : 'Pause'; } });
      document.body.appendChild(hud);
    }
    hud.querySelector('.say').textContent = text;
    hud.querySelector('.k').textContent = 'Tour · ' + (OFFSET[page] + n) + ' of ' + TOTAL;
    hud.querySelector('.bar i').style.width = ((OFFSET[page] + n) / TOTAL * 100) + '%';
  }
  function stop() { run++; paused = false; if (hud) { hud.remove(); hud = null; } }
  function skipTo() { run++; if (page === 'home') next('globe/'); else if (page === 'globe') next('stats/'); else finale(); }
  addEventListener('keydown', e => { if (e.key === 'Escape' && hud) stop(); });

  // waits that respect Pause and stop instantly on Exit or Skip
  const wait = (ms, id) => new Promise((ok, no) => { let left = ms, t0 = performance.now();
    const tick = () => { if (id !== run) return no('stopped'); const now = performance.now(); if (!paused) left -= now - t0; t0 = now; left <= 0 ? ok() : setTimeout(tick, 100); }; tick(); });
  function scrollTo(y, ms, id) { // eased scroll that the story's 3D scene follows; counts only un-paused time
    return new Promise((ok, no) => { const y0 = scrollY, d = reduce ? 0 : ms; let prev = performance.now(), done = 0;
      // a plain timer rather than animation frames, so the tour keeps time even in a background tab
      const f = () => { if (id !== run) return no('stopped'); const now = performance.now(); if (!paused) done += now - prev; prev = now;
        const k = d ? Math.min(1, done / d) : 1, e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        window.scrollTo({ top: y0 + (y - y0) * e, behavior: 'instant' }); k < 1 ? setTimeout(f, 16) : ok(); };
      f(); });
  }

  const sec = (key, f) => { const s = $('section[data-key="' + key + '"]'); return s ? s.offsetTop + s.offsetHeight * f - innerHeight * .5 : 0; };
  const until = async (test, ms, id) => { const t0 = performance.now(); while (!test() && performance.now() - t0 < ms) await wait(150, id); };

  // ---------- the three legs ----------
  async function home(id) {
    show('This is HZN-1: a concept chip that listens to aircraft radio broadcasts and estimates each plane\'s fuel.', 1);
    await scrollTo(0, 600, id); await wait(4200, id);
    show('Under the lid: a slab of silicon about 3 mm across, wired to its package with hair-thin gold.', 2);
    await scrollTo(sec('lid', .4), 1600, id); await wait(3600, id);
    show('Inside, eight areas each do one job: listen, decode, remember every plane, estimate its fuel.', 3);
    await scrollTo(sec('floor', .4), 1600, id); await wait(3800, id);
    show('Follow one real message from a KLM flight as it moves through the chip…', 4);
    await scrollTo(sec('msg', .05), 1400, id); await wait(600, id);
    await scrollTo(sec('msg', .9), 9000, id); await wait(600, id);
    show('Pulled apart, the chip is a stack: switches at the bottom, five layers of wiring above.', 5);
    await scrollTo(sec('layers', .4), 1800, id); await wait(3600, id);
    show('Down at the bottom: about a million on/off switches, each 1/450 the width of a hair.', 6);
    await scrollTo(sec('fe', .4), 1600, id); await wait(3400, id);
    show('All of it feeds Fuel Horizon: every plane in the sky, colored by how much fuel it has left.', 7);
    await scrollTo(sec('globe', .4), 1800, id); await wait(3600, id);
    show('Let\'s open the live globe.', 8); await wait(1400, id);
    next('globe/');
  }
  async function globe(id) {
    show('Loading every flight in the air…', 1);
    await until(() => window.FH && window.FH.ready(), 15000, id);
    const F = window.FH; if (!F) return;
    F.deselect(); F.clearAsk(); F.clearArea(); F.mode('fuel');
    show('Real flights, refreshed every hour. Red is close to its reserve, teal still has plenty.', 2);
    F.fly(48, -25, 2.6); await wait(5200, id);
    show('Ask it anything. “Flights to London”…', 3);
    F.ask('flights to London'); await wait(5200, id);
    show('“Longest flight right now”: the top ten, with the longest selected.', 4);
    F.ask('longest flight right now'); await wait(6000, id);
    show('What if every plane ran on batteries? Dark red planes would run out before landing.', 5);
    F.clearAsk(); F.deselect(); F.mode('elec'); F.fly(40, -95, 2.4); await wait(6000, id);
    F.mode('fuel');
    show('Replay the last 24 hours. Watch night sweep around the world.', 6);
    F.fly(30, 20, 3.2); await F.openReplay(); await wait(9000, id);
    F.closeReplay();
    show('Next: the numbers behind it all.', 7); await wait(1600, id);
    show('Opening the dashboard…', 8); await wait(600, id);
    next('stats/');
  }
  async function stats(id) {
    const at = s => { const el = $(s); return el ? el.getBoundingClientRect().top + scrollY - 90 : 0; };
    show('Every hour: how many planes are flying and how much jet fuel they burn.', 1);
    await until(() => $('#tiles .tile'), 6000, id); await scrollTo(0, 400, id); await wait(4200, id);
    show('Which airlines burn the most fuel right now, and which use the least per seat.', 2);
    await scrollTo(at('#h-air'), 1600, id); await wait(4200, id);
    show('And what could change it: sustainable fuel, batteries, hybrids or hydrogen.', 3);
    await scrollTo(at('#h-what'), 1600, id); await wait(1500, id);
    const r = $('#safBlend'); if (r) { for (let v = +r.value; v <= 50; v += 2) { r.value = v; r.dispatchEvent(new Event('input')); await wait(60, id); } }
    show('A 50% sustainable fuel blend would cut lifecycle CO₂ by about 42% across every flight.', 4); await wait(5200, id);
    finale();
  }
  function finale() {
    run++; show('That\'s HZN-1 and Fuel Horizon. Explore it yourself:', 5);
    if (!hud.querySelector('.end')) { const e = document.createElement('div'); e.className = 'end';
      e.innerHTML = '<a href="' + new URL('globe/', root).href + '">Open the globe</a><a class="ghost" href="' + new URL('chip/', root).href + '">Explore the chip</a><a class="ghost" href="' + new URL('?tour', root).href + '">Watch again</a>';
      hud.insertBefore(e, hud.querySelector('.bar')); }
    hud.querySelectorAll('[data-a="pause"],[data-a="skip"]').forEach(b => b.remove());
    hud.querySelector('.bar i').style.width = '100%';
  }

  function start() {
    if (page === 'other') { next(''); return; }
    const id = ++run; paused = false;
    ({ home, globe, stats })[page](id).catch(() => {});
  }
  document.addEventListener('click', e => { const b = e.target.closest('[data-tour-start]'); if (!b) return; e.preventDefault(); if (page === 'home') start(); else next(''); });
  if (new URLSearchParams(location.search).has('tour')) {
    history.replaceState(null, '', location.pathname + location.hash);  // keep shared links clean
    addEventListener('load', () => setTimeout(start, 600));
  }
})();
