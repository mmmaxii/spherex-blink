import { useState, type FormEvent } from "react";
import type { BlinkResult, Coverage, Target } from "../api/client";
import { formatDec, formatFov, formatRa } from "../sky/format";
import { PreviewLoop } from "./PreviewLoop";
import type { SkySelection } from "./SkyMap";

/** What the quick look is doing, shown in the panel. */
export type QuickLook =
  | { status: "idle" }
  | { status: "running"; fraction: number; stage: string }
  | {
      status: "done";
      target: Target;
      coverage: Coverage;
      result: BlinkResult;
      search: string;
    }
  | { status: "error"; message: string };

// The official test targets of the challenge, one click away.
const TEST_TARGETS = [
  "Barnard's Star",
  "eps Ind B",
  "WISE J085510.83-071442.5",
  "RW Aur",
  "R Dra",
];
const SHORT_NAMES: Record<string, string> = {
  "WISE J085510.83-071442.5": "WISE 0855",
};

interface Props {
  live: SkySelection | null; // follows the cursor until the person clicks
  picked: SkySelection | null; // fixed by a click on the map
  viewFovDeg: number | null; // what the map shows now
  quickLook: QuickLook;
  onAnalyse: () => void;
  onUnpick: () => void;
  onFind: (name: string) => void; // move the map to a named object and pick it
  onOpenFull: (search: string) => void;
}

/** One row of the coordinates table. */
function Field({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>
        {value}
        {hint && <small> {hint}</small>}
      </dd>
    </div>
  );
}

/**
 * Right-hand panel: the field to analyse. While the cursor moves over the map the numbers follow
 * it; a left click fixes them (the cursor can then travel to the button without changing them).
 */
export function SelectionPanel(props: Props) {
  const { live, picked, viewFovDeg, quickLook } = props;
  const shown = picked ?? live;
  const [name, setName] = useState("");

  const find = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim()) props.onFind(name.trim());
  };

  return (
    <aside className="glass selection" aria-label="Field to analyse">
      <h2>Select a part of the sky</h2>
      <p className="muted small">
        {picked
          ? "Field fixed. Click elsewhere on the map to change it."
          : "Move over the map: the numbers follow the cursor. Click (or tap) to fix them."}
      </p>

      <dl className="fields">
        <Field
          label="RA"
          value={shown ? formatRa(shown.raDeg) : "—"}
          hint={shown ? `${shown.raDeg.toFixed(4)}°` : undefined}
        />
        <Field
          label="Dec"
          value={shown ? formatDec(shown.decDeg) : "—"}
          hint={shown ? `${shown.decDeg.toFixed(4)}°` : undefined}
        />
        <Field
          label="Field"
          value={shown ? `${shown.fovArcmin}′ × ${shown.fovArcmin}′` : "—"}
          hint={
            viewFovDeg !== null
              ? `(map shows ${formatFov(viewFovDeg)}; analysis 3–20′)`
              : undefined
          }
        />
      </dl>

      <div className="actions">
        <button
          className="primary"
          disabled={!picked || quickLook.status === "running"}
          onClick={props.onAnalyse}
        >
          Analyse this field
        </button>
        {picked && (
          <button className="link-button" onClick={props.onUnpick}>
            Follow the cursor again
          </button>
        )}
      </div>

      {/* The result comes right under the button, before the name search. */}
      {quickLook.status === "running" && (
        <p className="progress" role="status">
          <progress value={quickLook.fraction} /> {quickLook.stage}…
        </p>
      )}
      {quickLook.status === "error" && (
        <p className="notice" role="alert">
          {quickLook.message}
        </p>
      )}
      {quickLook.status === "done" && (
        <section className="quick-look" aria-label="Preview">
          <PreviewLoop result={quickLook.result} />
          <p className="small">
            <strong>{quickLook.target.name ?? "This position"}</strong>:{" "}
            {quickLook.coverage.n_images} SPHEREx images in{" "}
            {quickLook.coverage.passes.length} survey passes. Preview: detector{" "}
            {quickLook.result.detector}, {quickLook.result.frames.length}{" "}
            images.
          </p>
          <button
            className="primary"
            onClick={() => props.onOpenFull(quickLook.search)}
          >
            Full analysis →
          </button>
        </section>
      )}
      <form className="find" onSubmit={find}>
        <label htmlFor="find-name" className="small muted">
          Or go to an object by name
        </label>
        <div className="find-row">
          <input
            id="find-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. RW Aur"
            autoComplete="off"
          />
          <button type="submit">Go</button>
        </div>
        <div className="chips" aria-label="Test targets of the challenge">
          {TEST_TARGETS.map((t) => (
            <button
              key={t}
              type="button"
              className="chip"
              onClick={() => props.onFind(t)}
            >
              {SHORT_NAMES[t] ?? t}
            </button>
          ))}
        </div>
      </form>
    </aside>
  );
}
