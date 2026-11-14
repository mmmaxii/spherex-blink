# SPHEREx Blink

Web tool to watch the SPHEREx infrared sky change over time: enter sky coordinates, blink images taken on
different dates, and spot objects that move or vary. Built for the NASA Space Apps Challenge 2026
("Planet X and SPHEREx").

> Work in progress. This repository is the project template; features are being built during the hackathon.

## Architecture

```
frontend/   React + Vite + TypeScript  → Vercel (static). /api/* is rewritten to the backend.
backend/    FastAPI (Python 3.12)      → Render, one instance in us-east (next to the SPHEREx S3 bucket).
            Finds images (IRSA SIA2), reads only the needed rows from S3, reprojects, stacks, measures spectra.
validation/ Jupyter notebooks that check each backend function against reference tools (astropy, reproject).
docs/       Notes and decisions.
```

## Run locally

Backend (terminal 1):

```bash
cd backend
uv venv .venv --python 3.12          # or: py -3.12 -m venv .venv
uv pip install -e ".[dev]"           # or: .venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\activate               # macOS/Linux: source .venv/bin/activate
uvicorn app.main:app --reload --port 8000     # docs at http://localhost:8000/docs
pytest
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
