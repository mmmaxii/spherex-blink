import { useEffect, useMemo, useRef, useState } from "react";
import type { BlinkResult, FrameInfo } from "../api/client";

/**
 * Add or subtract any images the person chooses, in the browser.
 *
 * The backend writes each aligned frame as numbers (MJy/sr, background removed, float16, north up;
 * NaN = no data or a flagged pixel). Here each frame goes to group A, group B or neither:
 *   only A  → the average of A (more signal, less noise; what moves is smeared or removed)
 *   A and B → average of A minus average of B (what changed between them; a moving star leaves a
 *             white–black pair)
 * Pixels are averaged ignoring NaN, so flagged pixels never enter a sum.
 */

type Group = "A" | "B" | null;

/** IEEE half-precision → number (Float16Array is not in every browser yet). */
function halfToNumber(h: number): number {
  const sign = h & 0x8000 ? -1 : 1;
  const exponent = (h >> 10) & 0x1f;
  const fraction = h & 0x3ff;
  if (exponent === 0) return sign * 2 ** -14 * (fraction / 1024);
  if (exponent === 31) return fraction ? NaN : sign * Infinity;
  return sign * 2 ** (exponent - 15) * (1 + fraction / 1024);
}

async function loadValues(url: string): Promise<Float32Array> {
  const buffer = await (await fetch(url)).arrayBuffer();
  const halves = new Uint16Array(buffer);
  const values = new Float32Array(halves.length);
  for (let i = 0; i < halves.length; i++) values[i] = halfToNumber(halves[i]);
  return values;
}

/** Per-pixel mean of the chosen frames, ignoring NaN. */
function average(frames: Float32Array[]): Float32Array | null {
  if (frames.length === 0) return null;
  const sum = new Float32Array(frames[0].length);
  const count = new Uint16Array(frames[0].length);
  for (const frame of frames)
    for (let i = 0; i < frame.length; i++)
      if (Number.isFinite(frame[i])) {
        sum[i] += frame[i];
        count[i] += 1;
      }
  for (let i = 0; i < sum.length; i++)
    sum[i] = count[i] ? sum[i] / count[i] : NaN;
  return sum;
}

/** Robust spread of the finite values (1.4826 × median absolute deviation). */
function robustSpread(values: Float32Array): number {
  const finite = Array.from(values)
    .filter(Number.isFinite)
    .sort((a, b) => a - b);
  if (finite.length < 3) return 1;
  const median = finite[Math.floor(finite.length / 2)];
  const deviations = finite
    .map((v) => Math.abs(v - median))
    .sort((a, b) => a - b);
  return 1.4826 * deviations[Math.floor(deviations.length / 2)] || 1;
}

/** Values → gray levels: the same asinh scale as the frames for an average, a linear ±6σ scale
 * centred on grey for a difference. NaN stays transparent. */
function paint(
  canvas: HTMLCanvasElement,
  values: Float32Array,
  width: number,
  height: number,
  stretch: BlinkResult["stretch"],
  difference: boolean,
) {
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return;
  const picture = context.createImageData(width, height);
  const limit = 6 * robustSpread(values);
  const a = stretch.asinh_a;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v)) continue; // alpha 0: shows the "no data" background
    let level: number;
    if (difference) level = Math.min(Math.max((v / limit + 1) / 2, 0), 1);
    else {
      const x = Math.min(
        Math.max(
          (v - stretch.vmin_mjysr) / (stretch.vmax_mjysr - stretch.vmin_mjysr),
          0,
        ),
        1,
      );
      level = Math.asinh(x / a) / Math.asinh(1 / a);
    }
    const gray = Math.round(level * 255);
    picture.data.set([gray, gray, gray, 255], i * 4);
  }
  context.putImageData(picture, 0, 0);
}

const day = (frame: FrameInfo) => frame.date_utc.slice(0, 10);

export function CombineView({ result }: { result: BlinkResult }) {
  const frames = result.frames;
  const passes = [...new Set(frames.map((f) => f.pass_index))].sort(
    (a, b) => a - b,
  );
  // Start with something useful: last pass in A, first pass in B (a difference), or all in A.
  const [groups, setGroups] = useState<Group[]>(() =>
    frames.map((f) =>
      passes.length > 1
        ? f.pass_index === passes[passes.length - 1]
          ? "A"
          : f.pass_index === passes[0]
            ? "B"
            : null
        : "A",
    ),
  );
  const [values, setValues] = useState<Float32Array[] | null>(null);
  const [failed, setFailed] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all(frames.map((f) => loadValues(f.data_url)))
      .then((loaded) => !cancelled && setValues(loaded))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [frames]);

  const chosen = (group: Group) =>
    frames.map((_, i) => i).filter((i) => groups[i] === group);
  const inA = chosen("A");
  const inB = chosen("B");

  const combined = useMemo(() => {
    if (!values) return null;
    const meanA = average(inA.map((i) => values[i]));
    const meanB = average(inB.map((i) => values[i]));
    if (!meanA) return null;
    if (!meanB) return { pixels: meanA, difference: false };
    const out = new Float32Array(meanA.length);
    for (let i = 0; i < out.length; i++) out[i] = meanA[i] - meanB[i];
    return { pixels: out, difference: true };
    // inA/inB are derived from groups
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, groups]);

  useEffect(() => {
    if (combined && canvas.current)
      paint(
        canvas.current,
        combined.pixels,
        result.grid.width_px,
        result.grid.height_px,
        result.stretch,
        combined.difference,
      );
  }, [combined, result]);

  const setGroup = (index: number, group: Group) =>
    setGroups((all) => all.map((g, i) => (i === index ? group : g)));
  const setPass = (pass: number, group: Group) =>
    setGroups((all) =>
      all.map((g, i) => (frames[i].pass_index === pass ? group : g)),
    );

  const describe = (indices: number[]) =>
    indices.length === 0
      ? "none"
      : `${indices.length} image${indices.length > 1 ? "s" : ""} (${day(frames[indices[0]])} to ${day(frames[indices[indices.length - 1]])})`;

  if (failed)
    return (
      <p className="notice">The image values could not be loaded. Try again.</p>
    );
  return (
    <div className="combine">
      <div className="stage combine-stage">
        {combined ? (
          <canvas ref={canvas} aria-label="Combined image" />
        ) : (
          <p className="muted small">
            {values
              ? "Put at least one image in group A."
              : "Loading the image values…"}
          </p>
        )}
      </div>
      <p className="caption">
        <strong>{combined?.difference ? "A − B" : "Average of A"}</strong> · A:{" "}
        {describe(inA)}
        {inB.length > 0 && ` · B: ${describe(inB)}`}
        {combined?.difference &&
          " · white = brighter in A, black = brighter in B"}
      </p>

      <div className="combine-passes">
        {passes.map((p) => (
          <span key={p}>
            Pass {p + 1}:{" "}
            <button onClick={() => setPass(p, "A")}>all → A</button>{" "}
            <button onClick={() => setPass(p, "B")}>all → B</button>{" "}
            <button onClick={() => setPass(p, null)}>none</button>
          </span>
        ))}
        <button onClick={() => setGroups(frames.map(() => null))}>
          Clear all
        </button>
      </div>

      <details className="notes">
        <summary>Choose images one by one ({frames.length})</summary>
        <table className="combine-table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Date (UTC)</th>
              <th>Wavelength</th>
              <th>Pass</th>
            </tr>
          </thead>
          <tbody>
            {frames.map((f, i) => (
              <tr key={f.index}>
                <td>
                  <div
                    className="segmented"
                    role="radiogroup"
                    aria-label={`Group of image ${i + 1}`}
                  >
                    {(["A", "B", null] as Group[]).map((g) => (
                      <button
                        key={g ?? "none"}
                        role="radio"
                        aria-checked={groups[i] === g}
                        onClick={() => setGroup(i, g)}
                      >
                        {g ?? "–"}
                      </button>
                    ))}
                  </div>
                </td>
                <td>{f.date_utc.slice(0, 16)}</td>
                <td>{f.lambda_um.toFixed(3)} µm</td>
                <td>{f.pass_index + 1}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
