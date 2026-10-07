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
        + ''.join(f'<script src="../assets/{n}.js?v=__V_{n}__" defer></script>\n' for n in ("analytics", "sound", "sitenav", "tour"))
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


SITE = "https://raghavv-711.github.io/hzn-1/"
DESCRIPTIONS = {  # what search engines and link previews show for each page
    "globe": "Every flight in the air on a 3D globe, refreshed hourly, with an estimate of the fuel each plane has left, "
             "its electric twin, airport boards and a 24-hour replay.",
    "chip": "Explore HZN-1 in 3D: the layers of a concept chip that decodes aircraft broadcasts, and one real message "
            "followed through it step by step.",
    "model": "How accurate Fuel Horizon's fuel estimates are: a per-aircraft model checked against 126 published "
             "fuel-burn figures, within about 5% on figures it never saw.",
    "silicon": "One block of HZN-1 built as a real SkyWater SKY130 chip layout: a Mode S CRC-24 checker tested on "
               "real ADS-B messages, which you can run in your browser.",
    "stats": "How much jet fuel is burning in the sky right now, which airlines and aircraft burn it, the last 24 "
             "hours, and what SAF, batteries, hybrids or hydrogen could save. Updated every hour.",
}


SHARED = ("analytics", "sound", "sitenav", "tour")  # scripts every page loads


def versioned(text):
    """Stamp the shared scripts' links with a hash of their contents, so browsers fetch them again only when they change."""
    for n in SHARED:
        text = text.replace(f"__V_{n}__", version(DOCS / "assets" / f"{n}.js"))
    return text


def stamp_landing():
    p = DOCS / "index.html"; s = p.read_text()
    for n in SHARED:
        s = re.sub(rf'src="assets/{n}\.js(\?v=[0-9a-f]+)?"', f'src="assets/{n}.js?v={version(DOCS / "assets" / f"{n}.js")}"', s)
    p.write_text(s)


def write(name, html):
    out = DOCS / name / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    d = DESCRIPTIONS[name].replace('"', "&quot;")
    img = {"globe": "og-globe.jpg", "stats": "og-stats.jpg"}.get(name, "og.jpg")  # share image for this page
    page = (f'<meta property="og:image" content="{SITE}assets/{img}">\n'
            f'<meta name="description" content="{d}">\n<meta property="og:description" content="{d}">\n'
            f'<link rel="canonical" href="{SITE}{name}/">\n<meta property="og:url" content="{SITE}{name}/">\n')
    out.write_text(versioned(HEAD) + page + localize(html))
    print(f"{out.relative_to(DOCS.parent)}  {out.stat().st_size / 1e3:.0f} kB")


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
#loading .pill{display:flex;align-items:center;gap:12px;padding:12px 18px;border-radius:999px;background:rgba(13,19,27,.82);border:1px solid rgba(255,255,255,.08);font:500 14px/1.2 Geist,system-ui,sans-serif;color:#e6edf5;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
#loading i{width:16px;height:16px;border-radius:50%;border:2px solid rgba(124,196,255,.25);border-top-color:#7cc4ff;animation:spin .8s linear infinite}
#loading.imagery{inset:auto 0 auto 0;top:calc(76px + env(safe-area-inset-top,0px));background:none;pointer-events:none}
#loading.done{opacity:0}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){#loading i{animation-duration:3s}}
</style>
<div id="loading" role="status" aria-live="polite"><div class="pill"><i aria-hidden="true"></i><span>Loading flights…</span></div></div>
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
    stamp_landing()


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
