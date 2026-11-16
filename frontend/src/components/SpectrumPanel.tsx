import { useEffect, useRef, useState } from "react";
import { SpectrumInfo } from "../content/explanations";
import { downloadText, fileStem, toCsv } from "../state/download";
import {
  ApiError,
  getSpectrum,
  type SpectrumPoint,
  type SpectrumResult,
  type Target,
} from "../api/client";

interface Props {
  target: Target;
  ready: boolean; // from /api/health: is the photometry built and validated?
}

/** One spectrum per survey pass: comparing passes at the same wavelength shows what varied. */
export function SpectrumPanel({ target, ready }: Props) {
  const [result, setResult] = useState<SpectrumResult | null>(null);
  const [progress, setProgress] = useState<{
    fraction: number;
    stage: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  // Stop listening when the panel goes away (App gives it a new key for each target).
  useEffect(() => () => request.current?.abort(), []);

  function measure() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setResult(null);
    setError(null);
    setProgress({ fraction: 0, stage: "Starting" });
    getSpectrum(
      target,
      (fraction, stage) => setProgress({ fraction, stage }),
      controller.signal,
    )
      .then(setResult)
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          e instanceof ApiError
            ? e.message
            : "The spectrum could not be measured.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setProgress(null);
      });
  }

  return (
    <section className="spectrum">
      <h2>Spectrum</h2>
      {!ready ? (
        <p className="muted">
          Measuring the spectrum of the object from these images (0.75–5 µm, one
          per survey pass) is being validated and is not available yet.
        </p>
      ) : !progress && !result ? (
        <button onClick={measure}>Measure the spectrum from the images</button>
      ) : null}
      {progress && (
        <p className="progress">
          <progress value={progress.fraction} /> {progress.stage}
        </p>
      )}
      {error && <p className="notice">{error}</p>}
      {result && (
        <>
          <SpectrumChart result={result} />
          <p className="actions">
            <button onClick={() => downloadSpectrum(result, target)}>
              Download the spectrum data (CSV)
            </button>
          </p>
        </>
      )}
    </section>
  );
}

/** Every measured point as a CSV table: one line per image, with its errors and quality flags. */
function downloadSpectrum(result: SpectrumResult, target: Target) {
  const columns = [
    "lambda_um",
    "bandwidth_um",
    "flux_mjy",
    "flux_err_mjy",
    "stat_err_mjy",
    "pass_index",
    "mjd",
    "date_utc",
    "detector",
    "collection",
    "obs_id",
    "background_mjysr",
    "n_bad_px",
    "lost_fraction",
    "suspect",
    "lambda_source",
    "flags",
  ] as const;
  const rows = result.points.map((p) =>
    columns.map((c) => (c === "flags" ? p.flags.join(";") : p[c])),
  );
  const comments = [
    `SPHEREx Blink spectrum of ${target.name ?? "a position"} (RA ${target.ra_deg.toFixed(6)} deg, Dec ${target.dec_deg.toFixed(6)} deg)`,
    `Data: ${result.collections.join(" + ")} (NASA/IPAC IRSA, DOI 10.26131/IRSA678). One line per image.`,
    "flux_err_mjy includes a 3 % calibration term in quadrature; stat_err_mjy is the statistical part only.",
    "suspect = far from the same-pass points at the same wavelength (shown hollow on the page).",
  ];
  downloadText(
    `spherex-spectrum-${fileStem(target)}.csv`,
    toCsv(comments, [...columns], rows),
  );
}

// Categorical slots 1–3 of the palette validated for scatter plots (all pairs, light and dark).
// Passes beyond the third use neutral ink; every pass also has its own shape, so identity never
// depends on colour alone.
const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
const W = 640;
const H = 300;
const M = { left: 56, right: 12, top: 12, bottom: 40 };
const X_RANGE_UM = [0.7, 5.1] as const;

function shape(
  index: number,
  cx: number,
  cy: number,
  color: string,
  title: string,
  hollow = false,
) {
  // Hollow = suspect point: drawn in its pass colour but empty, so it is visible yet clearly apart.
  const common = hollow
    ? { fill: "var(--bg)", stroke: color, strokeWidth: 1.5 }
    : { fill: color, stroke: "var(--bg)", strokeWidth: 1 };
  const r = 4;
  const kind = index % 4;
  return (
    <g>
      <title>{title}</title>
      {kind === 0 && <circle cx={cx} cy={cy} r={r} {...common} />}
      {kind === 1 && (
        <rect
          x={cx - r + 0.5}
          y={cy - r + 0.5}
          width={2 * r - 1}
          height={2 * r - 1}
          {...common}
        />
      )}
      {kind === 2 && (
        <path
          d={`M ${cx} ${cy - r - 1} L ${cx + r + 1} ${cy} L ${cx} ${cy + r + 1} L ${cx - r - 1} ${cy} Z`}
          {...common}
        />
      )}
      {kind === 3 && (
        <path
          d={`M ${cx} ${cy - r - 1} L ${cx + r + 1} ${cy + r} L ${cx - r - 1} ${cy + r} Z`}
          {...common}
        />
      )}
    </g>
  );
}

function niceTicks(max: number): number[] {
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step =
    [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? rough;
  return Array.from({ length: Math.floor(max / step) + 1 }, (_, i) => i * step);
}

/**
 * Vertical scale of the chart. Logarithmic by default: a spectrum spans several powers of ten
 * (eps Ind B goes from 0.01 to 60 mJy), and a linear axis flattens the faint end.
 */
function yScale(fluxes: number[], top: number, logScale: boolean) {
  const plotHeight = H - M.top - M.bottom;
  if (!logScale) {
    const max = top * 1.08 || 1;
    return {
      y: (mjy: number) => H - M.bottom - (Math.max(mjy, 0) / max) * plotHeight,
      ticks: niceTicks(max),
    };
  }
  const positive = fluxes.filter((f) => f > 0);
  const high = Math.log10(top * 1.3 || 1);
  const low = Math.max(Math.log10(Math.min(...positive, top) * 0.7), high - 5); // at most 5 decades
  const y = (mjy: number) => {
    const value = Math.min(
      Math.max(Math.log10(Math.max(mjy, 1e-12)), low),
      high,
    );
    return H - M.bottom - ((value - low) / (high - low)) * plotHeight;
  };
  const ticks = [];
  for (let power = Math.ceil(low); power <= Math.floor(high); power++)
    ticks.push(10 ** power);
  return { y, ticks };
}

/** "103 images left out: 95 saturated or flagged at the target, 8 at the detector edge". */
function skippedSummary(skipped: SpectrumResult["skipped"]): string | null {
  if (skipped.length === 0) return null;
  const counts = new Map<string, number>();
  for (const s of skipped) {
    const reason = s.reason.includes("light falls on flagged pixels")
      ? "saturated or flagged at the target"
      : s.reason;
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  const parts = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([r, n]) => `${n} ${r}`);
  return `${skipped.length} images left out: ${parts.join(", ")}.`;
}

function SpectrumChart({ result }: { result: SpectrumResult }) {
  const [logScale, setLogScale] = useState(true);
  const points = result.points.filter((p) => Number.isFinite(p.flux_mjy));
  if (points.length === 0)
    return <p className="notice">No image gave a usable measurement.</p>;
  const passes = result.passes.map((p) => p.pass_index);
  const color = (pass: number) =>
    SERIES[passes.indexOf(pass)] ?? "var(--muted)";
  // The scale follows the trusted points: one cosmic ray must not flatten the whole spectrum.
  const trusted = points.filter((p) => !p.suspect);
  const scaleOn = trusted.length > 0 ? trusted : points;
  const top = Math.max(
    ...scaleOn.map((p) => p.flux_mjy + (p.flux_err_mjy || 0)),
  );
  const { y, ticks } = yScale(
    scaleOn.map((p) => p.flux_mjy),
    top,
    logScale,
  );
  const nSuspect = points.length - trusted.length;
  const leftOut = skippedSummary(result.skipped);
  const x = (um: number) =>
    M.left +
    ((um - X_RANGE_UM[0]) / (X_RANGE_UM[1] - X_RANGE_UM[0])) *
      (W - M.left - M.right);
  const describe = (p: SpectrumPoint) =>
    `${p.lambda_um.toFixed(3)} µm: ${p.flux_mjy.toFixed(2)} ± ${p.flux_err_mjy.toFixed(2)} mJy · ${p.date_utc.slice(0, 10)} · pass ${p.pass_index + 1}` +
    (p.suspect ? " · suspect (far from the same pass)" : "");

  return (
    <figure>
      <div className="legend">
        {passes.map((pass, i) => (
          <span key={pass}>
            <svg
              width="14"
              height="14"
              viewBox="-7 -7 14 14"
              aria-hidden="true"
            >
              {shape(i, 0, 0, color(pass), "")}
            </svg>
            Pass {pass + 1}
          </span>
        ))}
        {nSuspect > 0 && (
          <span>
            <svg
              width="14"
              height="14"
              viewBox="-7 -7 14 14"
              aria-hidden="true"
            >
              {shape(0, 0, 0, "var(--muted)", "", true)}
            </svg>
            Suspect ({nSuspect})
          </span>
        )}
        <label className="log-toggle">
          <input
            type="checkbox"
            checked={logScale}
            onChange={(e) => setLogScale(e.target.checked)}
          />{" "}
          Log scale
        </label>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Flux against wavelength, one series per survey pass"
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              className="grid"
              x1={M.left}
              x2={W - M.right}
              y1={y(tick)}
              y2={y(tick)}
            />
            <text
              className="tick"
              x={M.left - 6}
              y={y(tick) + 4}
              textAnchor="end"
            >
              {tick < 1 ? tick.toPrecision(1) : tick}
            </text>
          </g>
        ))}
        {[1, 2, 3, 4, 5].map((um) => (
          <text
            key={um}
            className="tick"
            x={x(um)}
            y={H - M.bottom + 16}
            textAnchor="middle"
          >
            {um}
          </text>
        ))}
        <text
          className="axis"
          x={(M.left + W - M.right) / 2}
          y={H - 6}
          textAnchor="middle"
        >
          Wavelength (µm)
        </text>
        <text
          className="axis"
          transform={`translate(14 ${(M.top + H - M.bottom) / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          Flux (mJy)
        </text>
        {points.map((p) => (
          <line
            key={`e-${p.obs_id}-${p.detector}`}
            x1={x(p.lambda_um)}
            x2={x(p.lambda_um)}
            y1={y(p.flux_mjy - p.flux_err_mjy)}
            y2={y(p.flux_mjy + p.flux_err_mjy)}
            stroke={color(p.pass_index)}
            strokeWidth={1}
          />
        ))}
        {points.map((p) => (
          <g key={`p-${p.obs_id}-${p.detector}`}>
            {shape(
              passes.indexOf(p.pass_index),
              x(p.lambda_um),
              y(p.flux_mjy),
              color(p.pass_index),
              describe(p),
              p.suspect,
            )}
          </g>
        ))}
      </svg>
      <p className="small muted">
        {points.length} points, one per image.{leftOut && ` ${leftOut}`}
      </p>
      {result.classification && (
        <p>
          Looks like: <strong>{result.classification.label}</strong>
          {result.classification.probability !== null &&
            result.classification.probability !== undefined &&
            ` (${(result.classification.probability * 100).toFixed(0)} %, ${result.classification.method})`}
        </p>
      )}
      <details className="notes">
        <summary>Table of measurements ({points.length})</summary>
        <table>
          <thead>
            <tr>
              <th>Wavelength (µm)</th>
              <th>Flux (mJy)</th>
              <th>Error (mJy)</th>
              <th>Date</th>
              <th>Pass</th>
              <th>Detector</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={`${p.obs_id}-${p.detector}`}>
                <td>{p.lambda_um.toFixed(4)}</td>
                <td>{p.flux_mjy.toFixed(3)}</td>
                <td>{p.flux_err_mjy.toFixed(3)}</td>
                <td>{p.date_utc.slice(0, 10)}</td>
                <td>{p.pass_index + 1}</td>
                <td>{p.detector}</td>
                <td>
                  {[
                    p.suspect ? "suspect" : "",
                    p.lost_fraction > 0
                      ? `${(p.lost_fraction * 100).toFixed(0)} % light on flagged pixels (corrected)`
                      : "",
                    p.lambda_source === "wcs-wave"
                      ? "approximate wavelength"
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul>
          {result.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </details>
      <SpectrumInfo />
    </figure>
  );
}
