import { useEffect, useRef, useState } from "react";
import type { Target } from "../api/client";

/**
 * The same field as seen by other telescopes, with Aladin Lite (CDS). Aladin is ~1 MB, so it is
 * only downloaded when the person opens this panel. Version pinned to the one tested in the
 * prototype (3.8.2; the npm package is beta only).
 */
const ALADIN_URL =
  "https://aladin.cds.unistra.fr/AladinLite/api/v3/3.8.2/aladin.js";

const SURVEYS = [
  { id: "P/allWISE/color", label: "WISE (mid-infrared)" },
  { id: "P/2MASS/color", label: "2MASS (near-infrared)" },
  { id: "P/DSS2/color", label: "DSS2 (visible light)" },
];

interface AladinView {
  gotoRaDec(ra: number, dec: number): void;
  setFoV(deg: number): void;
  setBaseImageLayer?(id: string): void;
  setImageSurvey?(id: string): void;
}
interface AladinGlobal {
  init: Promise<void>;
  aladin(element: HTMLElement, options: Record<string, unknown>): AladinView;
}

let loading: Promise<AladinGlobal> | null = null;

function loadAladin(): Promise<AladinGlobal> {
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = ALADIN_URL;
    script.charset = "utf-8";
    script.onload = () => {
      const A = (window as unknown as { A: AladinGlobal }).A;
      A.init.then(() => resolve(A), reject);
    };
    script.onerror = () => {
      loading = null;
      reject(new Error("Aladin Lite could not be loaded."));
    };
    document.head.append(script);
  });
  return loading;
}

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
  const [survey, setSurvey] = useState(SURVEYS[0].id);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || !box.current) return;
    let cancelled = false;
    const fovDeg = fovArcmin / 60;
    if (view.current) {
      view.current.gotoRaDec(target.ra_deg, target.dec_deg);
      view.current.setFoV(fovDeg);
      return;
    }
    loadAladin()
      .then((A) => {
        if (cancelled || !box.current || view.current) return;
        view.current = A.aladin(box.current, {
          survey,
          fov: fovDeg,
          target: `${target.ra_deg} ${target.dec_deg}`,
          cooFrame: "ICRSd",
          showReticle: true,
          showCooGrid: false,
          showProjectionControl: false,
          showFullscreenControl: false,
          showLayersControl: false,
        });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
    };
    // `survey` is applied by changeSurvey; it only matters here for the first view.
  }, [open, target, fovArcmin]); // eslint-disable-line react-hooks/exhaustive-deps

  const changeSurvey = (id: string) => {
    setSurvey(id);
    if (view.current?.setBaseImageLayer) view.current.setBaseImageLayer(id);
    else view.current?.setImageSurvey?.(id);
  };

  return (
    <details className="notes" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>The same field seen by other telescopes</summary>
      <label>
        Survey{" "}
        <select value={survey} onChange={(e) => changeSurvey(e.target.value)}>
          {SURVEYS.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      {failed ? (
        <p className="notice">The sky map could not be loaded.</p>
      ) : (
        <div ref={box} className="aladin" />
      )}
      <p className="muted small">
        Sky map by Aladin Lite (CDS, Strasbourg). These surveys were taken years
        before SPHEREx: a fast object will not be where the SPHEREx images show
        it.
      </p>
    </details>
  );
}
