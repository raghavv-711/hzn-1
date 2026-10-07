"""Record a fresh snapshot of every airborne flight and rebuild the website's globe data.

    python3 tools/refresh_snapshot.py [--pulls 3] [--gap 240]

Pulls OpenSky's global feed a few times (a few minutes apart, so each plane gets a short trail), runs the
fuel model on every flight, and writes docs/globe/data.js and docs/assets/globe-points.json through
site-src/build_site.py. Recent paths are kept in .fuel-horizon-cache/history.json.gz between runs, so trails
grow longer when this runs on a schedule. Country, state, city and airport shapes live in docs/globe/static.js,
which this leaves alone since they don't change.

Exits with an error (leaving the site's data untouched) if OpenSky can't be reached or returns too few flights.
"""
import argparse, gzip, json, re, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "site-src"))
import fuel_horizon as F  # noqa: E402
import build_site  # noqa: E402

REPLAY_DIR = F.CACHE / "replay"   # one compact frame per run, kept between runs like the flight paths
REPLAY_HOURS = 24.5
REPLAY_MIN_GAP = 40 * 60      # pushes add extra frames; keep at most one per 40 minutes
MIN_FLIGHTS = 2000      # a healthy global pull has 5,000-10,000 airborne aircraft
TRAIL_KEEP = 7200       # seconds of path to ship with the snapshot
TRAIL_STEP = 180        # one trail point every 3 minutes keeps the file small


def compact_trails(encoded, hexes, now):
    """Server trails (delta-encoded t, lat*1e4, lon*1e4, ft) → thinned, coarser delta encoding for the globe."""
    out = {}
    for h, f in encoded.items():
        if h not in hexes:
            continue
        t = la = lo = al = 0; pts = []
        for i in range(0, len(f) - 3, 4):
            t += f[i]; la += f[i + 1]; lo += f[i + 2]; al += f[i + 3]; pts.append((t, la, lo, al))
        pts = [p for p in pts if now - p[0] <= TRAIL_KEEP]
        keep, last = [], -1e9
        for i, p in enumerate(pts):
            if p[0] - last >= TRAIL_STEP or i == len(pts) - 1:
                keep.append(p); last = p[0]
        if len(keep) < 2:
            continue
        flat, prev = [], None
        for p in keep:
            cur = (p[0], round(p[1] / 10), round(p[2] / 10), round(p[3] / 100))  # 0.001° and 100 ft steps
            flat.extend(cur if prev is None else [c - q for c, q in zip(cur, prev)]); prev = cur
        out[h] = flat
    return out


def save_frame(rows, ap, t):
    """Store this snapshot as a replay frame: per plane hex, position, height, heading and fuel left, plus totals."""
    hexes, vals, burn, modelled = [], [], 0.0, 0
    for r in rows:
        f = r[16] if len(r) > 16 else 0
        if f:
            modelled += 1; burn += f[7]
        hexes.append(r[0])
        frac = build_site.fuel_frac(r, ap)
        vals += [round(r[3] * 100), round(r[4] * 100), round(r[5] / 100), round(r[7] or 0), -1 if frac < 0 else round(frac * 100)]
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    frame = {"t": t, "n": len(rows), "modelled": modelled, "burn": round(burn), "h": hexes, "v": vals}
    with gzip.open(REPLAY_DIR / f"{t}.json.gz", "wt") as fh:
        json.dump(frame, fh, separators=(",", ":"))


def write_replay(now):
    """Combine the last day's frames into docs/globe/replay.json (newest wins when two are close together)."""
    files = sorted(REPLAY_DIR.glob("*.json.gz"), key=lambda p: -int(p.name.split(".")[0])) if REPLAY_DIR.exists() else []
    keep, last = [], None
    for p in files:
        t = int(p.name.split(".")[0])
        if now - t > REPLAY_HOURS * 3600:
            p.unlink(); continue
        if last is not None and last - t < REPLAY_MIN_GAP:
            p.unlink(); continue
        keep.append(p); last = t
    frames = []
    for p in reversed(keep):
        with gzip.open(p, "rt") as fh:
            frames.append(json.load(fh))
    out = ROOT / "docs" / "globe" / "replay.json"
    out.write_text(json.dumps({"frames": frames}, separators=(",", ":")))
    print(f"replay: {len(frames)} frames over {(frames[-1]['t'] - frames[0]['t']) / 3600:.1f} h, "
          f"{out.stat().st_size / 1e6:.1f} MB" if frames else "replay: no frames yet", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pulls", type=int, default=3, help="global pulls to make (4 OpenSky credits each)")
    ap.add_argument("--gap", type=float, default=240, help="seconds between pulls")
    args = ap.parse_args()

    F.ensure_static()
    routes, airports, types, aircraft, airlines = F.load_static()
    if F.FuelModel is not None:
        F.FUEL = F.FuelModel()
        print("fuel model: OpenAP, calibrated", flush=True)
    else:
        print("fuel model: OpenAP not installed, using the simple model", flush=True)
    live = F.Live(F.Matcher(routes, airports, types))
    print(f"restored recent paths for {live.load_history():,} aircraft", flush=True)

    got = 0
    for i in range(args.pulls):
        if i:
            time.sleep(args.gap)
        before = live.global_t
        live.pull_global()
        if live.global_t != before:
            got += 1
    rows, t = live.global_rows, live.global_t
    live.save_history()
    if not got or len(rows) < MIN_FLIGHTS:
        sys.exit(f"refresh failed: {got} successful pulls, {len(rows)} flights. {live.global_note}")

    payload = live.payload(rows, {})
    hexes = {r[0] for r in rows}
    trails = compact_trails(live.trails(None, None, None, 60), hexes, t)
    info = {r[0]: aircraft[r[0]].split("\t") for r in rows if r[0] in aircraft}
    als = {r[1][:3]: list(airlines[r[1][:3]]) for r in rows
           if re.match(r"^[A-Z]{3}\d", r[1]) and r[1][:3] in airlines and airlines[r[1][:3]][0]}

    # country/state/city shapes and place names don't change, so they stay in docs/globe/static.js
    data = {"t": t, "ap": payload["ap"], "p": rows, "trails": trails, "info": info, "airlines": als}
    js = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(js)
    save_frame(rows, payload["ap"], t)
    write_replay(t)
    build_site.build(f.name)
    modelled = sum(1 for r in rows if len(r) > 16 and r[16])
    print(f"snapshot {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(t))}: {len(rows):,} flights, "
          f"{modelled:,} modelled by type, {len(trails):,} trails", flush=True)


if __name__ == "__main__":
    main()
