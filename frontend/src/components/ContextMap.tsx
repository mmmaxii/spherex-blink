import { useEffect, useRef, useState } from "react";
import type { Target } from "../api/client";
import {
  loadAladin,
  QUIET_OPTIONS,
  showSurvey,
  type AladinView,
} from "../sky/aladin";
import { DEFAULT_SURVEY, SURVEYS, surveyById } from "../sky/surveys";
import { SurveysInfo } from "../content/explanations";

/**
 * The same field as seen by other telescopes (Aladin Lite, surveys served by IRSA). The map is
 * created only when the person opens this panel, because the library is large.
 */
export function ContextMap({
  target,
  fovArcmin,
}: {
  target: Target;
  fovArcmin: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const view = useRef<AladinView | null>(null);
  const [open, setOpen] = useState(false);
  const [surveyId, setSurveyId] = useState(DEFAULT_SURVEY.id);
  const [error, setError] = useState<string | null>(null);
  const survey = surveyById(surveyId);

  // Create the map the first time the panel opens; afterwards only move it.
  useEffect(() => {
    if (!open || !box.current) return;
    const fovDeg = (fovArcmin * 2) / 60; // a bit wider than the SPHEREx field, for context
    if (view.current) {
      view.current.gotoRaDec(target.ra_deg, target.dec_deg);
      view.current.setFoV(fovDeg);
      return;
    }
    let cancelled = false;
    loadAladin()
      .then((A) => {
        if (cancelled || !box.current || view.current) return;
        view.current = A.aladin(box.current, {
          ...QUIET_OPTIONS,
          showReticle: true,
          survey: survey.url,
          fov: fovDeg,
          target: `${target.ra_deg} ${target.dec_deg}`,
        });
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      cancelled = true;
    };
    // The survey is applied by its own effect below; here it only sets the first view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, target, fovArcmin]);

  useEffect(() => {
    if (view.current) showSurvey(view.current, survey.url, survey.slice);
  }, [survey]);

  return (
    <details className="notes" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>The same field seen by other telescopes</summary>
      <label>
        Survey{" "}
        <select value={surveyId} onChange={(e) => setSurveyId(e.target.value)}>
          {SURVEYS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label} · {s.band}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p className="notice">{error}</p>
      ) : (
        <div ref={box} className="aladin" />
      )}
      <p className="muted small">
        Sky map by Aladin Lite (CDS, Strasbourg), images served by IRSA. These
        surveys were taken years before SPHEREx: a fast object will not be where
        the SPHEREx images show it.
        {survey.note && ` ${survey.note}`}
      </p>
      <SurveysInfo />
    </details>
  );
}
