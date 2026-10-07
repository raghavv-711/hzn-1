# HZN-1 · Fuel Horizon

HZN-1 is a concept chip that hears aircraft ADS-B broadcasts, decodes them, and estimates how much fuel each plane has left. Fuel Horizon is the globe that shows its output.

The public website lives in [`docs/`](docs/) and is plain static files, so GitHub Pages can serve it straight from this folder with no build step.

| Page | What it is |
|---|---|
| [`docs/index.html`](docs/index.html) | Scroll-driven 3D story: lid, floorplan, one message, layers, transistors, globe |
| [`docs/globe/`](docs/globe/) | Fuel Horizon with a recorded snapshot of real flights |
| [`docs/chip/`](docs/chip/) | Inside HZN-1, the interactive chip explorer |
| [`docs/model/`](docs/model/) | Fuel model check against 126 published figures |

## Preview locally

```bash
python3 -m http.server 8770 --directory docs
```

Then open http://localhost:8770. Add `?debug` to the landing page URL to expose a frame-stepping hook for automated checks.

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
