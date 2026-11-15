import { useRef, useState } from "react";
import { ApiError, getBlink, getCoverage, resolveTarget } from "../api/client";
import { InfoDialog } from "../components/InfoDialog";
import {
  MAX_FIELD_ARCMIN,
  MIN_FIELD_ARCMIN,
} from "../components/ManualPosition";
import { RecentMenu } from "../components/RecentMenu";
import { SelectionPanel, type QuickLook } from "../components/SelectionPanel";
import { SkyMap, type FlyTo, type SkySelection } from "../components/SkyMap";
import { StatusBar } from "../components/StatusBar";
import { SurveyBar } from "../components/SurveyBar";
import {
  loadRecent,
  rememberAnalysis,
  type RecentAnalysis,
} from "../state/recent";
import { DEFAULT_STATE, toSearch } from "../state/urlState";
import { surveyById, type Survey } from "../sky/surveys";

// First view: the Orion Nebula, bright at every wavelength the map offers.
const START = { raDeg: 83.82, decDeg: -5.39, fovDeg: 2.0 };
const SURVEY_KEY = "spherex-blink:survey"; // last survey chosen, a convenience per browser
const NAME_FIELD_ARCMIN = 6; // field picked when the person goes to an object by name

/** Field to analyse for a map that shows `fovDeg`: the same size, within what the analysis allows. */
function analysisField(fovDeg: number): number {
  return Math.min(
    MAX_FIELD_ARCMIN,
    Math.max(MIN_FIELD_ARCMIN, Math.round(fovDeg * 60)),
  );
}

function savedSurvey(): Survey {
  try {
    return surveyById(localStorage.getItem(SURVEY_KEY));
  } catch {
    return surveyById(null);
  }
}

const sentence = (e: unknown) =>
  e instanceof ApiError
    ? e.message
    : "Something went wrong. Try again in a moment.";

/**
 * Home page: the whole sky to explore. Hovering shows coordinates, a click fixes a field, and
 * "Analyse" makes a quick blink preview with a link to the full analysis page.
 */
export function ExplorePage({ onOpen }: { onOpen: (search: string) => void }) {
  const [survey, setSurvey] = useState<Survey>(savedSurvey);
  const [cursor, setCursor] = useState<{
    raDeg: number;
    decDeg: number;
  } | null>(null);
  const [view, setView] = useState<{
    raDeg: number;
    decDeg: number;
    fovDeg: number;
  } | null>(null);
  const [picked, setPicked] = useState<
    (SkySelection & { name: string | null }) | null
  >(null);
  const [quickLook, setQuickLook] = useState<QuickLook>({ status: "idle" });
  const [recent, setRecent] = useState<RecentAnalysis[]>(loadRecent);
  const [menuOpen, setMenuOpen] = useState(false);
  const [flyTo, setFlyTo] = useState<FlyTo | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const running = useRef<AbortController | null>(null);

  const live: SkySelection | null =
    cursor && view
      ? { ...cursor, fovArcmin: analysisField(view.fovDeg) }
      : null;

  const chooseSurvey = (next: Survey) => {
    setSurvey(next);
    try {
      localStorage.setItem(SURVEY_KEY, next.id);
    } catch {
      // storage blocked: the choice is not remembered, nothing else changes
    }
  };

  const fly = (raDeg: number, decDeg: number, fovDeg: number) =>
    setFlyTo({ id: Date.now(), raDeg, decDeg, fovDeg });

  const pick = (
    raDeg: number,
    decDeg: number,
    name: string | null = null,
    fovArcmin?: number,
  ) => {
    running.current?.abort(); // a new field cancels the preview of the old one
    setPicked({
      raDeg,
      decDeg,
      name,
      fovArcmin: fovArcmin ?? analysisField(view?.fovDeg ?? START.fovDeg),
    });
    setQuickLook({ status: "idle" });
  };

  /** Go to an object by name: the map flies there and the field is fixed on it. */
  const find = async (name: string) => {
    try {
      const target = await resolveTarget({ name, ra: null, dec: null });
      pick(target.ra_deg, target.dec_deg, name, NAME_FIELD_ARCMIN);
      fly(target.ra_deg, target.dec_deg, (NAME_FIELD_ARCMIN * 4) / 60);
    } catch (e) {
      setQuickLook({ status: "error", message: sentence(e) });
    }
  };

  /** A position typed by hand: the backend reads the format, the map shows the field. */
  const previewTyped = async (ra: string, dec: string, fovArcmin: number) => {
    const field = Math.min(
      MAX_FIELD_ARCMIN,
      Math.max(MIN_FIELD_ARCMIN, Math.round(fovArcmin)),
    );
    try {
      const target = await resolveTarget({ name: null, ra, dec });
      pick(target.ra_deg, target.dec_deg, null, field);
      fly(target.ra_deg, target.dec_deg, (field * 4) / 60);
    } catch (e) {
      setQuickLook({ status: "error", message: sentence(e) });
    }
  };

  /** New size for the fixed field (the square on the map follows). */
  const resizeField = (fovArcmin: number) => {
    if (!picked) return;
    running.current?.abort(); // the preview was for the old size
    setPicked({ ...picked, fovArcmin });
    setQuickLook({ status: "idle" });
  };

  /** The quick look: position → what SPHEREx has there → a blink of the detector with most images. */
  const analyse = async () => {
    if (!picked) return;
    running.current?.abort();
    const controller = new AbortController();
    running.current = controller;
    const progress = (fraction: number, stage: string) =>
      setQuickLook({ status: "running", fraction, stage });
    try {
      progress(0, "Finding the position");
      // A name is resolved again so fast stars are followed with their proper motion.
      const where = picked.name
        ? { name: picked.name, ra: null, dec: null }
        : {
            name: null,
            ra: picked.raDeg.toFixed(6),
            dec: picked.decDeg.toFixed(6),
          };
      const target = await resolveTarget(where, controller.signal);

      progress(0.02, "Asking the archive which images exist");
      const coverage = await getCoverage(target, controller.signal);
      if (coverage.detectors.length === 0)
        throw new Error("SPHEREx has no images of this field yet.");
      const detector = coverage.detectors.reduce((best, d) =>
        d.n_images > best.n_images ? d : best,
      ).detector;

      const result = await getBlink(
        target,
        { fovArcmin: picked.fovArcmin, detector },
        progress,
        controller.signal,
      );

      // The full analysis page opens with exactly this field and detector.
      const search = toSearch({
        ...DEFAULT_STATE,
        target: where.name,
        ra: where.ra,
        dec: where.dec,
        fovArcmin: picked.fovArcmin,
        detector,
      });
      setRecent(
        rememberAnalysis({
          label:
            target.name ??
            `${target.ra_deg.toFixed(3)}°, ${target.dec_deg.toFixed(3)}°`,
          search,
          raDeg: target.ra_deg,
          decDeg: target.dec_deg,
          fovArcmin: picked.fovArcmin,
          nImages: coverage.n_images,
          savedAt: new Date().toISOString(),
        }),
      );
      setQuickLook({ status: "done", target, coverage, result, search });
    } catch (e) {
      if (controller.signal.aborted) return;
      setQuickLook({
        status: "error",
        message:
          e instanceof Error && !(e instanceof ApiError)
            ? e.message
            : sentence(e),
      });
    }
  };

  return (
    <div className="explore">
      <SkyMap
        survey={survey}
        initial={START}
        selection={picked}
        flyTo={flyTo}
        onPointer={(raDeg, decDeg) => setCursor({ raDeg, decDeg })}
        onView={(raDeg, decDeg, fovDeg) => setView({ raDeg, decDeg, fovDeg })}
        onPick={(raDeg, decDeg) => pick(raDeg, decDeg)}
        onError={setMapError}
      />
      {mapError && (
        <p className="glass map-error" role="alert">
          {mapError}
        </p>
      )}
      <RecentMenu
        open={menuOpen}
        recent={recent}
        onToggle={() => setMenuOpen((open) => !open)}
        onOpen={onOpen}
        onShow={(entry) => {
          fly(entry.raDeg, entry.decDeg, (entry.fovArcmin * 4) / 60);
          pick(entry.raDeg, entry.decDeg, null, entry.fovArcmin);
          setMenuOpen(false);
        }}
      />
      <SurveyBar current={survey} onChange={chooseSurvey} />
      <SelectionPanel
        live={live}
        picked={picked}
        viewFovDeg={view?.fovDeg ?? null}
        quickLook={quickLook}
        onAnalyse={() => void analyse()}
        onUnpick={() => {
          running.current?.abort();
          setPicked(null);
          setQuickLook({ status: "idle" });
        }}
        onFind={(name) => void find(name)}
        onManual={(ra, dec, fov) => void previewTyped(ra, dec, fov)}
        onFieldChange={resizeField}
        onInfo={() => setInfoOpen(true)}
        onOpenFull={onOpen}
      />
      <StatusBar cursor={cursor} view={view} survey={survey} />
      <InfoDialog open={infoOpen} onClose={() => setInfoOpen(false)} />
    </div>
  );
}
