"""Fuel Horizon fuel model.

Estimates how much fuel a flight took off with and how much it has burned, by aircraft type:

  1. OpenAP (TU Delft's open aircraft-performance model) gives fuel flow for 37 jet types as a function of
     weight, altitude, speed and climb rate. Each flight is simulated as climb, cruise and descent, getting
     lighter as it burns fuel.
  2. Takeoff fuel follows standard airline planning: taxi + trip + 5% contingency + fuel to an alternate
     airport 200 nm away + 30 minutes of holding.
  3. Each ICAO aircraft type gets one calibration factor so the simulation matches published fuel-per-km
     figures for real sector lengths (Wikipedia, "Fuel economy in aircraft"). Types OpenAP lacks are mapped
     to a close relative and calibrated to their own published figures; turboprops use published figures
     directly.

`python3 fuel_model.py` rebuilds the calibration and prints the validation (leave-one-out) results.
"""
import json, math, os, sys, time, warnings
from functools import lru_cache
from pathlib import Path

warnings.filterwarnings("ignore")
KT = 1.852            # km/h per knot
FUEL_CO2 = 3.16       # kg CO2 per kg of jet fuel
HERE = Path(__file__).resolve().parent
CACHE = HERE / ".fuel-horizon-cache"
CAL_FILE = CACHE / "fuel-calibration.json"
GRID_FILE = CACHE / "fuel-grid.json"
GRID_KM = list(range(200, 16001, 200))

# ICAO type -> (OpenAP base model, Wikipedia names used to calibrate it)
JETS = {
    "A19N": ("a19n", ["Airbus A319neo"]), "A20N": ("a20n", ["Airbus A320neo"]), "A21N": ("a21n", ["Airbus A321neo", "Airbus A321LR"]),
    "A318": ("a318", []), "A319": ("a319", ["Airbus A319"]), "A320": ("a320", ["Airbus A320"]), "A321": ("a321", ["Airbus A321-200"]),
    "A332": ("a332", ["Airbus A330-200"]), "A333": ("a333", ["Airbus A330-300"]), "A338": ("a332", ["Airbus A330-800"]),
    "A339": ("a333", ["Airbus A330-900"]), "A343": ("a343", ["Airbus A340-300"]), "A346": ("a343", []),
    "A359": ("a359", ["Airbus A350-900"]), "A35K": ("a359", ["Airbus A350-1000"]), "A388": ("a388", ["Airbus A380"]),
    "B733": ("b734", ["Boeing 737-300"]), "B734": ("b734", []), "B735": ("b734", []),
    "B736": ("b737", ["Boeing 737-600"]), "B737": ("b737", ["Boeing 737-700"]), "B738": ("b738", ["Boeing 737-800", "Boeing 737-800W"]),
    "B739": ("b739", ["Boeing 737-900ER", "Boeing 737-900ERW"]), "B37M": ("b37m", ["Boeing 737 MAX 7", "Boeing 737 MAX-7"]),
    "B38M": ("b38m", ["Boeing 737 MAX 8", "Boeing 737 MAX-8"]), "B39M": ("b39m", ["Boeing 737 MAX 9", "Boeing 737 MAX-9"]), "B3XM": ("b3xm", []),
    "B744": ("b744", ["Boeing 747-400"]), "B748": ("b748", ["Boeing 747-8"]),
    "B752": ("b752", ["Boeing 757-200", "Boeing 757-200W"]), "B753": ("b752", ["Boeing 757-300"]),
    "B762": ("b763", ["Boeing 767-200ER"]), "B763": ("b763", ["Boeing 767-300ER"]), "B764": ("b763", ["Boeing 767-400ER"]),
    "B772": ("b772", ["Boeing 777-200", "Boeing 777-200ER"]), "B77L": ("b77w", ["Boeing 777-200LR"]), "B773": ("b773", ["Boeing 777-300"]),
    "B77W": ("b77w", ["Boeing 777-300ER"]),
    "B788": ("b788", ["Boeing 787-8", "Boeing 787-8 GEnx", "Boeing 787-8 Trent"]), "B789": ("b789", ["Boeing 787-9", "Boeing 787-9 GEnx"]),
    "B78X": ("b789", ["Boeing 787-10", "Boeing 787-10 GEnx", "Boeing 787-10 Trent"]),
    "BCS1": ("a19n", ["Airbus A220-100"]), "BCS3": ("a19n", ["Airbus A220-300"]),
    "CRJ1": ("e145", ["Bombardier CRJ100"]), "CRJ2": ("e145", ["Bombardier CRJ200"]), "CRJ7": ("crj9", ["Bombardier CRJ700"]),
    "CRJ9": ("crj9", ["Bombardier CRJ900"]), "CRJX": ("crj9", ["Bombardier CRJ1000"]),
    "E135": ("e145", ["Embraer ERJ-135ER"]), "E145": ("e145", ["Embraer ERJ-145ER"]), "E45X": ("e145", ["Embraer ERJ-145ER"]),
    "E170": ("e170", ["Embraer E-Jet-170"]), "E75L": ("e75l", ["Embraer E-Jet-175"]), "E75S": ("e75l", ["Embraer E-Jet-175"]),
    "E190": ("e190", ["Embraer E-Jet-190"]), "E195": ("e195", ["Embraer E-Jet-195"]),
    "E290": ("e190", ["Embraer E-Jet E2-190"]), "E295": ("e195", ["Embraer E-Jet E2-195"]),
    "C550": ("c550", []), "GLF6": ("glf6", []),
}
# turboprops and small aircraft with published figures but no OpenAP model: (Wikipedia names, cruise kt, tank kg)
RATED = {
    "AT72": (["ATR 72-600"], 275, 5000), "AT75": (["ATR 72-600"], 275, 5000), "AT76": (["ATR 72-600"], 275, 5000),
    "AT43": (["ATR 42-600"], 300, 4500), "AT45": (["ATR 42-600"], 300, 4500), "AT46": (["ATR 42-600"], 300, 4500),
    "DH8D": (["Bombardier Dash 8 Q400"], 360, 5300), "SF34": (["Saab 340"], 250, 2600), "SB20": (["Saab 2000"], 340, 4200),
    "D328": (["Dornier 328"], 335, 3400), "PC12": (["Pilatus PC-12"], 270, 1200), "KODI": (["Quest Kodiak"], 170, 1000),
}

# Published block fuel per km for real sectors (Wikipedia, "Fuel economy in aircraft", per-model tables): name, nmi, kg/km, seats
REFERENCE = """Airbus A220-100,600,2.8,115|Airbus A220-300,600,3.1,140|Airbus A220-100,500,2.57,125|Airbus A220-300,500,2.85,160|Airbus A319neo,600,3.37,144|Airbus A319neo,660,2.82,124|Airbus A320neo,660,2.79,154|Airbus A321neo,660,3.3,192|ATR 42-600,500,1.3,50|ATR 72-600,500,1.41,72|Boeing 737-300,507,3.49,126|Boeing 737-600,500,3.16,110|Boeing 737-700,500,3.21,126|Boeing 737 MAX 7,660,2.85,128|Boeing 737 MAX 7,600,3.39,144|Boeing 737-800,500,3.59,162|Boeing 737 MAX 8,660,3.04,166|Boeing 737-900ER,500,3.83,180|Boeing 737 MAX 9,660,3.3,180|Boeing 757-200,500,4.68,200|Boeing 757-300,500,5.19,243|Bombardier CRJ100,577,1.87,50|Bombardier CRJ200,580,1.8,50|Bombardier CRJ700,574,2.45,70|Bombardier CRJ900,573,2.78,88|Bombardier CRJ1000,500,2.66,100|Bombardier Dash 8 Q400,500,2.31,74|Bombardier Dash 8 Q400,600,1.83,74|Dornier 328,600,1.08,31|Embraer E-Jet E2-190,500,2.48,106|Embraer E-Jet E2-190,600,2.83,106|Embraer E-Jet E2-195,500,2.62,132|Embraer E-Jet E2-195,600,3.07,132|Embraer E-Jet-170,606,2.6,80|Embraer E-Jet-175,605,2.8,88|Embraer E-Jet-190,607,3.24,114|Embraer E-Jet-195,607,3.21,122|Embraer ERJ-135ER,596,1.44,37|Embraer ERJ-145ER,598,1.55,50|Pilatus PC-12,500,0.41,9|Saab 340,500,0.95,31|Saab 2000,500,1.54,50|Airbus A220-100,1000,2.28,125|Airbus A220-300,1000,2.3,135|Airbus A220-300,1000,2.42,150|Airbus A220-300,1000,2.56,160|Airbus A319,1000,2.93,124|Airbus A319neo,1000,2.4,136|Airbus A320,1000,3.13,150|Airbus A320neo,1000,2.79,180|Airbus A321-200,1000,3.61,180|Airbus A321neo,1000,3.47,220|Airbus A330-200,1000,5.6,293|Boeing 737-600,1000,2.77,110|Boeing 737-700,1000,2.82,126|Boeing 737-700,1000,2.8,128|Boeing 737 MAX-7,1000,2.51,140|Boeing 737-800,1000,3.17,162|Boeing 737-800,1000,3.45,160|Boeing 737-800W,1000,3.18,162|Boeing 737 MAX-8,1000,2.71,162|Boeing 737-900ER,1000,3.42,180|Boeing 737-900ERW,1000,3.42,180|Boeing 737 MAX-9,1000,2.91,180|Boeing 757-200,1000,4.6,190|Boeing 757-200,1000,4.16,200|Boeing 757-300,1000,4.68,243|Boeing 787-8,1000,5.5,248|Boeing 787-9,1000,5.67,296|Boeing 787-10,1000,6.09,336|Quest Kodiak,1000,0.71,9|Airbus A220-300,2000,2.42,150|Airbus A320,2151,2.91,150|Airbus A321LR,3400,2.99,154|Airbus A330-200,3000,6,241|Airbus A330-300,3000,6.25,262|Airbus A330-900,3350,6,310|Airbus A340-300,3000,6.81,262|Airbus A380,2000,13.6,544|Boeing 737 MAX-8,3400,2.86,168|Boeing 737 MAX-9,3400,2.91,144|Boeing 747-400,2151,10.77,416|Boeing 747-8,3000,9.9,467|Boeing 757-200W,3400,3.79,158|Boeing 767-200ER,3000,4.83,181|Boeing 767-200ER,3400,5.01,193|Boeing 767-200ER,3000,4.93,224|Boeing 767-300ER,2151,5.38,218|Boeing 767-300ER,3000,5.39,218|Boeing 767-300ER,3000,5.51,269|Boeing 767-400ER,3000,5.78,245|Boeing 767-400ER,3000,5.93,304|Boeing 767-400ER,3265,5.92,304|Boeing 777-200,3000,6.83,305|Boeing 777-200ER,3000,6.96,301|Boeing 777-300,3000,7.88,368|Boeing 787-8,3400,5.26,291|Boeing 787-8,3400,5.11,238|Boeing 787-9,3350,5.77,304|Airbus A330-200,6000,6.4,241|Airbus A330-200,5549,6.55,248|Airbus A330-300,5548,6.81,274|Airbus A330-800,4650,5.45,248|Airbus A330-900,4650,5.94,300|Airbus A340-300,6000,7.32,262|Airbus A350-900,4972,6.03,315|Airbus A350-900,5534,6.52,318|Airbus A350-900,6542,7.07,315|Airbus A350-1000,5531,7.46,327|Airbus A350-1000,5531,7.58,367|Airbus A380,7200,13.78,525|Airbus A380,6000,13.78,544|Boeing 747-400,6000,11.11,416|Boeing 747-400,5503,11.82,393|Boeing 747-400,5479,12.31,487|Boeing 747-8,6000,10.54,467|Boeing 747-8,7200,10.9,405|Boeing 777-200ER,5535,7.57,304|Boeing 777-200ER,6000,7.42,301|Boeing 777-200ER,6000,7.44,301|Boeing 777-200LR,4972,7.57,291|Boeing 777-300ER,5507,8.86,382|Boeing 777-300ER,6000,8.49,365|Boeing 777-300ER,7200,8.58,344|Boeing 787-8,4650,5.38,243|Boeing 787-8 GEnx,5537,5.3,220|Boeing 787-8 Trent,5537,5.51,220|Boeing 787-9 GEnx,4650,5.85,294|Boeing 787-9,4972,5.63,304|Boeing 787-9 GEnx,5534,5.62,266|Boeing 787-9,6542,7.18,291|Boeing 787-10 GEnx,5529,6.12,337|Boeing 787-10 Trent,5529,6.24,337"""
REFS = [(n, float(a), float(b), int(c)) for n, a, b, c in (r.split(",") for r in REFERENCE.split("|"))]


@lru_cache(None)
def _openap(base):
    from openap import prop, FuelFlow
    try:
        ff = FuelFlow(base)
    except ValueError:  # some types (e.g. A320neo family, 737 MAX 7/9) borrow a close relative's drag data
        ff = FuelFlow(base, use_synonym=True)
    return prop.aircraft(base), ff


def _seats(icao, base):
    names = (JETS.get(icao) or ([],))[1] if icao in JETS else []
    s = [r[3] for r in REFS if r[0] in names]
    if s:
        return sum(s) / len(s)
    pax = _openap(base)[0].get("pax") or {}
    return (pax.get("low", 0) + pax.get("high", 0)) / 2 or pax.get("max", 100)


def fly(base, factor, dist_km, tow, dt=60.0):
    """Simulate climb / cruise / descent. Returns (trip fuel kg, km and fuel at top of climb, cruise kg/km, landing mass)."""
    a, ff = _openap(base)
    hc = (a.get("cruise", {}).get("height") or 10700) / 0.3048
    tas_c = (a.get("cruise", {}).get("mach") or 0.78) * 576
    clb_fpm = des_fpm = 2000.0
    while hc > 10000:  # short trips don't climb as high
        d_clb = hc / clb_fpm / 60 * (250 + tas_c) / 2 * KT
        if 2 * d_clb <= 0.85 * dist_km:
            break
        hc -= 2000
    d_des = hc / des_fpm / 60 * (250 + tas_c) / 2 * KT
    m, d, alt, fuel, toc, cruise_fuel, cruise_km, phase = tow, 0.0, 0.0, 0.0, None, 0.0, 0.0, "clb"
    while d < dist_km:
        rem = dist_km - d
        if phase == "clb" and alt >= hc:
            phase, toc = "crz", (d, fuel)
        if phase in ("clb", "crz") and rem <= d_des:
            phase = "des"
            if toc is None:
                toc = (d, fuel)
        if phase == "clb":
            vs, tas = clb_fpm, 250 + (tas_c - 250) * alt / hc
        elif phase == "crz":
            vs, tas = 0.0, tas_c
        else:
            vs, tas = (-des_fpm if alt > 1500 else 0.0), max(210.0, 250 + (tas_c - 250) * alt / hc)
        f = float(ff.enroute(mass=m, tas=tas, alt=alt, vs=vs)) * factor  # kg/s
        step = min(tas * KT * dt / 3600, rem)
        burn = f * dt * step / (tas * KT * dt / 3600)
        fuel += burn; m -= burn; d += step
        alt = min(hc, max(0.0, alt + vs * dt / 60))
        if phase == "crz":
            cruise_fuel += burn; cruise_km += step
    toc = toc or (dist_km, fuel)
    return fuel, toc[0], toc[1], (cruise_fuel / cruise_km if cruise_km else fuel / dist_km), m


def mission(icao, factor, dist_km, seats=None):
    """Plan a flight like an airline would and fly it. Returns a dict of fuel figures in kg."""
    base = JETS[icao][0]
    a, ff = _openap(base)
    oew, mtow, mfc = a["oew"], a["mtow"], a["mfc"]
    payload = (seats if seats is not None else 0.82 * _seats(icao, base)) * 100 + (0.08 * (mtow - oew) if mtow > 150000 else 0)
    taxi = 0.0016 * mtow / 1000 * 720 * factor
    planned = 0.35 * mfc
    for _ in range(3):
        tow = min(oew + payload + planned - taxi, mtow)
        trip, d_toc, f_toc, kgkm, landing = fly(base, factor, dist_km, tow)
        contingency = 0.05 * trip
        alternate = kgkm * 370 * 1.2
        final = float(ff.enroute(mass=landing, tas=210, alt=1500, vs=0)) * factor * 1800
        planned = min(mfc, taxi + trip + contingency + alternate + final)
    return {"tow": tow, "planned": planned, "trip": trip, "taxi": taxi, "reserve": contingency + alternate + final,
            "toc_km": d_toc, "toc_fuel": f_toc, "kgkm": kgkm, "tank": mfc, "block_per_km": (trip + taxi) / dist_km}


def _calibrate_ref(icao, nmi, seats, target, factor=1.0):
    for _ in range(3):
        got = mission(icao, factor, nmi * KT, seats)["block_per_km"]
        factor *= target / got
    return factor


def build_calibration(verbose=True):
    """Fit one factor per type and measure leave-one-out error on the published figures."""
    t0 = time.time()
    per_ref, out = [], {"factors": {}, "validation": [], "rated": {}}
    for icao, (base, names) in JETS.items():
        refs = [r for r in REFS if r[0] in names]
        for n, nmi, kgkm, seats in refs:
            raw = mission(icao, 1.0, nmi * KT, seats)["block_per_km"]
            fac = _calibrate_ref(icao, nmi, seats, kgkm, kgkm / raw)
            per_ref.append((icao, n, nmi, kgkm, seats, raw, fac))
    for icao in JETS:
        facs = [r[6] for r in per_ref if r[0] == icao]
        out["factors"][icao] = math.exp(sum(map(math.log, facs)) / len(facs)) if facs else None
    # types with no published figures borrow the median factor of their OpenAP base's calibrated types
    for icao, (base, _) in JETS.items():
        if out["factors"][icao] is None:
            sib = sorted(f for k, f in out["factors"].items() if f and JETS[k][0] == base)
            allf = sorted(f for f in out["factors"].values() if f)
            out["factors"][icao] = (sib or allf)[len(sib or allf) // 2]
    for icao, n, nmi, kgkm, seats, raw, fac in per_ref:
        others = [r[6] for r in per_ref if r[0] == icao and not (r[1] == n and r[2] == nmi and r[4] == seats)]
        loo = None
        if others:
            f = math.exp(sum(map(math.log, others)) / len(others))
            loo = mission(icao, f, nmi * KT, seats)["block_per_km"]
        out["validation"].append({"type": icao, "model": n, "nmi": nmi, "seats": seats, "published": kgkm,
                                  "openap_raw": round(raw, 3), "calibrated_loo": round(loo, 3) if loo else None})
    for icao, (names, kt, tank) in RATED.items():
        v = [r[2] for r in REFS if r[0] in names]
        out["rated"][icao] = {"kgkm": sum(v) / len(v), "kt": kt, "tank": tank}
    raw_err = [abs(v["openap_raw"] / v["published"] - 1) for v in out["validation"]]
    loo_err = [abs(v["calibrated_loo"] / v["published"] - 1) for v in out["validation"] if v["calibrated_loo"]]
    out["summary"] = {"refs": len(out["validation"]), "openap_raw_mape": sum(raw_err) / len(raw_err),
                      "loo_refs": len(loo_err), "calibrated_loo_mape": sum(loo_err) / len(loo_err) if loo_err else None,
                      "seconds": round(time.time() - t0, 1)}
    CACHE.mkdir(exist_ok=True)
    CAL_FILE.write_text(json.dumps(out, indent=1))
    if verbose:
        s = out["summary"]
        print(f"calibrated {sum(1 for f in out['factors'].values() if f)} types from {s['refs']} published figures in {s['seconds']} s")
        print(f"  OpenAP as-is:            average error {s['openap_raw_mape']*100:.1f}% (all {s['refs']} figures)")
        if s["calibrated_loo_mape"] is not None:
            print(f"  calibrated, held-out:    average error {s['calibrated_loo_mape']*100:.1f}% ({s['loo_refs']} figures predicted without seeing them)")
    return out


def build_grid(cal, verbose=True):
    """Pre-plan missions for every type at 200 km steps so live lookups are instant."""
    t0 = time.time(); grid = {}
    for icao in JETS:
        f = cal["factors"][icao]
        grid[icao] = [[round(v, 1) for v in (lambda m: [m["tow"], m["planned"], m["trip"], m["reserve"], m["toc_km"], m["toc_fuel"], m["kgkm"], m["tank"]])(mission(icao, f, km))]
                      for km in GRID_KM]
    GRID_FILE.write_text(json.dumps(grid, separators=(",", ":")))
    if verbose:
        print(f"planned {len(JETS) * len(GRID_KM)} missions in {time.time() - t0:.0f} s")
    return grid


class FuelModel:
    """What the server uses: per-flight takeoff fuel, burn so far and burn rate now."""

    def __init__(self):
        self.cal = json.loads(CAL_FILE.read_text()) if CAL_FILE.exists() else build_calibration(False)
        self.grid = json.loads(GRID_FILE.read_text()) if GRID_FILE.exists() else build_grid(self.cal, False)
        s = self.cal["summary"]
        # published figures are matched within ~5%; real flights also vary with load and winds, so show at least ±12%
        self.uncertainty = round(max(0.12, (s.get("calibrated_loo_mape") or 0.15) * 1.25), 3)

    def plan(self, icao, dist_km):
        """Interpolated mission for this type and distance, or None if the type isn't modelled."""
        if icao in JETS:
            g = self.grid[icao]
            x = min(max(dist_km, GRID_KM[0]), GRID_KM[-1])
            i = min(int((x - GRID_KM[0]) // 200), len(GRID_KM) - 2)
            t = (x - GRID_KM[i]) / 200
            v = [g[i][k] + (g[i + 1][k] - g[i][k]) * t for k in range(8)]
            if dist_km < GRID_KM[0]:  # scale the shortest mission down
                s = dist_km / GRID_KM[0]
                v[2] *= s; v[4] *= s; v[5] *= s; v[1] = min(v[7], v[1] - (1 - s) * (v[2] / s - v[2]))
            tow, planned, trip, reserve, toc_km, toc_fuel, kgkm, tank = v
            return {"planned": planned, "trip": trip, "reserve": reserve, "toc_km": toc_km, "toc_fuel": toc_fuel,
                    "kgkm": kgkm, "tank": tank, "tow": tow, "label": "OpenAP " + JETS[icao][0].upper() + " · calibrated"}
        if icao in self.cal["rated"]:
            r = self.cal["rated"][icao]
            trip = r["kgkm"] * dist_km
            reserve = 0.05 * trip + r["kgkm"] * 370 + r["kgkm"] * r["kt"] * KT * 0.5
            planned = min(r["tank"], trip + reserve)
            return {"planned": planned, "trip": trip, "reserve": reserve, "toc_km": min(dist_km, 60), "toc_fuel": r["kgkm"] * min(dist_km, 60) * 1.4,
                    "kgkm": r["kgkm"], "tank": r["tank"], "tow": None, "label": "published figures"}
        return None

    @staticmethod
    def used_at(p, flown_km):
        """Fuel burned after flying `flown_km` of the trip, including taxi."""
        taxi = max(0.0, p["planned"] - p["trip"] - p["reserve"])
        if flown_km < p["toc_km"]:
            f = p["toc_fuel"] * flown_km / max(p["toc_km"], 1e-6)
        else:
            f = p["toc_fuel"] + (flown_km - p["toc_km"]) * p["kgkm"]
        return taxi + min(f, p["trip"])

    def estimate(self, icao, dist_km, flown_km, alt_ft, gs_kt, vs_fpm):
        """Compact fuel figures for one flight, or None if its type isn't modelled.
        [takeoff fuel, trip fuel, reserves, top-of-climb km, fuel at top of climb, cruise kg/km, tank, burn now kg/h, label, uncertainty]"""
        if dist_km:
            p = self.plan(icao, dist_km)
            if not p:
                return None
            used = self.used_at(p, flown_km)
            burn = self.burn_now(icao, p["tow"], used, alt_ft, gs_kt, vs_fpm) or p["kgkm"] * gs_kt * KT
            return [round(p["planned"]), round(p["trip"]), round(p["reserve"]), round(p["toc_km"]), round(p["toc_fuel"]),
                    round(p["kgkm"], 3), round(p["tank"]), round(burn), p["label"], self.uncertainty]
        p = self.plan(icao, 1500)  # no route on file: burn rate only, at a typical mid-flight weight
        if not p:
            return None
        burn = self.burn_now(icao, p["tow"], 0.5 * p["trip"], alt_ft, gs_kt, vs_fpm) or p["kgkm"] * gs_kt * KT
        return [0, 0, 0, 0, 0, 0, round(p["tank"]), round(burn), p["label"], self.uncertainty]

    def burn_now(self, icao, tow, used, alt_ft, gs_kt, vs_fpm):
        """Fuel flow right now (kg/h) from OpenAP at the current weight, height, speed and climb rate."""
        if icao in JETS and tow:
            a, ff = _openap(JETS[icao][0])
            m = max(a["oew"], tow - used)
            f = float(ff.enroute(mass=m, tas=min(max(gs_kt, 150), 520), alt=max(alt_ft, 0), vs=max(-3000, min(vs_fpm, 4000))))
            return f * 3600 * self.cal["factors"][icao]
        if icao in self.cal["rated"]:
            r = self.cal["rated"][icao]
            return r["kgkm"] * r["kt"] * KT
        return None


if __name__ == "__main__":
    cal = build_calibration()
    if "--grid" in sys.argv:
        build_grid(cal)
