"""Build the public website's sub-pages in ../docs from the page sources in this folder.

    python3 site-src/build_site.py [path/to/fh-data.json]

Pages: docs/globe (Fuel Horizon snapshot), docs/chip (Inside HZN-1 explorer), docs/model (fuel model check).
The landing page (docs/index.html) and docs/assets are edited directly.
Passing a fresh fh-data.json (from the snapshot bundler) also refreshes the globe's recorded flights.
"""
import json, math, re, sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
DOCS = SRC.parent / "docs"

HEAD = ('<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<link rel="icon" href="../assets/favicon.svg" type="image/svg+xml">\n')
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


def write(name, html):
    out = DOCS / name / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEAD + localize(html))
    print(f"{out.relative_to(DOCS.parent)}  {out.stat().st_size / 1e3:.0f} kB")


def hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c); dl = math.radians(d - b)
    return 2 * 6371 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


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
        lat, lon, o, de, f = r[3], r[4], r[11], r[12], (r[16] if len(r) > 16 else 0)
        frac = -1
        if f and f[0] and o in ap and de in ap:
            D = hav(ap[o][2], ap[o][3], ap[de][2], ap[de][3]); flown = max(0, D - hav(lat, lon, ap[de][2], ap[de][3]))
            taxi = max(0, f[0] - f[1] - f[2]); x = f[4] * flown / max(f[3], 1e-6) if flown < f[3] else f[4] + (flown - f[3]) * f[5]
            frac = round(max(0, f[0] - taxi - min(x, f[1])) / f[0], 2)
        flights += [round(lat, 2), round(lon, 2), frac]
    out = {"land": land, "flights": flights, "t": d["t"], "n": len(d["p"]), "modelled": sum(1 for r in d["p"] if len(r) > 16 and r[16])}
    (DOCS / "assets" / "globe-points.json").write_text(json.dumps(out, separators=(",", ":")))


def build(data_json=None):
    # globe: data and imagery become separate files the browser can cache
    g = (SRC / "globe.html").read_text()
    g = rep(g, '<script type="application/json" id="fh">__DATA__</script>', '<script src="data.js"></script>')
    g = rep(g, '<script>const EARTH_WEST="data:image/jpeg;base64,__EARTH0__";</script>', '<script>const EARTH_WEST="earth-west.jpg";</script>')
    g = rep(g, '<script>const EARTH_EAST="data:image/jpeg;base64,__EARTH1__";</script>', '<script>const EARTH_EAST="earth-east.jpg";</script>')
    g = rep(g, "const DATA=JSON.parse(document.getElementById('fh').textContent);", "const DATA=window.FH_DATA;")
    g = re.sub(r'<div class="brand">(.*?)</div>', r'<a class="brand" href="../" style="pointer-events:auto;color:inherit;text-decoration:none" aria-label="HZN-1 home">\1</a>', g, count=1)
    write("globe", g)
    if data_json:
        (DOCS / "globe" / "data.js").write_text("window.FH_DATA=" + Path(data_json).read_text() + ";\n")
        globe_points(json.loads(Path(data_json).read_text()))
        print("refreshed docs/globe/data.js and docs/assets/globe-points.json")

    c = (SRC / "chip.html").read_text()
    c = rep(c, '<header class="top">\n  <div class="brand">', '<header class="top">\n  <a class="brand" href="../" style="color:inherit;text-decoration:none" aria-label="HZN-1 home">')
    c = rep(c, '<div><h1>Inside HZN-1</h1><p>A look inside the chip behind Fuel Horizon</p></div>\n  </div>',
            '<div><h1>Inside HZN-1</h1><p>A look inside the chip behind Fuel Horizon</p></div>\n  </a>')
    write("chip", c)

    m = (SRC / "model.html").read_text()
    m = rep(m, "__DATA__", (SRC / "model-data.json").read_text().replace("</", "<\\/"))
    m = rep(m, '<div class="eyebrow"><b>Fuel Horizon</b>', '<div class="eyebrow"><a href="../" style="text-decoration:none"><b>HZN-1</b></a><span>·</span><a href="../globe/" style="text-decoration:none"><b>Fuel Horizon</b></a>')
    write("model", m)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
