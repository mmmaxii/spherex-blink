# SPHEREx Blink

Web tool to watch the SPHEREx infrared sky change over time: enter sky coordinates, blink images taken on
different dates, and spot objects that move or vary. Built for the NASA Space Apps Challenge 2026
("Planet X and SPHEREx").

> Built during the hackathon. Images, stacks, differences, adding/subtracting frames, overlays, spectra and
> light curves work with real data; the classification of spectra is not built yet (see "Status").

Live: https://spherex-blink-umber.vercel.app (backend on Render's free plan: the first request after
15 idle minutes waits ~1 min while it wakes up).

## Architecture

```
frontend/   React + Vite + TypeScript  → Vercel (static). /api/* is rewritten to the backend.
backend/    FastAPI (Python 3.12)      → Render, one instance in us-east (next to the SPHEREx S3 bucket).
validation/ Jupyter notebooks where each step is tried and checked before it moves into backend/.
docs/       Notes and decisions.
```

Two pages, one address:

- `/` **sky map** (Aladin Lite, full screen). The coordinates follow the cursor; a click fixes a field
  (its size follows the map zoom, 3–20′); "Analyse this field" makes a quick blink preview of the
  detector with most images, and "Full analysis" opens the second page. Missions from ultraviolet to
  sub-mm (GALEX, DSS2, 2MASS, the SPHEREx all-sky cube at 2.04 µm, Spitzer, WISE, Herschel, Planck),
  all served by IRSA. The menu keeps the last five analyses in the browser.
- `/?ra=…&dec=…` or `/?target=…` **full analysis**: player, detectors, stacks, differences, add/subtract,
  overlays, spectrum, brightness changes and context map. Every option is in the address, so it can be shared or embedded.

What happens when someone analyses a position:

1. `GET /api/resolve`: a name (Sesame/SIMBAD) or typed coordinates → decimal degrees. Fast stars are moved
   to where they were when SPHEREx looked (Barnard's Star is 4.5′ from its J2000 position).
2. `GET /api/coverage`: one IRSA SIA2 query over every configured release → images per detector and per
   survey pass, without reading any image.
3. `GET /api/frames`: starts a background job and answers at once; the page polls `GET /api/jobs/{id}`.
   The job reads a small piece of each image straight from S3 (HTTP Range, ~3 MB instead of 65 MB), removes
   the sky level, puts every piece on one north-up grid, and writes PNG frames with a common brightness
   scale, one stack per survey pass, differences against a reference pass (in MJy/sr and relative
   to each star's brightness) and a GIF.
4. `GET /api/overlay`: Gaia DR3 (ESA) or AllWISE (IRSA) sources already placed on the frame.
5. `GET /api/spectrum`: same job mechanism. Measures the target on every image (one wavelength per image),
   with the wavelength and pixel solid angle of that exact pixel from the calibration maps, and returns the
   points grouped by survey pass, so passes can be compared at the same wavelength.
6. `GET /api/variability`: same job mechanism. Measures the target and comparison stars on every image
   (wide and deep surveys, up to 600 images) and returns the light curve, the verdict, a period when the
   sampling supports one, and the median per survey pass and wavelength band.

Every image is read from S3 with 4 HTTP Range requests (6 with the variance): the headers, the rows of
IMAGE around the position, the FLAGS row index and the compressed rows, decoded with astropy's RICE
codec. Pixels identical to astropy on real DR1/QR3 files; one light curve went from 52 to ~4 min.

Backend layout (`backend/app/`):

```
config.py     every URL, data release and limit (override with SPHEREX_* environment variables)
errors.py     the errors the API answers with: always {"error": {"code", "message", "detail"}}
schemas.py    shapes of the answers → /openapi.json → frontend types (npm run gen:api)
api/          routes: validation only
core/         HTTP with retries, disk cache, background jobs, product files
data/         resolve.py, sia.py, l2.py (partial reads from S3), flags.py, catalogs.py,
              calibration.py (per-pixel wavelength and solid angle, downloaded once)
imaging/      grid.py, align.py, background.py, stack.py, render.py
spectra/      photometry.py (aperture photometry), variability.py (light curves), classifier.py (stub)
pipeline/     blink.py, spectrum.py, variability.py: the ordered steps of each long request
```

## The challenge, point by point

| Asked for | Where |
|---|---|
| Enter RA/Dec, see a series of images "like a little video" | search form → `/api/frames` → player (play, step, speed, GIF) |
| Test targets (Barnard, eps Ind B, WISE 0855, RW Aur, R Dra) | one-click buttons; all five resolve and have images |
| Easy to update with new data releases | `sia_collections` in `config.py` or `SPHEREX_SIA_COLLECTIONS`; results are recomputed weekly |
| Use the 102 bands; add images per detector | detector picker (6 wavelength ranges); "Survey passes (stacked)" view |
| Spectra on the fly | "Measure the spectrum" → `/api/spectrum`: one point per image, 0.75–5 µm, one colour per pass |
| See what changed or moved | "What changed" view: each pass against the reference, relative to each star's brightness; constant stars stay grey, brighter = orange, fainter = blue, a moving star shows both side by side |
| Add or subtract images of different dates | stacks per survey pass; "Difference" view (pass − reference pass); "Add / subtract" tab: any frames in group A minus any in group B, computed in the browser from the aligned values |
| See how the sky changes over time | "Brightness changes" → `/api/variability`: light curve against constant stars, verdict and period |
| Choose the field of view | 3–20 arcmin |
| Overlay Gaia / WISE | layer checkboxes → `/api/overlay`; Gaia positions moved with their proper motions |
| Coordinates in the URL, embeddable | every option lives in the URL; `&embed=1` shows only the player |
| Metadata and contamination flags | "About this image": flags on the target, flagged pixels painted or hidden, quality keys |
| Astropy, Aladin | astropy + reproject in the backend; Aladin Lite as the home map (pick a field by clicking) and for "the same field seen by other telescopes" |

## Status

Checked with real data on 2026-11-14 (eps Ind B and WISE 0855 end to end; the five targets resolve and have
3–4 survey passes each). 75 offline tests + 4 live tests.

Not validated yet, and labelled as such in the code (`VERIFY`):

- stacks are per-pixel medians of every recorded pixel except detector defects (HOT, COLD, NONFUNC,
  MISSING_DATA). Hiding all flagged pixels image by image left flat patches around stars in the
  differences (pixels averaged over different subsets of images), and one image with an odd
  background left a bright band; the median fixes both (checked on RW Aur and eps Ind B, 15 Nov).
  Differences use as reference the first pass with at least 3 images. The S/N gain is not measured;
- differences show residuals at the position of every star (undersampled PSF, different wavelengths per
  image), so only clear dipoles mean motion. Alignment is not the cause: pass stacks agree to 0.1 px
  (0.3″) on RW Aur;
- "What changed" (checked 2026-11-15 on RW Aur and Barnard's Star, D1/D2, 12′): both stacks are blurred
  (Gaussian σ = 1.5 grid px = 4.6″, below the 9″ PSF), the difference is divided by their mean on
  pixels brighter than 8 sky σ, and only changes above max(3 × scatter of all star pixels, 10 %) are
  coloured (threshold ~27 % in those fields). RW Aur is the only star coloured (brighter in passes 2
  and 3, as its light curve says: ×0.68 in Sep 2025, ×1.48 in Sep 2026 in D1); Barnard's Star shows
  blue to the south and orange to the north, its known motion. Saturated stars can show false changes
  at their core; a change below the threshold is invisible here (use "Brightness changes");
- images of one detector see the position at different wavelengths: brightness changes between frames are
  not variability by themselves. Every frame is labelled with its wavelength;
- WISE 0855 is at the detection limit even in the stacked passes of detector 6;
- classification of spectra: not built.

Spectra (validated on 2026-11-15 with eps Ind B, all 463 images, from Chile in 11 min):
- aperture of 2.5 px (97.7–98.8 % of the ePSF) and a 6–10 px sky annulus, sigma-clipped. The SOURCE flag
  is not excluded from the sky: in DR1 it covers ~45 % of every detector;
- flagged pixels (official recipe) are left out and the flux is corrected for the light they held; images
  with more than 20 % of the light lost (saturated or damaged core) are skipped with the reason;
- wavelength and solid angle per pixel from the spectral WCS and solid-angle maps (WCS-WAVE differs by up
  to 0.13 % in wavelength, the solid angle by ±1.3 %); 3 % calibration error added in quadrature;
- result: 412 points, identical to the validation notebook on the 391 clean images (median ratio 1.0000);
  the four passes agree within 0.03 % on average, with 4 % scatter per point; the T-dwarf bands
  (H₂O at 1.4 and 1.9 µm, CH₄ from 2.2 to 3.5 µm) are clear;
- saturated targets (Barnard, R Dra; RW Aur at some wavelengths) get no spectrum point there; the page
  says so and points to "Brightness changes", which follows them with the PSF wings.

Brightness changes (validated on 2026-11-15, notebook 04 and the backend on the five targets):
- each measurement is divided by the same star at the same wavelength (± half a band) in the other
  images, so colour does not look like variability. Comparison stars (detected above 10σ, isolated, in a
  301 × 301 px piece) give what "constant" looks like. A per-image zero point is not applied: the real
  calibration error per image (0.4–0.9 %) is below the comparison-star noise;
- saturated targets (aperture fails on ≥ 30 % of images) are measured with the PSF wings (ring of 9–14 px
  minus the sky at 20–28 px), in relative units. Barnard's Star (quiet) shows the wings can fake changes
  up to ~15 %, so the threshold is higher for them;
- verdict: variable when the scatter is above max(3 × comparison scatter, 5 %), or 15 % with wings. The
  5 % floor is the smallest change recovered in an injection test (10 % sinusoid → 9.5 %, right period);
- period (Lomb–Scargle) only when power ≥ 0.25, the images span ≥ 1.5 periods without a gap longer than
  half a period, and the comparison stars show no period (power < 0.1);
- results: eps Ind B no change (5.2 % against 3.5 % for 12 comparison stars); RW Aur variable (41 %
  against 3.1 %, medians ×0.86, ×1.01, ×1.22 in its three passes, and a colour change); Barnard no change
  above 15 %; R Dra (saturated, 600 images) repeats every 244.6 days, its catalogue period is ~245 d;
- speed on Render's free plan: ~0.3 images/s, so a 335-image light curve takes ~20 min. Results are
  cached on disk until the service restarts.

Add / subtract (checked in the browser on 2026-11-15):
- each frame's aligned values (MJy/sr, sky removed, flagged pixels as NaN) are served as a float16 file
  (`data_url`, ~0.1 MB). The page averages group A and group B ignoring NaN and shows A − B on a ±6σ
  scale. Frames of one detector see the position at different wavelengths: a residual is not a change
  by itself unless both groups cover the same wavelengths (pick frames of the same pass position).

Sky map notes (checked 2026-11-15):
- Aladin Lite 3.8.2 is bundled from npm (`aladin-lite`), not loaded from the CDS server: that server
  answered 404 on 15 Nov, and so did the CDS survey tiles. Surveys are loaded from IRSA's copies
  (`irsa.ipac.caltech.edu/data/hips/...`, CORS open). The map needs WebGL2; without it the page says so.
- The SPHEREx all-sky cube is shown at one channel (2.04 µm). Aladin turns a slice number into a
  frequency assuming evenly spaced channels; slice 17 loads cube frame 43 (measured in the browser).
- In the blink, flagged pixels are filled from the surrounding sky for display only ("Paint flags" shows
  where they are; measurements never use filled pixels).

## Run locally

Backend (terminal 1):

```bash
cd backend
uv venv .venv --python 3.12          # or: py -3.12 -m venv .venv
uv pip install -e ".[dev]"           # or: .venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\activate               # macOS/Linux: source .venv/bin/activate
uvicorn app.main:app --reload --port 8000     # docs at http://localhost:8000/docs
pytest                                        # offline tests (synthetic images, saved answers)
pytest -m live                                # against IRSA, S3, CDS and ESA (about a minute)
```

Frontend (terminal 2):

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173 (proxies /api to :8000)
npm run gen:api                      # regenerate API types from the running backend
```

Validation:

```bash
cd validation
uv venv .venv --python 3.12 && uv pip install -r requirements.txt
.venv\Scripts\jupyter lab
```

## Working together

- One branch per task, merged to `main` through a Pull Request every 1–2 hours. `main` must always deploy.
- Folder ownership: `frontend/` and `backend/` (web), `validation/` (science checks), `docs/`.
- Never commit data, FITS files, `.venv/`, `node_modules/` or secrets.

## Data and credits

SPHEREx DR1 and QR3 spectral images and the DR1 all-sky cube, from NASA/IPAC Infrared Science Archive (IRSA).
Cite DOI [10.26131/IRSA678](https://www.ipac.caltech.edu/doi/10.26131/IRSA678) (DR1 spectral images) and
[10.26131/IRSA679](https://www.ipac.caltech.edu/doi/10.26131/IRSA679) (all-sky cube).

"This publication makes use of data products from the Spectro-Photometer for the History of the Universe,
Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory
and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration."

Sky viewer: Aladin Lite (CDS, Strasbourg). AI assistance (Claude) was used and is declared in the submission.

## License

MIT
