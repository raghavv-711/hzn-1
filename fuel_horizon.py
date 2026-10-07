#!/usr/bin/env python3
"""Fuel Horizon live server.

Polls live ADS-B traffic, matches each flight to its route and aircraft class,
and serves the 3D globe at http://localhost:8765.

  python3 fuel_horizon.py

Sources
  - OpenSky Network /states/all: every aircraft worldwide. Anonymous use allows
    ~100 global pulls a day; the poll interval adapts to the credits left.
    For ~10x more, create a free OpenSky API client and set
    OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET.
  - adsb.lol /v2/point: the 250 nm around wherever the globe is pointed,
    refreshed every few seconds.
  - VRS standing data (routes, airports), the ADS-B Exchange basic aircraft
    database (types) and Natural Earth countries and cities, downloaded once into
    .fuel-horizon-cache/.

Standard library only.
"""
import csv, gzip, json, math, os, re, signal, sys, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:  # per-aircraft fuel model (needs `pip install openap`); without it the page falls back to its simple model
    from fuel_model import FuelModel
except Exception:
    FuelModel = None
FUEL = None  # loaded in the background at startup

PORT = int(os.environ.get("PORT", "8765"))
HERE = Path(__file__).resolve().parent
CACHE = HERE / ".fuel-horizon-cache"
PAGE = HERE / "fuel_horizon.html"
UA = {"User-Agent": "fuel-horizon/1.0 (student project)"}
OPENSKY_URL = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
REGION_URL = "https://api.adsb.lol/v2/point/{lat:.1f}/{lon:.1f}/250"
TRACE_URL = "https://adsb.lol/data/traces/{tail}/trace_full_{hex}.json"
TRAIL_SECONDS = 2 * 3600  # how much recent path the server remembers per aircraft
HISTORY_SAVE_EVERY = 600  # seconds; history is saved to disk so restarts keep the trails
REGION_MIN_GAP = 6.0      # seconds between adsb.lol calls
GLOBAL_MIN_GAP = 10.0     # OpenSky's best time resolution for anonymous users
STATIC = {
    "routes.csv.gz": "https://vrs-standing-data.adsb.lol/routes.csv.gz",
    "airports.csv.gz": "https://vrs-standing-data.adsb.lol/airports.csv.gz",
    "basic-ac-db.json.gz": "https://downloads.adsbexchange.com/downloads/basic-ac-db.json.gz",
    "countries-50m.json": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json",
    "places-50m.geojson": "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_50m_populated_places_simple.geojson",
    "airlines.dat": "https://cdn.jsdelivr.net/gh/jpatokal/openflights@master/data/airlines.dat",
    "admin1-50m.geojson": "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_50m_admin_1_states_provinces.geojson",
}

PLACES = b"[]"  # filled in main()
HISTORY_FILE = CACHE / "history.json.gz"
AIRCRAFT, AIRLINES = {}, {}  # filled in main(): hex -> registration etc., ICAO airline code -> (name, country)

def compact_places():
    """Natural Earth cities as [name, lat, lon, scalerank, population, is_capital]."""
    d = json.loads((CACHE / "places-50m.geojson").read_text())
    out = []
    for f in d["features"]:
        p, (lon, lat) = f["properties"], f["geometry"]["coordinates"][:2]
        out.append([p.get("name") or "", round(lat, 3), round(lon, 3), int(p["scalerank"] if p.get("scalerank") is not None else 10),
                    int(p.get("pop_max") or 0), int(p.get("adm0cap") or 0)])
    out.sort(key=lambda r: (r[3], -r[4]))
    return json.dumps(out, separators=(",", ":")).encode()

# ---------------------------------------------------------------- reference data
def fetch(url, timeout=30, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)

def ensure_static():
    CACHE.mkdir(exist_ok=True)
    for name, url in STATIC.items():
        f = CACHE / name
        if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
            continue
        print(f"  downloading {name} …", flush=True)
        with fetch(url, timeout=120) as r:
            f.write_bytes(r.read())

def load_static():
    routes = {}
    with gzip.open(CACHE / "routes.csv.gz", "rt", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            routes[r["Callsign"]] = r["AirportCodes"].split("-")
    airports = {}
    with gzip.open(CACHE / "airports.csv.gz", "rt", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                airports[r["Code"]] = [r["IATA"] or r["ICAO"] or r["Code"], r["Location"] or r["Name"],
                                       round(float(r["Latitude"]), 3), round(float(r["Longitude"]), 3)]
            except ValueError:
                pass
    types, aircraft = {}, {}
    with gzip.open(CACHE / "basic-ac-db.json.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("icaotype"):
                types[r["icao"]] = r["icaotype"]
            model = " ".join(x for x in (r.get("manufacturer"), r.get("model")) if x)
            if r.get("reg") or model or r.get("ownop"):
                # "registration<TAB>model<TAB>owner/operator<TAB>year<TAB>military" as one string keeps 600k entries small
                aircraft[r["icao"]] = "\t".join((r.get("reg") or "", model, r.get("ownop") or "", str(r.get("year") or ""), "1" if r.get("mil") else ""))
    airlines = {}
    with open(CACHE / "airlines.dat", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) >= 7 and len(row[4]) == 3 and row[4] != "\\N":
                name = row[1] if row[1] != "\\N" else ""
                if row[4] not in airlines or row[7:8] == ["Y"]:  # prefer active airlines on duplicate codes
                    airlines[row[4]] = (name, row[6] if row[6] != "\\N" else "", row[3] if len(row[3]) == 2 else "")
    return routes, airports, types, aircraft, airlines

# ---------------------------------------------------------------- classification
CLASS_TYPES = {
    0: "B77W B77L B773 B744 B748 B74F A388 A35K AN124 C5M B742 B743",
    1: "B772 B788 B789 B78X A332 A333 A338 A339 A359 B762 B763 B764 A306 A30B A310 MD11 DC10 C17 K35R KC46 A400 A3ST B77F",
    2: "A318 A319 A320 A321 A19N A20N A21N B731 B732 B733 B734 B735 B736 B737 B738 B739 B37M B38M B39M B3XM B752 B753 B712 MD81 MD82 MD83 MD87 MD88 MD90 C919 BCS3 P8",
    3: "E75L E75S E170 E190 E195 E290 E295 CRJ1 CRJ2 CRJ7 CRJ9 CRJX E135 E145 E45X BCS1 F100 RJ85 RJ1H SU95 AJ27 F70",
    4: "DH8A DH8B DH8C DH8D AT43 AT45 AT72 AT75 AT76 PC12 B350 BE20 BE9L BE99 BE30 C208 SF34 JS41 D328 C130 C30J P180 TBM7 TBM8 TBM9 SW4 TEX2 PC21 DHC6 L410 C441 PAY2 PAY3 AN26 M600 PA46 KODI E120 B190",
    5: "C25A C25B C25C C25M C510 C525 C550 C560 C56X C650 C680 C68A C700 C750 CL30 CL35 CL60 GLF4 GLF5 GLF6 GL5T GL7T GLEX G280 E50P E55P E545 E550 LJ35 LJ40 LJ45 LJ60 LJ75 F2TH F900 FA7X FA8X FA50 H25B PC24 HDJT SF50 GALX BE40 PRM1 C501 C551 E35L ASTR",
    6: "C150 C152 C162 C170 C172 C177 C180 C182 C185 C195 C206 C207 C210 P28A P28B P28R P28T P32R P32T PA32 PA24 PA28 PA30 PA31 PA34 PA44 SR20 SR22 S22T DA40 DA42 DA62 DA20 DV20 M20P M20T BE33 BE35 BE36 BE58 BE55 BE76 BE23 AA5 AA1 C340 C310 C414 C421 RV7 RV8 RV6 RV10 RV14 RV9 RV12 GLAS J3 CH7A AT3 TOBA P210 G115 C77R C140 BL8 LA4 PA22 PA18 PA12 PA38 GA8 VL3 R200 EV97 DR40",
    7: "EC45 EC35 EC30 EC55 EC75 EC20 EC25 B407 B06 B429 B412 B427 B505 H60 H47 H64 AS50 AS55 AS65 AS32 A109 A119 A139 A169 A149 A189 R44 R22 R66 S76 S92 H125 H130 H135 H145 H160 MD52 MD60 EH10 NH90 B212 UH1 V22 S70 A129 BK17 EXPL CABR",
}
TYPE_CLASS = {}
for c, codes in CLASS_TYPES.items():
    for t in codes.split():
        TYPE_CLASS.setdefault(t, c)
CATEGORY_CLASS = {"A1": 6, "A2": 4, "A3": 2, "A4": 2, "A5": 1, "A6": 5, "A7": 7}
AIRLINE = re.compile(r"^[A-Z]{3}\d")

def hav(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(min(1, math.sqrt(h)))

def bearing(a, b, c, d):
    p1, p2, dl = math.radians(a), math.radians(c), math.radians(d - b)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

class Matcher:
    def __init__(self, routes, airports, types):
        self.routes, self.airports, self.types = routes, airports, types

    def route(self, cs, lat, lon, trk):
        """Pick the leg of the callsign's route that fits the aircraft's position and heading."""
        if not AIRLINE.match(cs) or cs not in self.routes:
            return None
        codes = [c for c in self.routes[cs] if c in self.airports]
        best = None
        for a, b in zip(codes, codes[1:]):
            A, B = self.airports[a], self.airports[b]
            leg = hav(A[2], A[3], B[2], B[3])
            d1, d2 = hav(A[2], A[3], lat, lon), hav(lat, lon, B[2], B[3])
            if leg <= 50 or d1 + d2 > leg * 1.12 + 120:
                continue
            if d2 > 150 and trk is not None and abs((bearing(lat, lon, B[2], B[3]) - trk + 540) % 360 - 180) > 50:
                continue
            if best is None or d1 + d2 - leg < best[0]:
                best = (d1 + d2 - leg, a, b, leg)
        return best

    def row(self, hexid, cs, lat, lon, alt_ft, gs, trk, vr_fpm, category, country, tpos, type_hint=None, squawk=""):
        cs = (cs or "").strip()
        t = type_hint or self.types.get(hexid, "")
        cls = TYPE_CLASS.get(t)
        if cls is None and category in CATEGORY_CLASS:
            cls = CATEGORY_CLASS[category]
        inferred = cls is None
        r = self.route(cs, lat, lon, trk)
        D = r[3] if r else 0
        if cls is None:
            if AIRLINE.match(cs):
                cls = 1 if D > 5500 else 4 if (8000 < alt_ft < 26000 and gs < 330) else 2
            else:
                cls = 6 if (alt_ft < 12000 and gs < 170) else 5 if alt_ft > 30000 else 4
        fuel = 0
        if FUEL and t:
            try:
                if r:
                    dest = self.airports[r[2]]
                    fuel = FUEL.estimate(t, D, max(0.0, D - hav(lat, lon, dest[2], dest[3])), alt_ft, gs, vr_fpm or 0) or 0
                else:
                    fuel = FUEL.estimate(t, None, None, alt_ft, gs, vr_fpm or 0) or 0
            except Exception:
                fuel = 0
        return [hexid, cs or hexid.upper(), t, round(lat, 4), round(lon, 4), int(alt_ft), int(gs),
                round(trk or 0, 1), int(vr_fpm or 0), cls, int(inferred),
                r[1] if r else "", r[2] if r else "", (country or "")[:24], int(tpos * 1000), squawk or "", fuel]

# ---------------------------------------------------------------- live feeds
class Live:
    def __init__(self, matcher):
        self.m = matcher
        self.lock = threading.Lock()
        self.global_rows, self.global_t, self.global_note = [], 0, "Waiting for first OpenSky pull"
        self.credits = None
        self.region = {"rows": [], "t": 0, "center": None, "note": ""}
        self.region_next = 0.0
        self.region_want, self.region_asked = None, 0.0
        self.region_fails = 0
        self.history = {}       # hex -> [[t, lat, lon, alt_ft], ...] from every report we've seen
        self.traces = {}        # hex -> (fetched_at, points) for selected aircraft
        self.saved_at = time.time()
        self.wake = threading.Event()  # set to pull the whole globe right away
        self.token, self.token_exp = None, 0
        self.auth_off = False   # set when OpenSky rejects the account, so pulls carry on anonymously

    # OpenSky ----------------------------------------------------------
    def auth_header(self):
        cid, sec = (os.environ.get("OPENSKY_CLIENT_ID") or "").strip(), (os.environ.get("OPENSKY_CLIENT_SECRET") or "").strip()
        if not (cid and sec) or self.auth_off:
            return {}
        if time.time() > self.token_exp - 60:
            body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}).encode()
            try:
                with fetch(OPENSKY_TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}) as r:
                    tok = json.load(r)
            except urllib.error.HTTPError as e:
                detail = e.read(300).decode("utf-8", "replace") if e.fp else ""
                print(f"[opensky] sign-in with the API client was rejected (HTTP {e.code}) {detail.strip()}; continuing anonymously", flush=True)
                self.auth_off = True
                return {}
            self.token, self.token_exp = tok["access_token"], time.time() + tok.get("expires_in", 1800)
            print("[opensky] signed in with the API client", flush=True)
        return {"Authorization": "Bearer " + self.token}

    def next_interval(self):
        """Spread the remaining daily credits (4 per global pull) until the next UTC midnight."""
        if self.credits is None:
            return 60.0
        pulls_left = max(0, self.credits // 4 - 1)
        if pulls_left == 0:
            return 900.0
        to_midnight = 86400 - (time.time() % 86400)
        return max(GLOBAL_MIN_GAP, to_midnight / pulls_left)

    def poll_global_forever(self):
        while True:
            wait = self.pull_global()
            self.wake.wait(min(wait, 900.0))
            self.wake.clear()

    def pull_global(self):
        """One OpenSky pull of every airborne aircraft; returns how long to wait before the next one."""
        wait = self.next_interval()
        try:
            with fetch(OPENSKY_URL, timeout=60, headers=self.auth_header()) as r:
                rem = r.headers.get("X-Rate-Limit-Remaining")
                self.credits = int(rem) if rem and rem.isdigit() else self.credits
                data = json.load(r)
            rows = []
            for s in data.get("states") or []:
                hexid, cs, country, tpos, lastc, lon, lat, balt, ground, vel, trk, vr, _, galt = s[:14]
                cat = s[17] if len(s) > 17 else None
                alt = balt if balt is not None else galt
                if ground or lat is None or lon is None or vel is None or alt is None or vel < 20:
                    continue
                if data["time"] - (tpos or lastc or 0) > 120:
                    continue
                category = "A%d" % (cat - 1) if isinstance(cat, int) and 2 <= cat <= 8 else ""
                rows.append(self.m.row(hexid, cs, lat, lon, alt * 3.28084, vel * 1.94384, trk,
                                       (vr or 0) * 196.85, category, country, tpos or lastc, squawk=s[14]))
            self.remember(rows)
            self.prune_history()
            if time.time() - self.saved_at > HISTORY_SAVE_EVERY:
                try:
                    self.save_history()
                except OSError as e:
                    print("[history] couldn't save:", e, flush=True)
            with self.lock:
                self.global_rows, self.global_t = rows, data["time"]
                self.global_note = ""
            wait = self.next_interval()
            print(f"[opensky] {len(rows)} airborne · credits left {self.credits} · next pull in {wait:.0f}s", flush=True)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and self.token and not self.auth_off:
                print(f"[opensky] the API client was refused (HTTP {e.code}); retrying anonymously", flush=True)
                self.auth_off = True
                return self.pull_global()
            if e.code == 429:
                retry = e.headers.get("X-Rate-Limit-Retry-After-Seconds")
                wait = float(retry) if retry and retry.isdigit() else 1800.0
                self.credits = 0
                note = "OpenSky daily quota used up. Global refresh resumes in %d min; your focus region stays live." % (wait // 60)
            else:
                note, wait = "OpenSky returned HTTP %d. Retrying." % e.code, 60.0
            with self.lock:
                self.global_note = note
            print("[opensky]", note, flush=True)
        except Exception as e:
            with self.lock:
                self.global_note = "OpenSky unreachable. Retrying."
            print("[opensky] error:", e, flush=True)
            wait = 60.0
        return wait

    # adsb.lol focus region ---------------------------------------------
    def want_region(self, lat, lon):
        """Record where the globe is pointed; the region thread fetches it in the background."""
        with self.lock:
            self.region_want = (max(-85.0, min(85.0, lat)), ((lon + 180) % 360) - 180)
            self.region_asked = time.time()

    def poll_region_forever(self):
        while True:
            time.sleep(0.5)
            with self.lock:
                want, asked, ready = self.region_want, self.region_asked, time.time() >= self.region_next
            if want and ready and time.time() - asked < 30:  # stop polling when no page is open
                self.poll_region(*want)

    def poll_region(self, lat, lon):
        now = time.time()
        with self.lock:
            self.region_next = now + REGION_MIN_GAP
        try:
            with fetch(REGION_URL.format(lat=lat, lon=lon), timeout=15) as r:
                d = json.load(r)
            rows = []
            for a in d.get("ac", []):
                alt = a.get("alt_baro")
                if a.get("lat") is None or a.get("gs") is None or not isinstance(alt, (int, float)):
                    continue  # alt_baro is "ground" for taxiing aircraft
                if a.get("seen_pos", 99) > 60 or a["gs"] < 40:
                    continue
                tpos = d.get("now", now * 1000) / 1000 - a.get("seen_pos", 0)
                rows.append(self.m.row(a["hex"], a.get("flight"), a["lat"], a["lon"], alt, a["gs"], a.get("track"),
                                       a.get("baro_rate") or a.get("geom_rate") or 0, a.get("category", ""), "", tpos,
                                       type_hint=a.get("t"), squawk=a.get("squawk")))
            self.remember(rows)
            with self.lock:
                self.region = {"rows": rows, "t": now, "center": [round(lat, 2), round(lon, 2)], "note": ""}
                self.region_fails = 0
            if now - getattr(self, "region_logged", 0) > 60:
                self.region_logged = now
                print(f"[adsb.lol] {len(rows)} aircraft around {lat:.1f}, {lon:.1f} (logged once a minute)", flush=True)
        except urllib.error.HTTPError as e:
            with self.lock:
                self.region_fails += 1
                self.region_next = now + (10 if e.code == 429 else 15)
                if self.region_fails >= 3:  # an occasional 429 is normal; only surface a streak
                    self.region["note"] = "adsb.lol is rate-limiting, so the focus area is refreshing slowly." if e.code == 429 else "adsb.lol returned HTTP %d." % e.code
            if self.region_fails >= 3:
                print("[adsb.lol] HTTP", e.code, flush=True)
        except Exception as e:
            with self.lock:
                self.region_fails += 1
                self.region_next = now + 15
                if self.region_fails >= 3:
                    self.region["note"] = "adsb.lol is unreachable, so the focus area isn't refreshing."
            print("[adsb.lol] error:", e, flush=True)

    # trails --------------------------------------------------------
    def remember(self, rows):
        """Append each report to that aircraft's recent path (rows are already-processed feed rows)."""
        cutoff = time.time() - TRAIL_SECONDS
        with self.lock:
            for r in rows:
                t = r[14] / 1000
                h = self.history.setdefault(r[0], [])
                if not h or t > h[-1][0] + 15:
                    h.append([round(t), r[3], r[4], r[5]])
                    while h and h[0][0] < cutoff:
                        h.pop(0)

    def prune_history(self):
        cutoff = time.time() - TRAIL_SECONDS
        with self.lock:
            for k in [k for k, h in self.history.items() if not h or h[-1][0] < cutoff]:
                del self.history[k]

    def trails(self, lat, lon, radius_km, thin):
        """Recent paths of aircraft within radius_km (None = everywhere), one point per `thin` seconds.
        Each path is a flat, delta-encoded int list: t, lat*1e4, lon*1e4, alt_ft, then differences."""
        out = {}
        with self.lock:
            items = [(k, list(h)) for k, h in self.history.items()]
        for hexid, h in items:
            if len(h) < 2 or (radius_km is not None and hav(lat, lon, h[-1][1], h[-1][2]) > radius_km):
                continue
            flat, last, prev = [], -1e9, None
            for t, la, lo, alt in h:
                if t - last < thin and t != h[-1][0]:
                    continue
                last, cur = t, (int(t), round(la * 1e4), round(lo * 1e4), int(alt))
                flat.extend(cur if prev is None else (c - q for c, q in zip(cur, prev)))
                prev = cur
            if len(flat) >= 8:
                out[hexid] = flat
        return out

    def save_history(self):
        with self.lock:
            data = {k: list(h) for k, h in self.history.items()}
        tmp = HISTORY_FILE.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as f:
            json.dump(data, f, separators=(",", ":"))
        tmp.replace(HISTORY_FILE)
        self.saved_at = time.time()

    def load_history(self):
        try:
            with gzip.open(HISTORY_FILE, "rt") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return 0
        cutoff = time.time() - TRAIL_SECONDS
        self.history = {k: [p for p in h if p[0] >= cutoff] for k, h in data.items()}
        self.history = {k: h for k, h in self.history.items() if h}
        return len(self.history)

    def trace(self, hexid):
        """The selected aircraft's actual path since takeoff, from adsb.lol's daily trace file."""
        hexid = hexid.lower()
        cached = self.traces.get(hexid)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        with fetch(TRACE_URL.format(tail=hexid[-2:], hex=hexid), timeout=20,
                   headers={"Referer": "https://adsb.lol/", "Accept-Encoding": "gzip"}) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
        d = json.loads(raw)
        base, pts = d.get("timestamp", 0), []
        for p in d.get("trace", []):
            t, lat, lon, alt = base + p[0], p[1], p[2], p[3]
            if lat is None or lon is None:
                continue
            on_ground = alt == "ground"
            # a new flight starts after the aircraft was on the ground, or after a long gap that begins or ends
            # low (oceanic coverage gaps at cruise altitude are part of the same flight)
            low = isinstance(alt, (int, float)) and alt < 10000
            if on_ground or (pts and t - pts[-1][3] > 45 * 60 and (low or pts[-1][2] < 10000)):
                pts = []
            if not on_ground and isinstance(alt, (int, float)):
                pts.append([round(lat, 5), round(lon, 5), int(alt), round(t)])
        self.traces[hexid] = (time.time(), pts)
        return pts

    def payload(self, rows, extra):
        aps = {}
        for r in rows:
            for code in (r[11], r[12]):
                if code and code not in aps:
                    aps[code] = self.m.airports[code]
        return {**extra, "ap": aps, "p": rows}

# ---------------------------------------------------------------- areas (isolate a country, state, city or airport)
def _unwrap(ring):
    """Make longitudes continuous so rings crossing the antimeridian stay in one piece (Antarctica excepted)."""
    if min(p[1] for p in ring) < -85:
        return [[round(p[0], 4), round(p[1], 4)] for p in ring]
    out = [[round(ring[0][0], 4), round(ring[0][1], 4)]]
    for lon, lat in ring[1:]:
        prev = out[-1][0]
        while lon - prev > 180: lon -= 360
        while lon - prev < -180: lon += 360
        out.append([round(lon, 4), round(lat, 4)])
    return out

class Areas:
    KIND_RANK = {"Country": 0, "State": 1, "City": 2, "Airport": 3}

    def __init__(self):
        self.index, self.shapes, self.circles = [], {}, {}
        # countries (TopoJSON)
        topo = json.loads((CACHE / "countries-50m.json").read_text())
        (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
        arcs = []
        for a in topo["arcs"]:
            x = y = 0; pts = []
            for dx, dy in a:
                x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
            arcs.append(pts)
        def ring(idx):
            out = []
            for i in idx:
                pts = arcs[i] if i >= 0 else arcs[~i][::-1]
                out.extend(pts if not out else pts[1:])
            return out
        for g in topo["objects"]["countries"]["geometries"]:
            name = (g.get("properties") or {}).get("name") or ""
            polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"] if g["type"] == "MultiPolygon" else []
            if name and polys:
                self._add_shape("country:" + name, "Country", name, "", [[ring(r) for r in poly] for poly in polys], 0)
        # states and provinces (GeoJSON; Natural Earth 50m covers 9 large countries)
        for f in json.loads((CACHE / "admin1-50m.geojson").read_text())["features"]:
            pr, gm = f["properties"], f["geometry"]
            if not gm or not pr.get("name"):
                continue
            polys = [gm["coordinates"]] if gm["type"] == "Polygon" else gm["coordinates"]
            kind = (pr.get("type_en") or "State")
            self._add_shape("state:%s|%s" % (pr.get("admin"), pr["name"]), "State", pr["name"],
                            "%s, %s" % (kind, pr.get("admin") or ""), polys, 0)
        # cities
        for i, f in enumerate(json.loads((CACHE / "places-50m.geojson").read_text())["features"]):
            pr, (lon, lat) = f["properties"], f["geometry"]["coordinates"][:2]
            if not pr.get("name"):
                continue
            pop = int(pr.get("pop_max") or 0)
            detail = ", ".join(x for x in (pr.get("adm1name"), pr.get("adm0name")) if x and x != pr["name"])
            self._add_circle("city:%d" % i, "City", pr["name"], detail, lat, lon, 100 if pop > 3e6 else 60, pop)
        # airports with an IATA code
        with gzip.open(CACHE / "airports.csv.gz", "rt", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if len(r["IATA"]) != 3:
                    continue
                try:
                    lat, lon = float(r["Latitude"]), float(r["Longitude"])
                except ValueError:
                    continue
                detail = ", ".join(x for x in (r["Location"], r["CountryISO2"]) if x)
                self._add_circle("airport:" + r["IATA"], "Airport", "%s · %s" % (r["IATA"], r["Name"]), detail, lat, lon, 40, 0, alt=r["IATA"])

    def _add_shape(self, aid, kind, name, detail, polys, pop):
        self.shapes[aid] = (kind, name, detail, polys)
        self.index.append((name.lower(), aid, kind, name, detail, pop, ""))

    def _add_circle(self, aid, kind, name, detail, lat, lon, radius, pop, alt=""):
        self.circles[aid] = (kind, name, detail, lat, lon, radius)
        self.index.append((name.lower(), aid, kind, name, detail, pop, alt.lower()))

    def search(self, q, limit=8):
        q = q.strip().lower()
        if len(q) < 2:
            return []
        hits = []
        for low, aid, kind, name, detail, pop, alt in self.index:
            if alt and alt == q: score = 0                          # exact airport code
            elif low == q: score = 0
            elif low.startswith(q): score = 1
            elif any(w.startswith(q) for w in re.split(r"[\s,·()-]+", low)): score = 2
            else: continue
            hits.append((score, self.KIND_RANK[kind], -pop, len(name), aid, kind, name, detail))
        hits.sort()
        return [{"id": h[4], "kind": h[5], "name": h[6], "detail": h[7]} for h in hits[:limit]]

    def area(self, aid):
        if aid in self.circles:
            kind, name, detail, lat, lon, radius = self.circles[aid]
            return {"id": aid, "kind": kind, "name": name, "detail": detail, "center": [lat, lon], "radius": radius, "extent": radius}
        if aid not in self.shapes:
            return None
        kind, name, detail, polys = self.shapes[aid]
        rings = [[_unwrap(r) for r in poly] for poly in polys]
        # center and extent from the largest polygon, so far-flung islands don't throw off the camera
        def area_of(r): return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]))) / 2
        main = max(rings, key=lambda poly: area_of(poly[0]))[0]
        a = cx = cy = 0
        for (x0, y0), (x1, y1) in zip(main, main[1:] + main[:1]):
            f = x0 * y1 - x1 * y0; a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
        lat, lon = (cy / (3 * a), cx / (3 * a)) if abs(a) > 1e-9 else (main[0][1], main[0][0])
        lon = (lon + 180) % 360 - 180
        extent = max(hav(lat, lon, y, x) for x, y in main[::max(1, len(main) // 400)])
        return {"id": aid, "kind": kind, "name": name, "detail": detail, "center": [round(lat, 4), round(lon, 4)],
                "extent": round(extent), "polys": rings}

AREAS = None  # built in main()

# ---------------------------------------------------------------- HTTP
def make_handler(live):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if "gzip" in self.headers.get("Accept-Encoding", "") and len(body) > 2048:
                body = gzip.compress(body, 5)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/countries.json":
                return self.send(200, (CACHE / "countries-50m.json").read_bytes(), "application/json")
            if u.path == "/places.json":
                return self.send(200, PLACES, "application/json")
            if u.path == "/api/global":
                since = int(q.get("since", ["0"])[0] or 0)
                with live.lock:
                    rows, t, note, credits = live.global_rows, live.global_t, live.global_note, live.credits
                meta = {"t": t, "note": note, "credits": credits, "next": round(live.next_interval())}
                body = meta if (t and t == since) else live.payload(rows, meta)
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            if u.path == "/api/trails":
                if q.get("all"):
                    body = live.trails(0, 0, None, thin=60)
                else:
                    try:
                        lat, lon, r = float(q["lat"][0]), float(q["lon"][0]), float(q.get("r", ["800"])[0])
                    except (KeyError, ValueError):
                        return self.send(400, b'{"error":"lat and lon are required"}', "application/json")
                    body = live.trails(lat, lon, min(r, 4000), thin=20)
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            if u.path == "/api/pull-now":  # local only (the server listens on 127.0.0.1); used for scheduled snapshots
                live.wake.set()
                return self.send(200, b'{"ok":true}', "application/json")
            if u.path == "/api/places":
                body = AREAS.search(q.get("q", [""])[0])
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            if u.path == "/api/area":
                body = AREAS.area(q.get("id", [""])[0])
                if body is None:
                    return self.send(404, b'{"error":"unknown area"}', "application/json")
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            if u.path == "/api/flight":
                hexid = re.sub(r"[^0-9a-fA-F]", "", q.get("hex", [""])[0])[:6].lower()
                cs = q.get("cs", [""])[0].strip().upper()
                ac = AIRCRAFT.get(hexid)
                ac = ac.split("\t") if ac else None
                al = AIRLINES.get(cs[:3]) if re.match(r"^[A-Z]{3}\d", cs) else None
                body = {"hex": hexid,
                        "aircraft": {"reg": ac[0], "model": ac[1], "operator": ac[2], "year": ac[3], "mil": ac[4] == "1"} if ac else None,
                        "airline": {"name": al[0], "country": al[1]} if al and al[0] else None}
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            if u.path == "/api/trace":
                hexid = re.sub(r"[^0-9a-fA-F]", "", q.get("hex", [""])[0])[:6]
                if len(hexid) != 6:
                    return self.send(400, b'{"error":"hex is required"}', "application/json")
                try:
                    body = {"hex": hexid, "points": live.trace(hexid)}
                except urllib.error.HTTPError as e:
                    body = {"hex": hexid, "points": [], "note": "adsb.lol has no trace for this aircraft (HTTP %d)." % e.code}
                except Exception:
                    body = {"hex": hexid, "points": [], "note": "Couldn't reach adsb.lol for this aircraft's path."}
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            if u.path == "/api/region":
                try:
                    lat, lon = float(q["lat"][0]), float(q["lon"][0])
                except (KeyError, ValueError):
                    return self.send(400, b'{"error":"lat and lon are required"}', "application/json")
                live.want_region(lat, lon)
                with live.lock:
                    reg = dict(live.region)
                body = live.payload(reg.pop("rows"), reg)
                return self.send(200, json.dumps(body, separators=(",", ":")).encode(), "application/json")
            self.send(404, b"Not found", "text/plain")
    return H

def main():
    print("Fuel Horizon — preparing reference data (first run downloads ~20 MB)")
    ensure_static()
    routes, airports, types, aircraft, airlines = load_static()
    global AIRCRAFT, AIRLINES, AREAS
    AIRCRAFT, AIRLINES = aircraft, airlines
    AREAS = Areas()
    global PLACES
    PLACES = compact_places()
    print(f"  {len(routes):,} routes · {len(airports):,} airports · {len(types):,} aircraft types")
    live = Live(Matcher(routes, airports, types))
    n = live.load_history()
    if n:
        print(f"  restored recent paths for {n:,} aircraft")
    if os.environ.get("OPENSKY_CLIENT_ID"):
        print("  OpenSky: using API client credentials")
    else:
        print("  OpenSky: anonymous (about 100 global pulls a day; set OPENSKY_CLIENT_ID/SECRET for more)")
    def load_fuel():
        global FUEL
        if FuelModel is None:
            print("  fuel model: OpenAP not installed (pip install openap); using the simple model", flush=True)
            return
        try:
            FUEL = FuelModel()
            s = FUEL.cal["summary"]
            print(f"  fuel model: OpenAP, calibrated on {s['refs']} published figures (held-out error {s['calibrated_loo_mape']*100:.1f}%)", flush=True)
        except Exception as e:
            print("  fuel model failed to load:", e, flush=True)
    load_fuel()
    threading.Thread(target=live.poll_global_forever, daemon=True).start()
    threading.Thread(target=live.poll_region_forever, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(live))

    def stop(*_):  # also save trails when stopped by a terminate signal, not just Ctrl+C
        live.save_history()
        print("\nStopped (recent paths saved).", flush=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    print(f"\n  Open http://localhost:{PORT}\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        live.save_history()
        print("\nStopped (recent paths saved).")

if __name__ == "__main__":
    main()
