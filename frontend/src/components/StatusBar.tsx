import { formatDec, formatFov, formatRa } from "../sky/format";
import type { Survey } from "../sky/surveys";

interface Props {
  cursor: { raDeg: number; decDeg: number } | null;
  view: { raDeg: number; decDeg: number; fovDeg: number } | null;
  survey: Survey;
}

/** Bottom line: where the cursor points, how wide the map is, and whose images these are. */
export function StatusBar({ cursor, view, survey }: Props) {
  const point = cursor ?? view;
  return (
    <p className="glass status-bar" aria-live="off">
      <span>
        RA <b>{point ? formatRa(point.raDeg) : "--"}</b>
      </span>
      <span>
        Dec <b>{point ? formatDec(point.decDeg) : "--"}</b>
      </span>
      <span>
        Field <b>{view ? formatFov(view.fovDeg) : "--"}</b>
      </span>
      <span>
        {survey.label} · {survey.band}
      </span>
      <span className="muted">
        Map: Aladin Lite (CDS) · images: IRSA
        {survey.note && ` · ${survey.note}`}
      </span>
    </p>
  );
}
