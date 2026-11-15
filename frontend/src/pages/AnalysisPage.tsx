import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  getBlink,
  getCoverage,
  getHealth,
  getOverlay,
  resolveTarget,
  type BlinkResult,
  type Catalog,
  type Coverage,
  type Health,
  type Overlay,
  type Target,
} from "../api/client";
import { ContextMap } from "../components/ContextMap";
import { Player } from "../components/Player";
import { SearchForm, type Query } from "../components/SearchForm";
import { SpectrumPanel } from "../components/SpectrumPanel";
import { AboutMission, DetectorsInfo } from "../content/explanations";
import { rememberAnalysis } from "../state/recent";
import {
  hasQuery,
  readState,
  toSearch,
  writeState,
  type ViewState,
} from "../state/urlState";

// Catalogues that can be drawn over the images (layer names in the URL).
const CATALOGS: Catalog[] = ["gaia", "wise"];

/** Text for the person: the backend's own sentence when there is one. */
const message = (e: unknown) =>
  e instanceof ApiError
    ? e.message
    : "Something went wrong. Try again in a moment.";

/**
 * The full analysis of one field, on its own address (everything is in the query string):
 * position (resolve) → what SPHEREx has there (coverage) → the images (frames job) → spectrum.
 */
export function AnalysisPage({ onHome }: { onHome: () => void }) {
  const [state, setState] = useState<ViewState>(readState);
  const [health, setHealth] = useState<Health | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [result, setResult] = useState<BlinkResult | null>(null);
  const [overlays, setOverlays] = useState<Overlay[]>([]);
  const [progress, setProgress] = useState<{
    fraction: number;
    stage: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const overlayRequests = useRef(new Set<string>());
  // A catalogue that could not be loaded: shown next to the player, and its layer is switched off.
  const [overlayError, setOverlayError] = useState<string | null>(null);

  // Every change of option goes through here so the URL always matches the screen.
  const update = (patch: Partial<ViewState>) =>
    setState((previous) => {
      const next = { ...previous, ...patch };
      writeState(next);
      return next;
    });

  // A layer whose catalogue failed is unticked (read from the latest state, not a stale copy).
  const switchOffLayer = (layer: Catalog) =>
    setState((previous) => {
      const next = {
        ...previous,
        layers: previous.layers.filter((l) => l !== layer),
      };
      writeState(next);
      return next;
    });

  // What the backend can do today (the spectrum panel depends on it). Failing is not fatal.
  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(setHealth)
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  // 1. Where is it, and which images does SPHEREx have there?
  useEffect(() => {
    if (!hasQuery(state)) return;
    const controller = new AbortController();
    setTarget(null);
    setCoverage(null);
    setResult(null);
    setError(null);
    setProgress({ fraction: 0, stage: "Finding the position" });
    resolveTarget(
      { name: state.target, ra: state.ra, dec: state.dec },
      controller.signal,
    )
      .then(async (found) => {
        setTarget(found);
        setProgress({
          fraction: 0.01,
          stage: "Asking the archive which images exist",
        });
        setCoverage(await getCoverage(found, controller.signal));
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(message(e));
        setProgress(null);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.target, state.ra, state.dec]);

  // Keep this analysis in the browser's recent list (the menu of the sky page).
  useEffect(() => {
    if (!target || !coverage || state.embed) return;
    rememberAnalysis({
      label:
        target.name ??
        `${target.ra_deg.toFixed(3)}°, ${target.dec_deg.toFixed(3)}°`,
      search: toSearch({ ...state, view: "frames", layers: ["marker"] }),
      raDeg: target.ra_deg,
      decDeg: target.dec_deg,
      fovArcmin: state.fovArcmin,
      nImages: coverage.n_images,
      savedAt: new Date().toISOString(),
    });
    // Saved once per field; changes of view or layers do not make a new entry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, coverage]);

  // The detector shown: the one in the URL when it has images, otherwise the one with most images.
  const detector = coverage
    ? (coverage.detectors.find((d) => d.detector === state.detector)
        ?.detector ??
      coverage.detectors.reduce((best, d) =>
        d.n_images > best.n_images ? d : best,
      ).detector)
    : null;

  // 2. The images themselves (a background job on the server; progress is reported).
  useEffect(() => {
    if (!target || detector === null) return;
    const controller = new AbortController();
    setResult(null);
    setError(null);
    getBlink(
      target,
      { fovArcmin: state.fovArcmin, detector },
      (fraction, stage) => setProgress({ fraction, stage }),
      controller.signal,
    )
      .then(setResult)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setProgress(null);
      });
    return () => controller.abort();
  }, [target, detector, state.fovArcmin]);

  // 3. Catalogues from other missions, loaded the first time their layer is switched on.
  useEffect(() => {
    setOverlays([]);
    overlayRequests.current.clear();
  }, [target, state.fovArcmin]);
  useEffect(() => {
    if (!target) return;
    for (const catalog of CATALOGS) {
      const key = `${catalog}|${target.ra_deg}|${target.dec_deg}|${state.fovArcmin}`;
      if (!state.layers.includes(catalog) || overlayRequests.current.has(key))
        continue;
      overlayRequests.current.add(key);
      getOverlay(target, state.fovArcmin, catalog)
        .then((overlay) => {
          if (overlayRequests.current.has(key))
            setOverlays((all) => [...all, overlay]);
        })
        .catch((e: unknown) => {
          overlayRequests.current.delete(key); // allow a new try later
          setOverlayError(
            `${catalog === "gaia" ? "Gaia" : "WISE"} layer: ${message(e)}`,
          );
          switchOffLayer(catalog);
        });
    }
  }, [target, state.fovArcmin, state.layers]);

  // A new search forgets the detector, so the one with most images is picked again.
  const search = (query: Query) => update({ ...query, detector: null });
  const copyLink = () => {
    void navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  const embedUrl = `${window.location.origin}${window.location.pathname}${toSearch({ ...state, embed: true })}`;

  return (
    <main className={state.embed ? "shell embed" : "shell"}>
      {!state.embed && (
        <>
          <header>
            <button className="link-button back" onClick={onHome}>
              ← Back to the sky map
            </button>
            <h1>SPHEREx Blink</h1>
            <p>
              How this patch of the infrared sky changed between the dates
              NASA's SPHEREx telescope looked at it.
            </p>
          </header>
          <AboutMission />
          {/* The field is chosen on the sky map; here it can still be changed by hand. */}
          <details className="notes">
            <summary>Change position or field of view</summary>
            <SearchForm
              initial={state}
              busy={progress !== null}
              onSearch={search}
            />
          </details>
        </>
      )}

      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      {progress && (
        <p className="progress" role="status">
          <progress value={progress.fraction} /> {progress.stage}…
        </p>
      )}

      {target && !state.embed && (
        <p className="target">
          <strong>{target.name ?? "Position"}</strong> · RA{" "}
          {target.ra_deg.toFixed(5)}° Dec {target.dec_deg.toFixed(5)}°
          {target.pm_ra_masyr !== null && target.pm_dec_masyr !== null && (
            <span className="muted">
              {" "}
              · moves{" "}
              {(
                Math.hypot(target.pm_ra_masyr, target.pm_dec_masyr) / 1000
              ).toFixed(2)}
              ″ per year (field centred on where it was in January 2026)
            </span>
          )}
        </p>
      )}

      {coverage && (
        <div
          className="detectors"
          role="group"
          aria-label="Detector (wavelength range)"
        >
          {coverage.detectors.map((d) => (
            <button
              key={d.detector}
              aria-pressed={d.detector === detector}
              onClick={() => update({ detector: d.detector })}
              title={`${d.n_images} images`}
            >
              D{d.detector}
              <small>
                {d.lambda_min_um.toFixed(2)}–{d.lambda_max_um.toFixed(2)} µm ·{" "}
                {d.n_images}
              </small>
            </button>
          ))}
        </div>
      )}
      {coverage && !state.embed && <DetectorsInfo />}

      {result && (
        <Player
          key={result.key}
          result={result}
          view={state.view}
          layers={state.layers}
          overlays={overlays}
          onView={(view) => update({ view })}
          onLayers={(layers) => update({ layers })}
        />
      )}

      {overlayError && (
        <p className="notice small" role="alert">
          {overlayError}
        </p>
      )}

      {result && target && !state.embed && (
        <>
          <ContextMap target={target} fovArcmin={state.fovArcmin} />
          <SpectrumPanel
            key={`${target.ra_deg},${target.dec_deg}`}
            target={target}
            ready={health?.spectrum_ready ?? false}
          />
          <details className="notes">
            <summary>Share or embed this view</summary>
            <p>
              The address of this page holds everything you see (position,
              field, detector, layers).{" "}
              <button onClick={copyLink}>
                {copied ? "Copied" : "Copy link"}
              </button>
            </p>
            <p>To embed it in another site:</p>
            <pre>{`<iframe src="${embedUrl}" width="640" height="820" style="border:0"></iframe>`}</pre>
          </details>
        </>
      )}

      {state.embed ? (
        <p className="muted small">
          <a
            href={`${window.location.pathname}${toSearch({ ...state, embed: false })}`}
            target="_blank"
            rel="noreferrer"
          >
            Open in SPHEREx Blink
          </a>
        </p>
      ) : (
        <footer className="muted small">
          {coverage && (
            <p>
              {coverage.n_images} SPHEREx images cover this position in{" "}
              {coverage.passes.length} survey passes (
              {coverage.collections
                .map((c) => c.replace("spherex_", "").toUpperCase())
                .join(" + ")}
              ).
            </p>
          )}
          <p>
            Data: SPHEREx spectral images from the NASA/IPAC Infrared Science
            Archive (
            <a href="https://www.ipac.caltech.edu/doi/10.26131/IRSA678">
              DOI 10.26131/IRSA678
            </a>
            ). Names by SIMBAD/Sesame (CDS), catalogues by ESA Gaia and NASA
            WISE. Built for the NASA Space Apps Challenge 2026.
          </p>
        </footer>
      )}
    </main>
  );
}
