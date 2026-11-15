/**
 * Sky surveys the map can show, from ultraviolet to far infrared, so the same patch of sky can be
 * compared across wavelengths.
 *
 * Every map is a HiPS (hierarchical tiles of the whole sky) served by IRSA, with CORS open. They
 * are given as full URLs on purpose: with a short ID Aladin asks CDS for mirrors, and on 15 Nov 2026
 * the CDS servers answered 404. IRSA keeps copies of the CDS surveys under /data/hips/CDS/.
 * Checked on 15 Nov 2026 with `curl .../properties` (HTTP 200, Access-Control-Allow-Origin: *).
 */

export interface Survey {
  id: string; // short key, kept in the browser
  label: string; // button text
  band: string; // wavelength range shown under the label
  url: string; // HiPS base URL
  note?: string;
}

const IRSA = "https://irsa.ipac.caltech.edu/data/hips";

export const SURVEYS: Survey[] = [
  {
    id: "galex",
    label: "GALEX",
    band: "UV · 0.15–0.28 µm",
    url: `${IRSA}/CDS/GALEX/GR6-03-2014/AIS-Color`,
    note: "Patches only: GALEX avoided the Milky Way plane.",
  },
  { id: "dss2", label: "DSS2", band: "Visible · 0.4–0.7 µm", url: `${IRSA}/CDS/DSS2/color` },
  { id: "2mass", label: "2MASS", band: "Near-IR · 1.2–2.2 µm", url: `${IRSA}/CDS/2MASS/Color` },
  {
    id: "spherex",
    label: "SPHEREx",
    band: "0.75–5 µm · all-sky cube",
    url: `${IRSA}/SPHEREx/spherex_allsky_cube`,
    note: "SPHEREx DR1 all-sky cube (first wavelength channel shown); the analysis uses the individual images.",
  },
  { id: "irac", label: "Spitzer", band: "IRAC 3.6 µm", url: `${IRSA}/CDS/SPITZER/IRAC1`, note: "Partial coverage." },
  { id: "allwise", label: "WISE", band: "Mid-IR · 3.4–22 µm", url: `${IRSA}/CDS/AllWISE/RGB-W4-W2-W1` },
  {
    id: "herschel",
    label: "Herschel",
    band: "Far-IR · 70–160 µm",
    url: `${IRSA}/ESAC/PACS-color`,
    note: "Partial coverage.",
  },
  { id: "planck", label: "Planck", band: "Sub-mm · 0.35–3 mm", url: `${IRSA}/CDS/PLANCK/R2/HFI/color` },
];

export const DEFAULT_SURVEY = SURVEYS.find((s) => s.id === "2mass") ?? SURVEYS[0];

export const surveyById = (id: string | null): Survey =>
  SURVEYS.find((s) => s.id === id) ?? DEFAULT_SURVEY;
