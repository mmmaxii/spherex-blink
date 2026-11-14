# CLAUDE.md — SPHEREx Blink

Context for AI sessions working on this repo. Read fully before changing code.

## What this is

Public web tool for the NASA Space Apps Challenge 2026, "Planet X and SPHEREx": the user enters RA/Dec (or a
name) and sees a series of SPHEREx images of that patch of sky "like a little video", to spot what moves or
varies. Official test targets: Barnard's Star, Epsilon Indi B, WISE 0855, RW Aur, R Dra.

The team writes the code during the hackathon. **Build step by step with the team; do not implement features
nobody asked for.** Everything in the repo is in English (code, routes, URL parameters, UI text).

## Architecture (decided)

- `frontend/`: React + Vite + TypeScript on Vercel. State lives in the URL (`src/state/urlState.ts`).
  Aladin Lite 3.8.2 from the CDS CDN. API types generated from FastAPI's `/openapi.json` (`npm run gen:api`).
- `backend/`: FastAPI on Render (one instance, us-east, Python 3.12). All settings in `app/config.py`.
  API contract in `app/api/routes.py`; unbuilt endpoints return 501.
- `validation/`: notebooks comparing backend functions with astropy/reproject.

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
