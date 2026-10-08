// One navigation for every page: Home · Globe · Dashboard · Chip · Silicon · Drivers · Model check.
// Put <div data-sitenav data-page="globe"></div> anywhere on the page. It's docked in the same place on every page,
// top right, so switching pages never moves it: full tabs on wide windows, one Menu button below COLLAPSE pixels.
// Pages keep the top 65px of their right side clear for it (12px gap + 41px bar + 12px).
(() => {
  const base = new URL('../', document.currentScript.src);
  const ICON = {
    home: '<rect x="7" y="7" width="18" height="18" rx="4"/><path d="M12 7V4M16 7V4M20 7V4M12 28v-3M16 28v-3M20 28v-3M7 12H4M7 16H4M7 20H4M28 12h-3M28 16h-3M28 20h-3"/><path d="M9.5 20.5h13" stroke-linecap="round"/><path d="M13 20.5a3 3 0 0 1 6 0M10.5 20.5a5.5 5.5 0 0 1 11 0" stroke-linecap="round"/><circle cx="16" cy="20.5" r="1.7" fill="currentColor" stroke="none"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.8 3 2.8 15 0 18M12 3c-2.8 3-2.8 15 0 18"/>',
    stats: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    chip: '<path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/>',
    model: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    drivers: '<path d="M5 16V11l2-5h10l2 5v5"/><path d="M3 16h18v3H3z"/><circle cx="7.5" cy="19" r="1.5"/><circle cx="16.5" cy="19" r="1.5"/><path d="M5 11h14"/>',
    silicon: '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  };
  const COLLAPSE = 1160;
  const PAGES = [
    { id: 'home', href: '', label: 'Home', desc: 'The chip, taken apart layer by layer' },
    { id: 'globe', href: 'globe/', label: 'Globe', desc: 'Every flight in the air, with fuel left' },
    { id: 'stats', href: 'stats/', label: 'Dashboard', desc: 'Fuel and CO₂ right now, plus what-ifs' },
    { id: 'chip', href: 'chip/', label: 'Chip', desc: 'Explore HZN-1 in 3D and follow a message' },
    { id: 'silicon', href: 'silicon/', label: 'Silicon', desc: 'One block built as a real chip layout' },
    { id: 'drivers', href: 'drivers/', label: 'Drivers', desc: 'A fuel-rewards concept for ride-hail drivers' },
    { id: 'model', href: 'model/', label: 'Model check', desc: 'How accurate the fuel estimates are' },
  ];
  const icon = id => '<svg viewBox="' + (id === 'home' ? '0 0 32 32' : '0 0 24 24') + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ICON[id] + '</svg>';

  const css = document.createElement('style');
  css.textContent = `
.sn{--sn-text:var(--text,var(--ink,#e8eef5));--sn-muted:var(--muted,#8a98aa);--sn-line:var(--line,rgba(160,190,225,.14));--sn-accent:var(--accent,#7cc4ff);
  position:relative;display:flex;align-items:center;font:500 13.5px/1 Geist,ui-sans-serif,system-ui,-apple-system,sans-serif;pointer-events:auto}
.sn-dock{position:fixed;top:calc(12px + env(safe-area-inset-top,0px));right:calc(16px + env(safe-area-inset-right,0px));z-index:900}
.sn-tabs{position:relative;display:flex;gap:2px;padding:4px;border-radius:999px;background:rgba(10,16,24,.66);border:1px solid var(--sn-line);backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2)}
.sn-tab{position:relative;z-index:1;display:flex;align-items:center;gap:7px;padding:8px 13px;border-radius:999px;color:var(--sn-muted);text-decoration:none;white-space:nowrap;transition:color .15s,background .15s}
.sn-tab svg{width:15px;height:15px;flex-shrink:0}
.sn-tab:hover{color:var(--sn-text);background:rgba(255,255,255,.06)}
/* a soft highlight that glides to whichever tab the pointer is over */
.sn-glide{position:absolute;top:4px;bottom:4px;left:0;width:0;border-radius:999px;background:rgba(255,255,255,.07);opacity:0;pointer-events:none;transition:transform .32s cubic-bezier(.3,.7,.2,1),width .32s cubic-bezier(.3,.7,.2,1),opacity .2s}
.sn-tabs.gliding .sn-tab:hover{background:none}
@media (prefers-reduced-motion:reduce){.sn-glide{transition:opacity .2s}}
.sn-tab[aria-current="page"]{color:#06121c;background:var(--sn-text)}
.sn-btn{all:unset;cursor:pointer;display:none;align-items:center;gap:8px;padding:9px 14px;border-radius:999px;color:var(--sn-text);background:rgba(10,16,24,.66);border:1px solid var(--sn-line);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);white-space:nowrap}
.sn-btn svg{width:15px;height:15px}
.sn-btn:focus-visible,.sn-tab:focus-visible,.sn-item:focus-visible{outline:2px solid var(--sn-accent);outline-offset:2px}
.sn.compact .sn-tabs{display:none}
.sn.compact .sn-btn{display:inline-flex;box-sizing:border-box;width:144px}  /* one width on every page, so the menu never shifts */
.sn-pop{position:absolute;top:calc(100% + 8px);left:0;z-index:60;width:min(300px,calc(100vw - 32px));padding:6px;border-radius:16px;background:rgba(10,16,24,.94);border:1px solid var(--sn-line);
  backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 18px 40px rgba(0,0,0,.45);display:flex;flex-direction:column}
.sn-dock .sn-pop{left:auto;right:0}
.sn-item{display:grid;grid-template-columns:34px 1fr;gap:2px 10px;align-items:center;padding:9px 10px;border-radius:11px;text-decoration:none;color:#e8eef5}
.sn-item:hover{background:rgba(255,255,255,.06)}
.sn-item i{grid-row:1/span 2;width:34px;height:34px;border-radius:9px;display:grid;place-items:center;background:rgba(124,196,255,.12);color:#7cc4ff}
.sn-item i svg{width:17px;height:17px}
.sn-item b{font-weight:500;font-size:14px}
.sn-item small{font-size:12px;color:#8a98aa;line-height:1.3}
.sn-item[aria-current="page"]{background:rgba(124,196,255,.1)}
.sn-item[aria-current="page"] b::after{content:" · you're here";font-weight:400;color:#8a98aa}
.sn-pop[hidden]{display:none}`;
  document.head.appendChild(css);

  document.querySelectorAll('[data-sitenav]').forEach(nav => {
    const here = nav.dataset.page;
    document.body.appendChild(nav);  // out of the page's own header, so every page shows it in exactly the same spot
    nav.classList.add('sn', 'sn-dock');
    nav.setAttribute('aria-label', 'Site');
    if (nav.tagName !== 'NAV') nav.setAttribute('role', 'navigation');
    const url = p => new URL(p.href, base).href;
    const cur = p => (p.id === here ? ' aria-current="page"' : '');
    nav.innerHTML =
      '<div class="sn-tabs">' + PAGES.map(p => '<a class="sn-tab" href="' + url(p) + '"' + cur(p) + '>' + icon(p.id) + '<span>' + p.label + '</span></a>').join('') + '</div>' +
      '<button class="sn-btn" type="button" aria-expanded="false" aria-haspopup="true">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>' +
        '<span>' + (PAGES.find(p => p.id === here) || PAGES[0]).label + '</span></button>' +
      '<div class="sn-pop" role="menu" hidden>' + PAGES.map(p => '<a class="sn-item" role="menuitem" href="' + url(p) + '"' + cur(p) + '><i>' + icon(p.id) + '</i><b>' + p.label + '</b><small>' + p.desc + '</small></a>').join('') + '</div>';
    const btn = nav.querySelector('.sn-btn'), pop = nav.querySelector('.sn-pop');
    const setOpen = open => { pop.hidden = !open; btn.setAttribute('aria-expanded', String(open));
      if (open) pop.querySelector('.sn-item').focus({ preventScroll: true }); };
    btn.addEventListener('click', e => { e.stopPropagation(); setOpen(pop.hidden); });
    document.addEventListener('click', e => { if (!nav.contains(e.target)) setOpen(false); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !pop.hidden) { setOpen(false); btn.focus(); } });
    // the gliding highlight (mouse and trackpad only)
    const tabs = nav.querySelector('.sn-tabs');
    if (matchMedia('(hover: hover)').matches) {
      const glide = document.createElement('span'); glide.className = 'sn-glide'; tabs.prepend(glide); tabs.classList.add('gliding');
      tabs.addEventListener('pointerover', e => { const t = e.target.closest('.sn-tab'); if (!t || t.getAttribute('aria-current')) { glide.style.opacity = 0; return; }
        const jump = glide.style.opacity !== '1';  // appearing: start under the tab instead of sliding in from the edge
        if (jump) glide.style.transition = 'opacity .2s';
        glide.style.width = t.offsetWidth + 'px'; glide.style.transform = 'translateX(' + t.offsetLeft + 'px)';
        if (jump) { void glide.offsetWidth; glide.style.transition = ''; }
        glide.style.opacity = 1; });
      tabs.addEventListener('pointerleave', () => { glide.style.opacity = 0; });
    }
    const fit = () => { const compact = innerWidth < COLLAPSE; nav.classList.toggle('compact', compact); if (!compact) setOpen(false); };
    addEventListener('resize', fit); fit();
  });
})();
