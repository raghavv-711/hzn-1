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
    globals()["_frames"] = frames
    out.write_text(json.dumps({"frames": frames}, separators=(",", ":")))
    print(f"replay: {len(frames)} frames over {(frames[-1]['t'] - frames[0]['t']) / 3600:.1f} h, "
          f"{out.stat().st_size / 1e6:.1f} MB" if frames else "replay: no frames yet", flush=True)


def seats_for(icao):
    """Typical seats for an aircraft type, from the published figures the fuel model is tuned on (None if unknown)."""
    import fuel_model as M
    if icao in M.JETS:
        return M._seats(icao, M.JETS[icao][0])
    if icao in M.RATED:
        s = [r[3] for r in M.REFS if r[0] in M.RATED[icao][0]]
        return sum(s) / len(s) if s else None
    return None


def type_name(icao):
    import fuel_model as M
    names = (M.JETS.get(icao) or (None, []))[1] if icao in M.JETS else (M.RATED.get(icao) or ([],))[0]
    return names[0] if names else icao


def write_stats(rows, ap, airlines, t):
    """docs/stats/stats.json for the dashboard: totals now, the last 24 hours, rankings and per-flight scenario inputs."""
    from collections import Counter, defaultdict
    hav = build_site.hav
    burn = 0.0; modelled = 0; flights = []; al = defaultdict(lambda: {"n": 0, "burn": 0.0, "eff": []})
    routes, types, seat_cache = Counter(), Counter(), {}
    for r in rows:
        f = r[16] if len(r) > 16 else 0
        cs, typ, cls, o, de = r[1], r[2], r[9], r[11], r[12]
        if typ:
            types[typ] += 1
        if o in ap and de in ap:
            routes[(ap[o][0], ap[de][0])] += 1
        code = cs[:3] if re.match(r"^[A-Z]{3}\d", cs) and cs[:3] in airlines and airlines[cs[:3]][0] else None
        if code:
            al[code]["n"] += 1
        if not f:
            continue
        modelled += 1; burn += f[7]
        if code:
            al[code]["burn"] += f[7]
        if f[0] and o in ap and de in ap:
            D = hav(ap[o][2], ap[o][3], ap[de][2], ap[de][3])
            if typ not in seat_cache:
                seat_cache[typ] = seats_for(typ)
            seats = seat_cache[typ]
            trip = f[0] - f[2]                                 # taxi + trip, without reserves
            need = trip * 4190 / (f[6] * 0.9)                  # battery Wh/kg needed if the battery weighed as much as a full tank
            flights += [round(D), round(trip), round(need), cls, round(seats or 0)]
            if seats and D > 300 and code:
                al[code]["eff"].append(f[1] / D / seats * 3.16 * 1000)  # g CO2 per seat-km on this trip
    top_al = sorted(al.items(), key=lambda kv: -kv[1]["burn"])[:15]
    eff = sorted(((k, v) for k, v in al.items() if len(v["eff"]) >= 8), key=lambda kv: sum(kv[1]["eff"]) / len(kv[1]["eff"]))
    out = {
        "t": t, "n": len(rows), "modelled": modelled, "burn": round(burn),
        "history": [[fr["t"], fr["n"], fr["burn"], fr.get("modelled", 0)] for fr in globals().get("_frames", [])],
        "airlines": [[k, airlines[k][0], v["n"], round(v["burn"])] for k, v in top_al],
        "efficiency": [[k, airlines[k][0], len(v["eff"]), round(sum(v["eff"]) / len(v["eff"]), 1)] for k, v in eff],
        "routes": [[a, b, ap_name(ap, a), ap_name(ap, b), n] for (a, b), n in routes.most_common(10)],
        "types": [[k, type_name(k), n] for k, n in types.most_common(12)],
        "flights": flights,
    }
    p = ROOT / "docs" / "stats" / "stats.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(re.sub(r"\s*[–—]\s*", lambda m: " - " if m.group(0).strip() != m.group(0) else "-",
                        json.dumps(out, separators=(",", ":"), ensure_ascii=False)))
    print(f"stats: {len(flights) // 5:,} routed modelled flights, {len(eff)} airlines rated for efficiency", flush=True)


def ap_name(ap, iata):
    for v in ap.values():
        if v[0] == iata:
            return v[1]
    return iata


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
    js = re.sub(r"\s*[–—]\s*", lambda m: " - " if m.group(0).strip() != m.group(0) else "-", js)  # no en/em dashes in names on the site
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(js)
    save_frame(rows, payload["ap"], t)
    write_replay(t)
    write_stats(rows, payload["ap"], airlines, t)
    build_site.build(f.name)
    modelled = sum(1 for r in rows if len(r) > 16 and r[16])
    print(f"snapshot {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(t))}: {len(rows):,} flights, "
          f"{modelled:,} modelled by type, {len(trails):,} trails", flush=True)


if __name__ == "__main__":
    main()
