import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  getVariability,
  type Target,
  type VariabilityResult,
} from "../api/client";
import { InfoNote } from "./InfoNote";

/**
 * "Does it change?": the target measured on every image, divided by itself at the same wavelength
 * in the other images, next to comparison stars of the same images (what constant looks like).
 */
export function VariabilityPanel({ target }: { target: Target }) {
  const [result, setResult] = useState<VariabilityResult | null>(null);
  const [progress, setProgress] = useState<{
    fraction: number;
    stage: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  function check() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setResult(null);
    setError(null);
    setProgress({ fraction: 0, stage: "Starting" });
    getVariability(
      target,
      (fraction, stage) => setProgress({ fraction, stage }),
      controller.signal,
    )
      .then(setResult)
      .catch((e: unknown) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof ApiError
              ? e.message
              : "The light curve could not be measured.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setProgress(null);
      });
  }

  return (
    <section className="variability">
      <h2>Brightness changes</h2>
      {!progress && !result && (
        <>
          <p className="muted small">
            Measures the object on every SPHEREx image (wide and deep surveys)
            and compares it with constant stars of the same images. Takes a few
            minutes. Works for saturated stars too, through the wings of their
            image.
          </p>
          <button onClick={check}>Check for brightness changes</button>
        </>
      )}
      {progress && (
        <p className="progress">
          <progress value={progress.fraction} /> {progress.stage}
        </p>
      )}
      {error && <p className="notice">{error}</p>}
      {result && <VariabilityResultView result={result} />}
      <VariabilityInfo />
    </section>
  );
}

const W = 640;
const H = 280;
const M = { left: 48, right: 12, top: 12, bottom: 36 };
const Y_RANGE = [0.2, 5]; // residuals on a log axis: ×0.2 to ×5
const PASS_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

const pct = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${(100 * value).toFixed(1)} %`;

function mjdToDate(mjd: number): string {
  return new Date(Date.UTC(1858, 10, 17) + mjd * 86400000)
    .toISOString()
    .slice(0, 10);
}

function VariabilityResultView({ result }: { result: VariabilityResult }) {
  const curve = result.light_curve;
  const allMjd = [
    ...curve.map((c) => c.mjd),
    ...result.reference.map((c) => c.mjd),
  ];
  const t0 = Math.min(...allMjd);
  const t1 = Math.max(...allMjd) + 1e-6; // avoids dividing by zero with a single date
  const x = (mjd: number) =>
    M.left + ((mjd - t0) / (t1 - t0)) * (W - M.left - M.right);
  const y = (residual: number) => {
    const v = Math.min(Math.max(residual, Y_RANGE[0]), Y_RANGE[1]);
    const f =
      (Math.log10(v) - Math.log10(Y_RANGE[0])) /
      (Math.log10(Y_RANGE[1]) - Math.log10(Y_RANGE[0]));
    return H - M.bottom - f * (H - M.top - M.bottom);
  };
  const passes = result.passes.map((p) => p.pass_index);
  const color = (pass: number) =>
    PASS_COLORS[passes.indexOf(pass) % PASS_COLORS.length];
  const v = result.verdict;

  return (
    <figure>
      <p className={v.variable ? "verdict variable" : "verdict"}>
        <strong>
          {v.variable
            ? "Variable"
            : v.variable === false
              ? "No change detected"
              : "Undecided"}
          .
        </strong>{" "}
        {v.text}
      </p>
      <dl className="stats">
        <dt>Object scatter</dt>
        <dd>{pct(result.target_scatter)}</dd>
        <dt>Constant stars</dt>
        <dd>
          {pct(result.reference_scatter)} ({result.n_comparison_stars} stars)
        </dd>
        <dt>Images</dt>
        <dd>
          {curve.length} measured of {result.n_images} read (
          {result.n_available} available)
          {result.wing_share > 0 &&
            `, ${Math.round(100 * result.wing_share)} % through the PSF wings (saturated)`}
        </dd>
      </dl>

      <div className="legend">
        {passes.map((p) => (
          <span key={p}>
            <svg
              width="12"
              height="12"
              viewBox="-6 -6 12 12"
              aria-hidden="true"
            >
              <circle r="4" fill={color(p)} />
            </svg>
            Pass {p + 1}
          </span>
        ))}
        <span>
          <svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true">
            <circle r="4" fill="none" stroke="var(--muted)" strokeWidth="1.5" />
          </svg>
          wings (saturated)
        </span>
        <span>
          <svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true">
            <circle r="2" fill="var(--border)" />
          </svg>
          constant stars
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Brightness of the object against time, relative to its usual level at each wavelength"
      >
        {[0.5, 1, 2].map((tick) => (
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
              ×{tick}
            </text>
          </g>
        ))}
        {result.reference.map((c, i) => (
          <circle
            key={`r${i}`}
            cx={x(c.mjd)}
            cy={y(c.residual)}
            r={1.3}
            fill="var(--border)"
          />
        ))}
        {curve.map((c, i) => (
          <circle
            key={`t${i}`}
            cx={x(c.mjd)}
            cy={y(c.residual)}
            r={3}
            fill={c.method === "wings" ? "var(--bg)" : color(c.pass_index)}
            stroke={color(c.pass_index)}
            strokeWidth={c.method === "wings" ? 1.5 : 0.5}
          >
            <title>{`${mjdToDate(c.mjd)} · ${c.lambda_um.toFixed(3)} µm · ×${c.residual.toFixed(2)} · ${c.method}`}</title>
          </circle>
        ))}
        <text className="tick" x={M.left} y={H - 8}>
          {mjdToDate(t0)}
        </text>
        <text className="tick" x={W - M.right} y={H - 8} textAnchor="end">
          {mjdToDate(t1)}
        </text>
        <text
          className="axis"
          x={(M.left + W - M.right) / 2}
          y={H - 8}
          textAnchor="middle"
        >
          date
        </text>
      </svg>

      <details className="notes">
        <summary>By survey pass and wavelength band</summary>
        <table>
          <thead>
            <tr>
              <th>Band (µm)</th>
              {result.passes.map((p) => (
                <th key={p.pass_index}>
                  Pass {p.pass_index + 1}
                  <br />
                  <small>
                    {mjdToDate(p.mjd_start)} to {mjdToDate(p.mjd_end)}
                  </small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>All</strong>
              </td>
              {result.passes.map((p) => (
                <td key={p.pass_index}>
                  ×{p.median.toFixed(2)}
                  {p.error !== null &&
                    p.error !== undefined &&
                    ` ± ${p.error.toFixed(2)}`}{" "}
                  <small>({p.n})</small>
                </td>
              ))}
            </tr>
            {result.bands.map((band) => (
              <tr key={band.lambda_min_um}>
                <td>
                  {band.lambda_min_um.toFixed(2)}–
                  {band.lambda_max_um.toFixed(2)}
                </td>
                {result.passes.map((p) => {
                  const cell = band.passes[String(p.pass_index)];
                  return (
                    <td key={p.pass_index}>
                      {cell ? (
                        <>
                          ×{cell.median.toFixed(2)} <small>({cell.n})</small>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">
          ×1 = the usual brightness at that wavelength. Bands that move in
          opposite directions mean the colour changed (as dust around young
          stars does).
        </p>
        <ul>
          {result.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </details>
    </figure>
  );
}

function VariabilityInfo() {
  return (
    <InfoNote title="How are brightness changes measured?">
      <p>
        SPHEREx sees a star at a different wavelength in each image, so two
        images cannot simply be compared: the star may look brighter only
        because of its colour. Each measurement is instead divided by the same
        star <strong>at the same wavelength</strong> in the other images. A
        constant star stays around ×1.
      </p>
      <dl>
        <dt>Constant stars (grey)</dt>
        <dd>
          Stars detected around the object, measured the same way. Their scatter
          is what noise looks like here. The object is called variable only when
          it scatters at least three times more (and at least 5 %).
        </dd>
        <dt>Saturated stars (hollow points)</dt>
        <dd>
          Very bright stars burn the centre of their image. Then the ring 9–14
          pixels from the centre (the PSF wings) is used: it follows the
          brightness in relative units. It cannot see changes smaller than ~15 %
          (measured on Barnard's Star, which is quiet), so the threshold is
          higher.
        </dd>
        <dt>Passes and bands</dt>
        <dd>
          The median of each survey pass, and of each band in each pass: a
          change that depends on wavelength is a change of colour.
        </dd>
      </dl>
      <p className="small muted">
        Checked: eps Ind B (constant) 3.8 % against 4.0 % for its comparison
        stars; a 10 % sinusoid injected into it is recovered as 9.5 %; RW Aur
        varies (34 % against 2.7 %) and changes colour; R Dra (saturated) varies
        through its wings (25 % against 2.5 %).
      </p>
    </InfoNote>
  );
}
