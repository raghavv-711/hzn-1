// Two small finishing touches shared by every page:
//  1. Decoding text: monospace labels scramble through random characters and settle into the real text the first
//     time they scroll into view, like a radio message being decoded. Runs once per label.
//  2. Spotlight: on cards and panels, a soft light follows the cursor and lights the border nearest to it.
// Both stay off for people who ask for reduced motion, and the spotlight only runs with a mouse or trackpad.
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const path = location.pathname;
  const on3d = /\/(globe|chip)\/?$/.test(path);  // full-screen 3D pages keep their own look

  // ---------- 1. decoding text ----------
  const GLYPHS = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*+<>/';
  function decode(el) {
    const nodes = [], walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n; (n = walk.nextNode());) if (n.nodeValue.trim()) nodes.push({ n, text: n.nodeValue });
    const total = nodes.reduce((a, x) => a + x.text.length, 0); if (!total) return;
    const dur = Math.min(900, 320 + total * 18), t0 = performance.now();
    const tick = now => {
      const p = Math.min(1, (now - t0) / dur), shown = Math.floor(p * p * (3 - 2 * p) * total);  // eased, left to right
      let i = 0;
      for (const x of nodes) {
        let out = '';
        for (const ch of x.text) { out += i < shown || /[\s·.,:;|()\-–—/]/.test(ch) ? ch : GLYPHS[(Math.random() * GLYPHS.length) | 0]; i++; }
        x.n.nodeValue = out;
      }
      if (p < 1) requestAnimationFrame(tick); else nodes.forEach(x => { x.n.nodeValue = x.text; });
    };
    requestAnimationFrame(tick);
  }
  if (!reduce && 'IntersectionObserver' in window) {
    // only monospace text, so scrambling never shifts the layout
    const isMono = el => /mono/i.test(getComputedStyle(el).fontFamily);
    const targets = [...document.querySelectorAll('.eyebrow, .stat .v, .tag, .real, .k, .lbl')].filter(el => isMono(el) && !el.closest('.sn, .tour, [data-sitenav]'));
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { io.unobserve(e.target); decode(e.target); } }), { threshold: .6 });
    targets.forEach(el => io.observe(el));
  }

  // ---------- 2. spotlight on cards ----------
  if (on3d || reduce || !matchMedia('(hover: hover) and (pointer: fine)').matches) return;
  const css = document.createElement('style');
  css.textContent = `
.fx-glow,.fx-rim{position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;transition:opacity .35s ease;z-index:1}
.fx-glow{background:radial-gradient(380px circle at var(--mx,50%) var(--my,50%),rgba(124,196,255,.11),transparent 65%)}
.fx-rim{padding:1px;background:radial-gradient(300px circle at var(--mx,50%) var(--my,50%),rgba(150,210,255,.8),transparent 70%);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude}
.fx-spot:hover>.fx-glow,.fx-spot:hover>.fx-rim{opacity:1}`;
  document.head.appendChild(css);
  const SEL = '.card, .quick a, .tiles, .stats, .panel, .pt, .out, .node, .gap, .next';
  function arm(el) {
    if (el.closest('.fx-spot')) return;  // already lit, or inside a lit panel
    if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
    el.classList.add('fx-spot');
    for (const c of ['fx-glow', 'fx-rim']) { const s = document.createElement('span'); s.className = c; s.setAttribute('aria-hidden', 'true'); el.appendChild(s); }
  }
  const armAll = () => document.querySelectorAll(SEL).forEach(arm);
  armAll(); addEventListener('load', armAll);
  let raf = 0, last = null;
  addEventListener('pointermove', e => {
    last = e; if (raf) return;
    raf = requestAnimationFrame(() => { raf = 0; const el = last.target.closest && last.target.closest('.fx-spot'); if (!el) return;
      const r = el.getBoundingClientRect(); el.style.setProperty('--mx', (last.clientX - r.left) + 'px'); el.style.setProperty('--my', (last.clientY - r.top) + 'px'); });
  }, { passive: true });
})();
