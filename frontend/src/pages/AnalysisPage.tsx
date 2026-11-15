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
import { LayerToggles, Player } from "../components/Player";
import { SearchForm, type Query } from "../components/SearchForm";
import { SpectrumPanel } from "../components/SpectrumPanel";
import { VariabilityPanel } from "../components/VariabilityPanel";
import {
  AboutMission,
  DetectorsInfo,
  PlayerInfo,
} from "../content/explanations";
import { rememberAnalysis } from "../state/recent";
import {
  FOV_ARCMIN_OPTIONS,
  hasQuery,
  readState,
  toSearch,
  writeState,
  type ViewState,
} from "../state/urlState";

// Catalogues that can be drawn over the images (layer names in the URL).
const CATALOGS: Catalog[] = ["gaia", "wise"];

/** The four ways of looking at the field; they share the big stage of the page. */
type StageTab = "blink" | "surveys" | "spectrum" | "variability";
const STAGE_TABS: { id: StageTab; label: string }[] = [
  { id: "blink", label: "Blink" },
  { id: "surveys", label: "Other telescopes" },
  { id: "spectrum", label: "Spectrum" },
  { id: "variability", label: "Brightness changes" },
];

/** Text for the person: the backend's own sentence when there is one. */
const message = (e: unknown) =>
  e instanceof ApiError
    ? e.message
    : "Something went wrong. Try again in a moment.";

/**
 * The full analysis of one field, on its own address (everything is in the query string):
 * position (resolve) → what SPHEREx has there (coverage) → the images (frames job) → spectrum.
 *
 * Layout: a top bar, a rail with every control on the left and one big stage on the right, where
 * the four views (blink, other telescopes, spectrum, brightness changes) take turns. Background
 * notes open in a dialog. Embedded in another site (`embed=1`) the page keeps one short column.
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
  const [tab, setTab] = useState<StageTab>("blink");
  const [notesOpen, setNotesOpen] = useState(false);
  const overlayRequests = useRef(new Set<string>());
  // A catalogue that could not be loaded: shown next to the layers, and its layer is switched off.
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

  // --- pieces used by both layouts ------------------------------------------------------------

  const notices = (
    <>
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
    </>
  );

  const detectorButtons = coverage && (
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
  );

  const overlayNotice = overlayError && (
    <p className="notice small" role="alert">
      {overlayError}
    </p>
  );

  // --- embedded in another site (iframe): the short one-column layout, as before --------------

  if (state.embed)
    return (
      <main className="shell embed">
        {notices}
        {detectorButtons}
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
        {overlayNotice}
        <p className="muted small">
          <a
            href={`${window.location.pathname}${toSearch({ ...state, embed: false })}`}
            target="_blank"
            rel="noreferrer"
          >
            Open in SPHEREx Blink
          </a>
        </p>
      </main>
    );

  // --- full page: top bar, rail of controls, one big stage ------------------------------------

  // The other views need the position; until it is known only the blink view can be chosen.
  const shownTab: StageTab = target ? tab : "blink";
  const movesArcsecPerYear =
    target && target.pm_ra_masyr !== null && target.pm_dec_masyr !== null
      ? Math.hypot(target.pm_ra_masyr, target.pm_dec_masyr) / 1000
      : null;

  return (
    <main className="workbench">
      <header className="topbar">
        <button className="link-button" onClick={onHome}>
          ← Sky map
        </button>
        <h1>SPHEREx Blink</h1>
        {target && (
          <p className="topbar-target">
            <strong>{target.name ?? "Position"}</strong>{" "}
            <span className="muted">
              RA {target.ra_deg.toFixed(5)}° · Dec {target.dec_deg.toFixed(5)}°
            </span>
          </p>
        )}
        <div className="topbar-actions">
          <button onClick={copyLink}>{copied ? "Copied" : "Copy link"}</button>
          <button onClick={() => setNotesOpen(true)}>
            <span className="info-mark" aria-hidden="true">
              i
            </span>
            Notes and methods
          </button>
        </div>
      </header>

      <div className="workbench-body">
        <aside className="rail" aria-label="Controls">
          <section>
            <h2>{target?.name ?? "Field"}</h2>
            {target ? (
              <dl className="stats">
                <dt>RA</dt>
                <dd>{target.ra_deg.toFixed(5)}°</dd>
                <dt>Dec</dt>
                <dd>{target.dec_deg.toFixed(5)}°</dd>
                {movesArcsecPerYear !== null && (
                  <>
                    <dt>Moves</dt>
                    <dd>
                      {movesArcsecPerYear.toFixed(2)}″ per year{" "}
                      <span className="muted small">
                        (field centred on where it was in January 2026)
                      </span>
                    </dd>
                  </>
                )}
              </dl>
            ) : (
              <p className="muted small">Finding the position…</p>
            )}
            {coverage && (
              <p className="muted small">
                {coverage.n_images} SPHEREx images in {coverage.passes.length}{" "}
                survey passes (
                {coverage.collections
                  .map((c) => c.replace("spherex_", "").toUpperCase())
                  .join(" + ")}
                ).
              </p>
            )}
          </section>

          <section>
            <h3>Field of view</h3>
            <div
              className="fov-buttons"
              role="group"
              aria-label="Field of view"
            >
              {FOV_ARCMIN_OPTIONS.map((fov) => (
                <button
                  key={fov}
                  aria-pressed={fov === state.fovArcmin}
                  onClick={() => update({ fovArcmin: fov })}
                >
                  {fov}′
                </button>
              ))}
            </div>
          </section>

          {coverage && (
            <section>
              <h3>Detector</h3>
              {detectorButtons}
            </section>
          )}

          <section>
            <h3>Layers</h3>
            <LayerToggles
              layers={state.layers}
              overlays={overlays}
              onLayers={(layers) => update({ layers })}
            />
            {overlayNotice}
          </section>

          {/* The field is chosen on the sky map; here it can still be changed by hand. */}
          <details className="notes">
            <summary>Change position</summary>
            <SearchForm
              initial={state}
              busy={progress !== null}
              onSearch={search}
            />
          </details>

          <p className="muted small credits">
            Data: SPHEREx images from NASA/IPAC IRSA (
            <a href="https://www.ipac.caltech.edu/doi/10.26131/IRSA678">
              DOI 10.26131/IRSA678
            </a>
            ). Names by SIMBAD/Sesame (CDS), catalogues by ESA Gaia and NASA
            WISE. Built for the NASA Space Apps Challenge 2026.
          </p>
        </aside>

        <section className="stage-area">
          {notices}
          <div className="tabs stage-tabs" role="tablist" aria-label="View">
            {STAGE_TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={t.id === shownTab}
                disabled={t.id !== "blink" && !target}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Every view stays mounted and is only hidden: a spectrum being measured keeps going
              while another view is on screen. */}
          <div className="stage-view" hidden={shownTab !== "blink"}>
            {result ? (
              <Player
                key={result.key}
                result={result}
                view={state.view}
                layers={state.layers}
                overlays={overlays}
                onView={(view) => update({ view })}
                onLayers={(layers) => update({ layers })}
                compact
              />
            ) : (
              !error && (
                <div className="stage stage-empty">
                  <p>
                    {progress ? `${progress.stage}…` : "Waiting for the images"}
                  </p>
                </div>
              )
            )}
          </div>
          {target && (
            <>
              <div className="stage-view wide" hidden={shownTab !== "surveys"}>
                <ContextMap
                  target={target}
                  fovArcmin={state.fovArcmin}
                  active={shownTab === "surveys"}
                />
              </div>
              <div className="stage-view wide" hidden={shownTab !== "spectrum"}>
                <SpectrumPanel
                  key={`${target.ra_deg},${target.dec_deg}`}
                  target={target}
                  ready={health?.spectrum_ready ?? false}
                />
              </div>
              <div
                className="stage-view wide"
                hidden={shownTab !== "variability"}
              >
                <VariabilityPanel
                  key={`v-${target.ra_deg},${target.dec_deg}`}
                  target={target}
                />
              </div>
            </>
          )}
        </section>
      </div>

      <NotesDialog
        open={notesOpen}
        onClose={() => setNotesOpen(false)}
        embedUrl={embedUrl}
      />
    </main>
  );
}

/** Background and method notes, out of the way of the pictures: opened from the top bar. */
function NotesDialog({
  open,
  onClose,
  embedUrl,
}: {
  open: boolean;
  onClose: () => void;
  embedUrl: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);

  // A native <dialog>: Escape closes it and focus stays inside while it is open.
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    if (!open && element.open) element.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className="glass info"
      onClose={onClose}
      aria-labelledby="notes-title"
    >
      <form method="dialog" className="panel-title">
        <h2 id="notes-title">Notes and methods</h2>
        <button className="info-button" aria-label="Close">
          ✕
        </button>
      </form>
      <p className="muted">
        How this patch of the infrared sky changed between the dates NASA's
        SPHEREx telescope looked at it.
      </p>
      <AboutMission />
      <DetectorsInfo />
      <PlayerInfo />
      <h3>Share or embed this view</h3>
      <p className="small">
        The address of the page holds everything you see (position, field,
        detector, layers). To embed it in another site:
      </p>
      <pre>{`<iframe src="${embedUrl}" width="640" height="820" style="border:0"></iframe>`}</pre>
    </dialog>
  );
}
