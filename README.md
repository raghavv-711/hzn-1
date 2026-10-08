# HZN-1 · Fuel Horizon

HZN-1 is a concept chip that hears aircraft ADS-B broadcasts, decodes them, and estimates how much fuel each plane has left. Fuel Horizon is the globe that shows its output.

The public website lives in [`docs/`](docs/) and is plain static files, so GitHub Pages can serve it straight from this folder with no build step.

| Page | What it is |
|---|---|
| [`docs/index.html`](docs/index.html) | Scroll-driven 3D story: lid, floorplan, one message, layers, transistors, globe |
| [`docs/globe/`](docs/globe/) | Fuel Horizon with a recorded snapshot of real flights |
| [`docs/chip/`](docs/chip/) | Inside HZN-1, the interactive chip explorer |
| [`docs/model/`](docs/model/) | Fuel model check against 126 published figures |
| [`docs/stats/`](docs/stats/) | Hourly fuel & CO₂ dashboard with what-if scenarios (sources in [`site-src/scenario-sources.md`](site-src/scenario-sources.md)) |
| [`docs/drivers/`](docs/drivers/) | Concept: Fuel Horizon for ride-hail drivers, with a simulated shift and the economics (source: `site-src/drivers.html`) |
| [`docs/silicon/`](docs/silicon/) | Real silicon: the Mode S CRC-24 checker as a SKY130 layout, with an in-browser run. Design, tests and GDS live in [raghavv-711/hzn-1-silicon](https://github.com/raghavv-711/hzn-1-silicon); `layout.png` comes from its `gds_render` artifact |

The globe also has a 24-hour replay, search by flight number or registration, airport boards, "Ask the globe"
(plain-English questions like "longest flight" or "United 787s to London", answered in the browser from the flight
data with no AI service), and shareable links (`#flight/UAL123`, `#area/airport:ORD`, `#ask/longest%20flight`, `#replay`).

## Visitor counts

[`docs/assets/analytics.js`](docs/assets/analytics.js) loads [GoatCounter](https://www.goatcounter.com) (free, no cookies) on every page once its site code is filled in. It stays off while the code is empty.

## Preview locally

```bash
python3 -m http.server 8770 --directory docs
```

Then open http://localhost:8770. Add `?debug` to the landing page URL to expose a frame-stepping hook for automated checks.

## Hourly refresh

[`.github/workflows/site.yml`](.github/workflows/site.yml) rebuilds and deploys the site every hour and on every push. It runs [`tools/refresh_snapshot.py`](tools/refresh_snapshot.py), which pulls OpenSky's global feed three times a few minutes apart, runs the fuel model on every flight, and rewrites the globe data, a replay frame (the last 24 kept in the Actions cache) and the dashboard numbers. The fresh data goes straight into the Pages deployment, so the repo doesn't grow with each refresh; flight paths carry over between runs in the Actions cache. If OpenSky can't be reached, the site is deployed with the data already in `docs/`.

- Run it now: Actions → *Build and deploy site* → *Run workflow*, or `gh workflow run site.yml`.
- Optional: add `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET` as repository secrets for higher OpenSky limits.
- GitHub pauses scheduled workflows after 60 days without commits; re-enable it from the Actions tab if that happens.

## Editing

- The landing page is edited directly: `docs/index.html` (markup and styles) and `docs/assets/story.js` (the 3D scene and scroll keyframes, see `KEYS`).
- The other three pages are generated from `site-src/` with `python3 site-src/build_site.py`, which turns the published-artifact links into relative site links.
- To refresh the globe with a new recording, run the snapshot bundler to get a new `fh-data.json`, then `python3 site-src/build_site.py path/to/fh-data.json`.

## Live version (local)

`fuel_horizon.py` runs Fuel Horizon with live flights on your own machine (Python 3, no packages needed beyond the standard library; the fuel model in `fuel_model.py` uses `pip install openap`):

```bash
python3 fuel_horizon.py
```

Then open http://localhost:8765. Set `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET` for higher OpenSky limits.

## Credits

Flight data: OpenSky Network and adsb.lol. Aircraft details: ADS-B Exchange database. Aircraft performance: OpenAP (TU Delft). Published fuel figures: Wikipedia, "Fuel economy in aircraft". Imagery: NASA Blue Marble. 3D: three.js.

HZN-1 is a design concept; the chip has not been fabricated.
