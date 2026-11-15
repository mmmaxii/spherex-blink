# SPHEREx Blink

Web tool to watch the SPHEREx infrared sky change over time: enter sky coordinates, blink images taken on
different dates, and spot objects that move or vary. Built for the NASA Space Apps Challenge 2026
("Planet X and SPHEREx").

> Work in progress, built during the hackathon. Images, stacks, differences and overlays work with real
> data; spectra and their classification have the plumbing but not the science yet (see "Status").

## Architecture

```
frontend/   React + Vite + TypeScript  → Vercel (static). /api/* is rewritten to the backend.
backend/    FastAPI (Python 3.12)      → Render, one instance in us-east (next to the SPHEREx S3 bucket).
validation/ Jupyter notebooks where each step is tried and checked before it moves into backend/.
docs/       Notes and decisions.
```

What happens when someone enters a position:

1. `GET /api/resolve`: a name (Sesame/SIMBAD) or typed coordinates → decimal degrees. Fast stars are moved
   to where they were when SPHEREx looked (Barnard's Star is 4.5′ from its J2000 position).
2. `GET /api/coverage`: one IRSA SIA2 query over every configured release → images per detector and per
   survey pass, without reading any image.
3. `GET /api/frames`: starts a background job and answers at once; the page polls `GET /api/jobs/{id}`.
   The job reads a small piece of each image straight from S3 (HTTP Range, ~3 MB instead of 65 MB), removes
   the sky level, puts every piece on one north-up grid, and writes PNG frames with a common brightness
   scale, one stack per survey pass, pass-minus-first-pass differences and a GIF.
4. `GET /api/overlay`: Gaia DR3 (ESA) or AllWISE (IRSA) sources already placed on the frame.
5. `GET /api/spectrum`: same job mechanism; answers 501 until the photometry is validated.

Backend layout (`backend/app/`):

```
config.py     every URL, data release and limit (override with SPHEREX_* environment variables)
errors.py     the errors the API answers with: always {"error": {"code", "message", "detail"}}
schemas.py    shapes of the answers → /openapi.json → frontend types (npm run gen:api)
api/          routes: validation only
core/         HTTP with retries, disk cache, background jobs, product files
data/         resolve.py, sia.py, l2.py (partial reads from S3), flags.py, catalogs.py
imaging/      grid.py, align.py, background.py, stack.py, render.py
spectra/      photometry.py and classifier.py (stubs with their contracts)
pipeline/     blink.py and spectrum.py: the ordered steps of each long request
```

## The challenge, point by point

| Asked for | Where |
|---|---|
| Enter RA/Dec, see a series of images "like a little video" | search form → `/api/frames` → player (play, step, speed, GIF) |
| Test targets (Barnard, eps Ind B, WISE 0855, RW Aur, R Dra) | one-click buttons; all five resolve and have images |
| Easy to update with new data releases | `sia_collections` in `config.py` or `SPHEREX_SIA_COLLECTIONS`; results are recomputed weekly |
| Use the 102 bands; add images per detector | detector picker (6 wavelength ranges); "Survey passes (stacked)" view |
| Spectra on the fly | `pipeline/spectrum.py` is wired; `spectra/photometry.py` is not written yet (501) |
| Add or subtract images of different dates | stacks per survey pass; "Difference" view (pass − first pass) |
| Choose the field of view | 3–20 arcmin |
| Overlay Gaia / WISE | layer checkboxes → `/api/overlay`; Gaia positions moved with their proper motions |
| Coordinates in the URL, embeddable | every option lives in the URL; `&embed=1` shows only the player |
| Metadata and contamination flags | "About this image": flags on the target, flagged pixels painted or hidden, quality keys |
| Astropy, Aladin | astropy + reproject in the backend; Aladin Lite for "the same field seen by other telescopes" |

## Status

Checked with real data on 2026-11-14 (eps Ind B and WISE 0855 end to end; the five targets resolve and have
3–4 survey passes each). 53 offline tests + 4 live tests.

Not validated yet, and labelled as such in the code (`VERIFY`):

- stacks are plain sigma-clipped means (no variance weights); the S/N gain has not been measured;
- differences show residuals at the position of every star (undersampled PSF, different wavelengths per
  image), so only clear dipoles mean motion;
- images of one detector see the position at different wavelengths: brightness changes between frames are
  not variability by themselves. Every frame is labelled with its wavelength;
- WISE 0855 is at the detection limit even in the stacked passes of detector 6;
- spectra and classification: not built.

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
