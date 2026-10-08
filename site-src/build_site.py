"""Build the public website's sub-pages in ../docs from the page sources in this folder.

    python3 site-src/build_site.py [path/to/fh-data.json]

Pages: docs/globe (Fuel Horizon snapshot), docs/chip (Inside HZN-1 explorer), docs/model (fuel model check),
docs/stats (hourly fuel & CO2 dashboard), docs/silicon (the real CRC-24 checker layout;
its images live in docs/silicon and come from the hzn-1-silicon repo's GDS action).
The landing page (docs/index.html) and docs/assets are edited directly.
Passing a fresh fh-data.json (from the snapshot bundler) also refreshes the globe's recorded flights.
"""
import hashlib, json, math, re, sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
DOCS = SRC.parent / "docs"

HEAD = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">\n'
        + ''.join(f'<script src="../assets/{n}.js?v=__V_{n}__" defer></script>\n' for n in ("analytics", "sitenav", "tour", "fx"))
        + '<style>@view-transition{navigation:auto}::view-transition-old(root),::view-transition-new(root){animation-duration:.32s}</style>\n'
        + ''.join(f'<meta {k}="{n}" content="{v}">\n' for k, n, v in [
            ("property", "og:image:width", "1200"), ("property", "og:image:height", "630"),
            ("property", "og:site_name", "HZN-1"), ("name", "twitter:card", "summary_large_image")]))
LINKS = {  # the published artifact links become relative links inside the site
    "https://claude.ai/artifact/BPyUVxays1xfAfQw4hxFaD": "../globe/",
    "https://claude.ai/artifact/QikibNNyAbzssymtuLyMsT": "../model/",
    "https://claude.ai/artifact/FZrd6xYcEQB9wsWajUwTsp": "../chip/",
}


def localize(s):
    for a, b in LINKS.items():
        # internal links open in the same tab and lose the external-link arrow
        s = re.sub(r'href="' + re.escape(a) + r'"( target="_blank")?( rel="noopener")?', f'href="{b}"', s)
        s = s.replace(a, b)
    s = re.sub(r'(href="\.\./(?:globe|model|chip)/"[^>]*>[^<]*?) ↗', r"\1", s)
    assert "claude.ai/artifact" not in s
    return s


def rep(s, a, b):
    assert s.count(a) == 1, f"expected one match for {a[:60]!r}, found {s.count(a)}"
    return s.replace(a, b)


SITE = "https://hzn1.com/"
DESCRIPTIONS = {  # what search engines and link previews show for each page
    "globe": "Every flight in the air on a 3D globe, refreshed hourly, with an estimate of the fuel each plane has left, "
             "its electric twin, airport boards and a 24-hour replay.",
    "chip": "Explore HZN-1 in 3D: the layers of a concept chip that decodes aircraft broadcasts, and one real message "
            "followed through it step by step.",
    "model": "How accurate Fuel Horizon's fuel estimates are: a per-aircraft model checked against 126 published "
             "fuel-burn figures, within about 5% on figures it never saw.",
    "silicon": "One block of HZN-1 built as a real SkyWater SKY130 chip layout: a Mode S CRC-24 checker tested on "
               "real ADS-B messages, which you can run in your browser.",
    "drivers": "A concept for ride-hail drivers: estimate fuel left from trips, predict the next fill-up and steer it "
               "to a partner station that pays for the visit. Watch a simulated shift and the economics.",
    "stats": "How much jet fuel is burning in the sky right now, which airlines and aircraft burn it, the last 24 "
             "hours, and what SAF, batteries, hybrids or hydrogen could save. Updated every hour.",
}


SHARED = ("analytics", "sitenav", "tour", "fx")  # scripts every page loads


def versioned(text):
    """Stamp the shared scripts' links with a hash of their contents, so browsers fetch them again only when they change."""
    for n in SHARED:
        text = text.replace(f"__V_{n}__", version(DOCS / "assets" / f"{n}.js"))
    return text


def stamp_landing():
    p = DOCS / "index.html"; s = p.read_text()
    s = re.sub(r'assets/live\.json(\?v=[0-9a-f]+)?', 'assets/live.json?v=' + version(DOCS / "assets" / "live.json"), s)
    for n in SHARED:
        s = re.sub(rf'src="assets/{n}\.js(\?v=[0-9a-f]+)?"', f'src="assets/{n}.js?v={version(DOCS / "assets" / f"{n}.js")}"', s)
    s = re.sub(r'(<meta property="og:image" content="[^"]*/assets/og\.jpg)(\?v=[0-9a-f]+)?"', lambda m: m.group(1) + "?v=" + version(DOCS / "assets" / "og.jpg") + '"', s)
    p.write_text(s)


def write(name, html):
    out = DOCS / name / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    d = DESCRIPTIONS[name].replace('"', "&quot;")
    img = {"globe": "og-globe.jpg", "stats": "og-stats.jpg", "silicon": "og-silicon.jpg", "drivers": "og-drivers.jpg"}.get(name, "og.jpg")  # share image for this page
    img += "?v=" + version(DOCS / "assets" / img.split("?")[0])  # so link previews pick up a changed image
    page = (f'<meta property="og:image" content="{SITE}assets/{img}">\n'
            f'<meta name="description" content="{d}">\n<meta property="og:description" content="{d}">\n'
            f'<link rel="canonical" href="{SITE}{name}/">\n<meta property="og:url" content="{SITE}{name}/">\n')
    t = re.search(r"<title>(.*?)</title>", html)
    if t:
        page += f'<meta property="og:title" content="{t.group(1)}">\n'
    out.write_text(versioned(HEAD) + page + localize(html))
    print(f"{out.relative_to(DOCS.parent)}  {out.stat().st_size / 1e3:.0f} kB")


# ---------- assets/live.json: the home page's live numbers and its decoder feed ----------
ADSB_CHARS = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ##### ###############0123456789######"


def adsb_ident(icao, callsign):
    """A Mode S extended squitter (DF17) identification message for this aircraft, with its real 24-bit check code.
    Same encoding the plane broadcasts, so it passes the same check as the HZN-1 silicon block."""
    cs = (callsign.upper() + " " * 8)[:8]
    if any(c not in ADSB_CHARS or c == "#" for c in cs):
        return None
    me = 4 << 51  # type code 4: aircraft identification
    for i, c in enumerate(cs):
        me |= ADSB_CHARS.index(c) << (42 - 6 * i)
    data = (((17 << 3) | 5) << 24 | int(icao, 16)) << 56 | me
    rem = 0
    for i in range(88):
        b = (data >> (87 - i)) & 1
        fb = ((rem >> 23) & 1) ^ b
        rem = ((rem << 1) & 0xFFFFFF) ^ (0xFFF409 if fb else 0)
    return f"{data:022X}{rem:06X}"


def write_live():
    st = json.loads((DOCS / "stats" / "stats.json").read_text())
    src = (DOCS / "globe" / "data.js").read_text()
    d = json.loads(src[src.index("=") + 1:src.rstrip().rindex("}") + 1])
    ap, msgs = d["ap"], []
    rows = [r for r in d["p"] if re.fullmatch(r"[A-Z]{3}\d{1,4}[A-Z]?", r[1] or "") and r[5] and r[5] > 15000 and r[11] in ap and r[12] in ap]
    rows.sort(key=lambda r: hashlib.md5((r[0] + str(st["t"])).encode()).hexdigest())  # a different mix each hour
    for r in rows:
        f = fuel_frac(r, ap)
        m = adsb_ident(r[0], r[1])
        if f < 0 or not m:
            continue
        msgs.append({"m": m, "cs": r[1], "o": ap[r[11]][0], "d": ap[r[12]][0], "alt": int(round(r[5], -2)), "f": int(round(f * 100))})
        if len(msgs) >= 48:
            break
    hist = [h[:3] for h in st.get("history", [])][-24:]
    out = {"t": st["t"], "n": st["n"], "burn": st["burn"], "hist": hist, "msgs": msgs}
    (DOCS / "assets" / "live.json").write_text(json.dumps(out, separators=(",", ":")))


def hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c); dl = math.radians(d - b)
    return 2 * 6371 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def fuel_frac(r, ap):
    """Fraction of takeoff fuel still on board for one snapshot row, or -1 when there's no route or model."""
    lat, lon, o, de, f = r[3], r[4], r[11], r[12], (r[16] if len(r) > 16 else 0)
    if not (f and f[0] and o in ap and de in ap):
        return -1
    D = hav(ap[o][2], ap[o][3], ap[de][2], ap[de][3]); flown = max(0, D - hav(lat, lon, ap[de][2], ap[de][3]))
    taxi = max(0, f[0] - f[1] - f[2]); x = f[4] * flown / max(f[3], 1e-6) if flown < f[3] else f[4] + (flown - f[3]) * f[5]
    return round(max(0, f[0] - taxi - min(x, f[1])) / f[0], 2)


def globe_points(d):
    """Dots for the landing page globe: land from the mask, flights with their fuel-left fraction (-1 = no route)."""
    from PIL import Image
    m = Image.open(SRC / "land-mask.png").convert("L"); W, H = m.size; px = m.load()
    n, ga, land = 42000, math.pi * (3 - 5 ** .5), []
    for i in range(n):
        y = 1 - 2 * (i + .5) / n; lat = math.degrees(math.asin(y)); lon = math.degrees((i * ga) % (2 * math.pi)) - 180
        if px[min(W - 1, int((lon + 180) / 360 * W)), min(H - 1, int((90 - lat) / 180 * H))] > 127:
            land += [round(lat, 2), round(lon, 2)]
    ap, flights = d["ap"], []
    for r in d["p"]:
        flights += [round(r[3], 2), round(r[4], 2), fuel_frac(r, ap)]
    out = {"land": land, "flights": flights, "t": d["t"], "n": len(d["p"]), "modelled": sum(1 for r in d["p"] if len(r) > 16 and r[16])}
    (DOCS / "assets" / "globe-points.json").write_text(json.dumps(out, separators=(",", ":")))


def write_globe_data(d):
    """Split a snapshot into static.js (outlines and place names, which never change) and data.js (the flights),
    so the hourly refresh only changes the smaller file."""
    static = {k: d.pop(k) for k in ("areas", "places") if k in d}
    if static:
        (DOCS / "globe" / "static.js").write_text("window.FH_STATIC=" + json.dumps(static, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/") + ";\n")
    (DOCS / "globe" / "data.js").write_text("window.FH_DATA=" + json.dumps(d, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/") + ";\n")


def version(path):
    """Short content hash, added to file links so browsers fetch a file again only when it changes."""
    return hashlib.sha1(path.read_bytes()).hexdigest()[:10] if path.exists() else "0"


# loading indicator: covers the page while the flight data downloads, then shrinks to a pill until the imagery arrives
LOADING = """<style>
#loading{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:radial-gradient(120% 90% at 50% 45%,#0c1420 0%,#060a10 62%);transition:opacity .45s,background .45s}
#loading .ld{display:flex;flex-direction:column;align-items:center;gap:16px}
#loading .mark{width:68px;height:68px;color:#7cc4ff;filter:drop-shadow(0 0 14px rgba(124,196,255,.45))}
#loading .mark .a1,#loading .mark .a2{animation:sig 1.6s ease-in-out infinite}
#loading .mark .a2{animation-delay:.22s}
#loading .mark .dot{animation:sig 1.6s ease-in-out infinite;animation-delay:-.2s}
@keyframes sig{0%,100%{opacity:.18}45%{opacity:1}}
#loading .pill{display:flex;align-items:center;gap:10px;font:500 12px/1.2 "Geist Mono",ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase;color:#8c9bad}
#loading i{width:13px;height:13px;border-radius:50%;border:2px solid rgba(124,196,255,.25);border-top-color:#7cc4ff;animation:spin .8s linear infinite;display:none}
#loading.imagery{inset:auto 0 auto 0;top:calc(112px + env(safe-area-inset-top,0px));background:none;pointer-events:none}
#loading.imagery .mark{display:none}
#loading.imagery i{display:block}
#loading.imagery .pill{padding:10px 16px;border-radius:999px;background:rgba(13,19,27,.82);border:1px solid rgba(255,255,255,.08);font:500 13.5px/1.2 Geist,system-ui,sans-serif;letter-spacing:0;text-transform:none;color:#e6edf5;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
@media (max-width:760px){#loading.imagery{top:calc(152px + env(safe-area-inset-top,0px))}}
#loading.done{opacity:0}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){#loading i{animation-duration:3s}#loading .mark *{animation:none!important}}
</style>
<div id="loading" role="status" aria-live="polite"><div class="ld">
<svg class="mark" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="7" y="7" width="18" height="18" rx="4"/><path d="M12 7V4M16 7V4M20 7V4M12 28v-3M16 28v-3M20 28v-3M7 12H4M7 16H4M7 20H4M28 12h-3M28 16h-3M28 20h-3"/><path d="M9.5 20.5h13" stroke-linecap="round"/><path class="a1" d="M13 20.5a3 3 0 0 1 6 0" stroke-linecap="round"/><path class="a2" d="M10.5 20.5a5.5 5.5 0 0 1 11 0" stroke-linecap="round"/><circle class="dot" cx="16" cy="20.5" r="1.7" fill="currentColor" stroke="none"/></svg>
<div class="pill"><i aria-hidden="true"></i><span>Listening for flights…</span></div></div></div>
<script>
function setLoading(t){const e=document.getElementById('loading');if(e){e.classList.add('imagery');e.querySelector('span').textContent=t;}}
function hideLoading(){const e=document.getElementById('loading');if(e&&!e.classList.contains('done')){e.classList.add('done');setTimeout(()=>e.remove(),500);}}
setTimeout(hideLoading,20000);
</script>
"""


def build(data_json=None):
    if data_json:
        d = json.loads(Path(data_json).read_text())
        globe_points(d)
        write_globe_data(d)
        print("refreshed docs/globe/data.js and docs/assets/globe-points.json")
    # globe: data and imagery are separate files the browser can cache; phones get half-size imagery,
    # larger screens load it first and then swap in the full-resolution version
    g = (SRC / "globe.html").read_text()
    g = rep(g, '<script type="application/json" id="fh">__DATA__</script>',
            LOADING + f'<script src="static.js?v={version(DOCS / "globe" / "static.js")}"></script>\n'
                      f'<script src="data.js?v={version(DOCS / "globe" / "data.js")}"></script>')
    g = rep(g, '<script>const EARTH_WEST="data:image/jpeg;base64,__EARTH0__";</script>',
            '<script>const EARTH_WEST="earth-west-small.webp",EARTH_EAST="earth-east-small.webp";'
            'const EARTH_HI=Math.min(screen.width,screen.height)<820||(navigator.connection&&navigator.connection.saveData)?null:["earth-west.webp","earth-east.webp"];</script>')
    g = rep(g, '<script>const EARTH_EAST="data:image/jpeg;base64,__EARTH1__";</script>\n', '')
    g = rep(g, "const DATA=JSON.parse(document.getElementById('fh').textContent);", "const DATA=Object.assign({},window.FH_STATIC,window.FH_DATA);")
    g = rep(g, "function buildEarth(){\n  [EARTH_WEST,EARTH_EAST].forEach((src,i)=>{const img=new Image();img.onload=()=>{",
            "function buildEarth(){\n  setLoading('Loading satellite imagery…');\n  loadEarth([EARTH_WEST,EARTH_EAST],()=>{hideLoading();loadLights();if(EARTH_HI)loadEarth(EARTH_HI);});\n}\n"
            "function loadEarth(srcs,done){let left=srcs.length;const finish=()=>{if(--left===0&&done)done();};\n"
            "  srcs.forEach((src,i)=>{const img=new Image();img.onerror=finish;img.onload=()=>{")
    g = rep(g, "earthMats[i].uniforms.map.value=tex;earthMats[i].uniforms.hasMap.value=1;};img.src=src;});",
            "const old=earthMats[i].uniforms.map.value;earthMats[i].uniforms.map.value=tex;earthMats[i].uniforms.hasMap.value=1;if(old&&old.dispose)old.dispose();finish();};img.src=src;});")
    g = rep(g, "replay.json?v=__RV__", f"replay.json?v={version(DOCS / 'globe' / 'replay.json')}")
    g = re.sub(r'<div class="brand">(.*?)</div>', r'<a class="brand" href="../" style="pointer-events:auto;color:inherit;text-decoration:none" aria-label="HZN-1 home">\1</a>', g, count=1)
    write("globe", g)

    c = (SRC / "chip.html").read_text()
    c = rep(c, '<header class="top">\n  <div class="brand">', '<header class="top">\n  <a class="brand" href="../" style="color:inherit;text-decoration:none" aria-label="HZN-1 home">')
    c = rep(c, '<div><h1>Inside HZN-1</h1><p>A look inside the chip behind Fuel Horizon</p></div>\n  </div>',
            '<div><h1>Inside HZN-1</h1><p>A look inside the chip behind Fuel Horizon</p></div>\n  </a>')
    write("chip", c)

    st = (SRC / "stats.html").read_text()
    write("stats", rep(st, "stats.json?v=__SV__", f"stats.json?v={version(DOCS / 'stats' / 'stats.json')}"))

    m = (SRC / "model.html").read_text()
    m = rep(m, "__DATA__", (SRC / "model-data.json").read_text().replace("</", "<\\/"))
    m = rep(m, '<div class="eyebrow"><b>Fuel Horizon</b>', '<div class="eyebrow"><a href="../" style="text-decoration:none"><b>HZN-1</b></a><span>·</span><a href="../globe/" style="text-decoration:none"><b>Fuel Horizon</b></a>')
    write("model", m)

    write("silicon", (SRC / "silicon.html").read_text())
    write("drivers", (SRC / "drivers.html").read_text())
    write_live()
    stamp_landing()


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
