# CLAUDE.md — SPHEREx Blink

Context for AI sessions working on this repo. Read fully before changing code.

## What this is

Public web tool for the NASA Space Apps Challenge 2026, "Planet X and SPHEREx": the user enters RA/Dec (or a
name) and sees a series of SPHEREx images of that patch of sky "like a little video", to spot what moves or
varies. Official test targets: Barnard's Star, Epsilon Indi B, WISE 0855, RW Aur, R Dra.

The team writes the code during the hackathon. **Build step by step with the team; do not implement features
nobody asked for.** Everything in the repo is in English (code, routes, URL parameters, UI text).

## Architecture (decided)

- `frontend/`: React + Vite + TypeScript on Vercel. Two pages chosen by the URL in `App.tsx`:
  `pages/ExplorePage` (no position in the URL: full-screen sky map, field picked by click, quick-look
  preview, last five analyses in localStorage) and `pages/AnalysisPage` (`?ra&dec` or `?target`: the
  full analysis; its state lives in the URL, `src/state/urlState.ts`). Sky map: `components/SkyMap` +
  `src/sky/` (Aladin Lite 3.8.2 bundled from npm, surveys from IRSA's HiPS copies, coordinate formats).
  Other components: `Player` (with the `CombineView` add/subtract tab), `SpectrumPanel`,
  `VariabilityPanel`, `ContextMap`, `SelectionPanel`, `ManualPosition`, `RecentMenu`, `SurveyBar`,
  `StatusBar`, `PreviewLoop`, `InfoDialog`. Every panel explains itself in a collapsible `InfoNote`
  (texts in `src/content/explanations.tsx`). API types generated from FastAPI's `/openapi.json`
  (`npm run gen:api`, backend running) into `src/api/schema.d.ts`.
- `backend/`: FastAPI on Render (one instance, one worker, us-east, Python 3.12). Layers, top to bottom:
  `api/routes.py` (validation only) → `pipeline/` (ordered steps of a long request, run as background jobs)
  → `data/`, `imaging/`, `spectra/` (one small function per step) → `core/` (HTTP retries, disk cache,
  jobs, product files). All settings in `app/config.py`; answer shapes in `app/schemas.py`; errors in
  `app/errors.py` (always `{"error": {"code", "message", "detail"}}`).
- Long requests (`/api/frames`, `/api/spectrum`, `/api/variability`) answer at once with a job; the page polls
  `/api/jobs/{id}`. The job id is a hash of the parameters, so equal requests share work, and results are
  kept on disk under `.cache/products/` (a cache only: Render's disk is temporary).
- `validation/`: notebooks where a step is tried and checked first. Code that passes moves into
  `backend/app/` with a note of the notebook cell it came from.

Spectra (`spectra/photometry.measure()`) and light curves (`spectra/variability.py`) work, validated
2026-11-15 (see below). Not built:
`spectra/classifier.classify()` (stub; it loads `backend/models/classifier.joblib` when the file exists) and
the all-sky-cube quick look (`/api/spectrum?mode=cube` answers 501).

Code style: small functions with clear names and comments that say why; no dense one-liners to save time.

## Rules

1. **Scientific honesty first.** No result is shown without its validation. A well-explained null result beats
   an inflated one.
2. **Verify, don't assume.** Anything not confirmed in official docs (IRSA, Explanatory Supplement) or real data
   is marked `VERIFY` in code.
3. **Releases:** DR1 + QR3 go together (same R7 pipeline). Never mix with QR2.
4. **Compare at the same wavelength.** Every pixel sees a different λ (linear variable filter). Every image
   shown says its λ and date.
5. **Units in names:** `_jy`, `_um`, `_px`, `_deg`, `_arcmin`, `mjd`.
6. **Read from the file what the file says** (IMAGE data offset, flag bit names, WCS-WAVE table size).

## Verified facts (2026-11-13)

- SIA collections: `spherex_dr1`, `spherex_qr3`, `spherex_dr1_deep`, `spherex_qr3_deep`, `spherex_dr1_cube`.
  SIA returns metadata (access_url, cloud_access, t_min/t_max, energy_bandpassname, em_min/em_max, s_region),
  not the FITS. IRSA has no CORS; S3 does.
- L2 file (~65 MB): PRIMARY, IMAGE (2040², float32, MJy/sr, uncompressed, row-major), FLAGS (RICE-compressed
  table, bit names in `MSKNnnnn`), VARIANCE, ZODI (not subtracted), EPSF (441 zones × 33×33), WCS-WAVE.
  Pixel 6.15″; `PSF_FWHM` ~9″ (undersampled). Useful keys: `MJD-AVG`, `FINAST`, `SPS_EPA`, `X_SC/Y_SC/Z_SC`,
  `*_CONT` contamination booleans.
- Official flag recipe for photometry: exclude SUR_ERROR, NONFUNC, MISSING_DATA, HOT, COLD, NONLINEAR, PERSIST,
  BLOOM, SNOWBALL, HALO, SATELLITE_HALO; keep TRANSIENT, OVERFLOW, OUTLIER, SOURCE. SOURCE also marks known
  asteroids: never discard a target for it.
- IRSA cutout service: 10–13 s and ~4 MB per cutout. Read rows from S3 instead (8,160 bytes per IMAGE row).
- Survey passes last 10–88 days, ~6 months apart; exposures 2.4 min apart within a burst.
- Test targets (DR1 + QR3): eps Ind B 458 images / 4 passes (not saturated); Barnard 358 / 3 (saturated);
  WISE 0855 258 / 3 (faint, D5–D6; today 2.1′ from the challenge's coordinates); RW Aur 335 / 3 complete
  passes; R Dra 539 / 3 (saturated, near the deep field).
- All-sky cube: zodi subtracted, 12.88″ pixels, no time information → quick-look spectra only.

## Measured on 2026-11-14

- SIA straight from the URL with `RESPONSEFORMAT=CSV` and several `COLLECTION` parameters: ~2.5 s for 467
  images (astroquery adds a "capabilities" request that fails at times).
- One L2 cutout with astropy + fsspec takes ~15 range requests (headers of every extension, rows, compressed
  flags, WCS-WAVE). From Chile ~1–3 s per image in parallel and bandwidth-bound; not measured on Render yet.
- Flagged pixels (official recipe) must be hidden in the blink: cosmic-ray hits, persistence and halos change
  from image to image and look like moving objects. The unmasked frame is served too (`raw_url`).
- Sesame redirects to a mirror when Strasbourg is down (follow redirects); TAPVizieR and IRSA TAP timed out,
  so overlays use the ESA Gaia TAP and the IRSA cone search (`SCS`, table `allwise_p3as_psd`).
- SIMBAD does not know "WISE 0855-0714"; it knows "WISE J085510.83-071442.5" (alias in `data/resolve.py`).
- `FINAST` >= 2 = astrometry unusable (image skipped). The "W" WCS wavelength is approximate (9 x 9 table).
- `logging.getLogger("astropy")` before importing astropy breaks astropy's start-up (see `app/log.py`).

## Validated on 2026-11-15 (spectra)

- The DR1 `SOURCE` flag covers ~45 % of every detector (Supplement §3.2.9: pixels with flux from catalog
  sources). Never exclude it from a sky estimate: the sky becomes empty. Sky = sigma-clipped annulus.
- Science wavelength: `dr1/spectral_wcs/...` (CWAVE/CBAND per pixel); solid angle: `dr1/solid_angle_pixel_map/...`.
  WCS-WAVE differs from CWAVE by ≤ 0.13 %. The API ships a grid of every 8th pixel of those maps
  (`data/calibration_dr1.npz`, built by `scripts/build_calibration_grid.py`): downloading the 300 MB of maps
  filled the 512 MB Render instance. Grid vs full maps: λ ≤ 0.04 % (p99), CBAND ≤ 5 % (p99, pixel noise),
  solid angle 1e-7. No photutils/astroquery/pyvo: apertures are in `spectra/aperture.py` (= photutils to 1e-11).
- `dr1/l3_flux_corrections/` only converts QR2 to the R7 scale: not used with DR1 + QR3.
- eps Ind B through `pipeline/spectrum.run`: 412 points; identical to the notebook on 391 clean images; the
  four passes agree on average; 4 % scatter per point. 42 images skipped for >20 % light on flagged pixels.
- Saturated stars (Barnard, R Dra) cannot be measured with an aperture. Their PSF wings (9–14 px) follow
  the variability in relative units: R Dra gives P = 244.8 d. Barnard shows the wings can fake ±20–30 %
  changes in its most saturated bands, so only large changes are trustworthy (validation notebook 04).
- Variability: compare each star with itself at the same wavelength in other images; comparison stars are
  the "constant star" reference. Per-image zero-point correction is not worth it: the real calibration
  error per image is ~0.4–0.9 %, below the comparison-star noise.
- One spectrum with all 463 images took 11 min from Chile with astropy + fsspec. `data/l2.py` now asks S3
  only for the headers, the IMAGE rows, the FLAGS row index and its compressed rows (4 Range requests, 6
  with variance; RICE decoded with astropy's `Rice1`). Identical pixels, flags and variance to astropy on
  real files; one light curve went from 52 min to ~4 min from Chile.

## Validated on 2026-11-15 (light curves, add/subtract, deploy)

- `/api/variability` (backend, 240 images): eps Ind B no change (5.2 % vs 3.5 % for 12 comparison stars);
  RW Aur variable (41 % vs 3.1 %; passes ×0.86, ×1.01, ×1.22); Barnard no change above 15 % (wings).
  R Dra needed 600 images (`variability_max_images`) for P = 244.6 d, power 0.27.
- Rules in `spectra/variability.py`: wings only when the aperture fails on ≥ 30 % of images
  (`SATURATED_SHARE`); verdict threshold max(3 × comparison scatter, 5 %), 15 % with wings; period only if
  power ≥ 0.25, span ≥ 1.5 P, largest gap < 0.5 P and comparison-star power < 0.1. Comparison stars need
  a 301 × 301 px piece (`variability_cutout_half_px = 150`); 161 px found too few.
- Add/subtract: blink frames also write aligned values as little-endian float16 (`data_url`, NaN =
  flagged or no data); the browser averages groups A and B ignoring NaN.
- Deploy: Vercel (`spherex-blink-umber.vercel.app`) rewrites `/api/*` to Render in `frontend/vercel.json`,
  so the frontend needs no environment variable. `SPHEREX_ALLOWED_ORIGINS` on Render covers direct calls.
  Render free plan: sleeps after 15 idle min, 512 MB, ~0.3 images/s for light curves (~20 min for RW Aur);
  the disk cache is lost on restart.
- CDS (Strasbourg) answered 404 for the Aladin script and its survey tiles on 15 Nov: Aladin is bundled
  from npm and surveys use IRSA URLs. Aladin takes over the element it is mounted on (CSS position), so
  size and pointer listeners live on an outer element (`SkyMap`). Check UI changes in a real browser
  (Playwright with the local Chrome, `channel="chrome"`, swiftshader for WebGL) before committing.
