/**
 * The blink player: shows one picture at a time (single images, stacked survey passes or
 * differences) with play/step controls, optional layers drawn on top, and the details of
 * the image on screen. Pictures are PNGs already aligned by the backend, so the player only
 * swaps them.
 */
import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import type { BlinkResult, FrameInfo, Overlay } from "../api/client";
import type { Layer, View } from "../state/urlState";

/** One step of the animation, whatever the view. */
interface Item {
  key: string;
  url: string;
  flagsUrl: string | null;
  title: string;
  subtitle: string;
  x: number | null; // expected target position, fraction of the picture (0 = left)
  y: number | null; // (0 = top)
  frame: FrameInfo | null;
}

interface Props {
  result: BlinkResult;
  view: View;
  layers: Layer[];
  overlays: Overlay[];
  onView: (view: View) => void;
  onLayers: (layers: Layer[]) => void;
}

const VIEW_LABELS: Record<View, string> = {
  frames: "Every image",
  passes: "Survey passes (stacked)",
  difference: "Difference",
};

const LAYER_LABELS: Record<Layer, string> = {
  marker: "Target marker",
  raw: "Show flagged pixels",
  flags: "Paint flags",
  gaia: "Gaia",
  wise: "WISE",
};

// Time each picture stays on screen.
const SPEEDS = [
  { label: "Slow", ms: 1200 },
  { label: "Normal", ms: 600 },
  { label: "Fast", ms: 250 },
];

/** Keeps the date of an ISO timestamp: the first 10 characters. */
const day = (dateUtc: string) => dateUtc.slice(0, 10);

/** Turn the backend's result into the list of pictures of the chosen view. */
function buildItems(result: BlinkResult, view: View, raw: boolean): Item[] {
  if (view === "frames")
    return result.frames.map((f) => ({
      key: `f${f.index}`,
      url: raw ? f.raw_url : f.url,
      flagsUrl: f.flags_url,
      title: `${f.date_utc.slice(0, 16)} UTC`,
      subtitle: `${f.lambda_um.toFixed(3)} µm · pass ${f.pass_index + 1}`,
      x: f.target_x_frac,
      y: f.target_y_frac,
      frame: f,
    }));
  if (view === "passes")
    return [...result.stacks, result.stack_all].map((s) => ({
      key: `s${s.pass_index ?? "all"}`,
      url: s.url,
      flagsUrl: null,
      title:
        s.pass_index === null || s.pass_index === undefined
          ? "All passes together"
          : `Pass ${s.pass_index + 1} · ${day(s.date_start_utc)} to ${day(s.date_end_utc)}`,
      subtitle: `${s.n_images} images added · ${s.lambda_min_um.toFixed(2)}–${s.lambda_max_um.toFixed(2)} µm`,
      x: s.target_x_frac,
      y: s.target_y_frac,
      frame: null,
    }));
  return result.differences.map((d) => ({
    key: `d${d.pass_index}`,
    url: d.url,
    flagsUrl: null,
    title: `Pass ${d.pass_index + 1} minus pass ${d.reference_pass_index + 1}`,
    subtitle: `white = brighter later, black = fainter (±${d.limit_mjysr.toFixed(2)} MJy/sr)`,
    x: null,
    y: null,
    frame: null,
  }));
}

export function Player({
  result,
  view,
  layers,
  overlays,
  onView,
  onLayers,
}: Props) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speedMs, setSpeedMs] = useState(SPEEDS[1].ms);
  const items = useMemo(
    () => buildItems(result, view, layers.includes("raw")),
    [result, view, layers],
  );
  // The index can point past the end right after a change of view; clamp it.
  const current = items[Math.min(index, items.length - 1)] ?? null;

  // Load every picture up front so the blink does not flicker.
  useEffect(() => {
    for (const item of items) new Image().src = item.url;
  }, [items]);

  // Advance on a timer while playing; wraps around at the end.
  useEffect(() => {
    if (!playing || items.length < 2) return;
    const timer = setInterval(
      () => setIndex((i) => (i + 1) % items.length),
      speedMs,
    );
    return () => clearInterval(timer);
  }, [playing, speedMs, items.length]);

  // Stepping by hand pauses the animation.
  const step = (delta: number) => {
    setPlaying(false);
    setIndex(
      (i) =>
        (Math.min(i, items.length - 1) + delta + items.length) % items.length,
    );
  };
  const toggleLayer = (layer: Layer) =>
    onLayers(
      layers.includes(layer)
        ? layers.filter((l) => l !== layer)
        : [...layers, layer],
    );
  const changeView = (next: View) => {
    setIndex(0);
    onView(next);
  };
  // Keyboard: arrows step, space plays or pauses (when the picture has focus).
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "ArrowRight") step(1);
    else if (event.key === "ArrowLeft") step(-1);
    else if (event.key === " ") setPlaying((p) => !p);
    else return;
    event.preventDefault();
  };

  const fov = result.grid.fov_arcmin;
  const arcmin = 100 / fov; // one arcminute in viewBox units
  const shownOverlays = overlays.filter((o) => layers.includes(o.catalog));

  return (
    <section className="player">
      <div className="tabs" role="tablist">
        {(Object.keys(VIEW_LABELS) as View[]).map((v) => (
          <button
            key={v}
            role="tab"
            aria-selected={v === view}
            onClick={() => changeView(v)}
          >
            {VIEW_LABELS[v]}
          </button>
        ))}
      </div>

      {current ? (
        <>
          <div
            className="stage"
            tabIndex={0}
            onKeyDown={onKey}
            aria-label={`SPHEREx image, ${current.title}, ${current.subtitle}`}
          >
            <img src={current.url} alt="" />
            {view === "frames" &&
              layers.includes("flags") &&
              current.flagsUrl && <img src={current.flagsUrl} alt="" />}
            {/* Drawn over the picture in a 0–100 box: catalogue sources, target marker,
                compass and a 1-arcminute scale bar. */}
            <svg viewBox="0 0 100 100" aria-hidden="true">
              {shownOverlays.map((overlay) =>
                overlay.sources.map((s) => (
                  <circle
                    key={s.id}
                    className={`source ${overlay.catalog}`}
                    cx={s.x_frac * 100}
                    cy={s.y_frac * 100}
                    r={1.6}
                  >
                    <title>{`${s.id}${s.mag === null || s.mag === undefined ? "" : ` · ${s.band} = ${s.mag.toFixed(1)}`}`}</title>
                  </circle>
                )),
              )}
              {layers.includes("marker") &&
                current.x !== null &&
                current.y !== null && (
                  <circle
                    className="marker"
                    cx={current.x * 100}
                    cy={current.y * 100}
                    r={4.5}
                  />
                )}
              <g className="furniture">
                <path d="M 93 12 V 4 M 93 4 l -1.5 2.5 M 93 4 l 1.5 2.5 M 93 12 H 85 M 85 12 l 2.5 -1.5 M 85 12 l 2.5 1.5" />
                <text x="93" y="3.2" textAnchor="middle">
                  N
                </text>
                <text x="83.4" y="13" textAnchor="end">
                  E
                </text>
                <path d={`M 4 95 h ${arcmin}`} />
                <text x={4 + arcmin / 2} y="93.4" textAnchor="middle">
                  1′
                </text>
              </g>
            </svg>
          </div>

          <p className="caption">
            <strong>{current.title}</strong> · {current.subtitle} · detector{" "}
            {result.detector}
            <span className="muted">
              {" "}
              ({index + 1}/{items.length})
            </span>
          </p>

          <div className="controls">
            <button onClick={() => step(-1)} aria-label="Previous image">
              ◀
            </button>
            <button className="primary" onClick={() => setPlaying((p) => !p)}>
              {playing ? "Pause" : "Play"}
            </button>
            <button onClick={() => step(1)} aria-label="Next image">
              ▶
            </button>
            <input
              type="range"
              min={0}
              max={items.length - 1}
              value={Math.min(index, items.length - 1)}
              onChange={(e) => {
                setPlaying(false);
                setIndex(Number(e.target.value));
              }}
              aria-label="Image in the series"
            />
            <select
              value={speedMs}
              onChange={(e) => setSpeedMs(Number(e.target.value))}
              aria-label="Speed"
            >
              {SPEEDS.map((s) => (
                <option key={s.ms} value={s.ms}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </>
      ) : (
        <p className="notice">
          Only one survey pass has images here, so there is nothing to subtract
          yet.
        </p>
      )}

      <div className="layers">
        {(Object.keys(LAYER_LABELS) as Layer[]).map((layer) => (
          <label key={layer} className={layer}>
            <input
              type="checkbox"
              checked={layers.includes(layer)}
              onChange={() => toggleLayer(layer)}
            />
            {LAYER_LABELS[layer]}
          </label>
        ))}
      </div>
      {shownOverlays.map((o) => (
        <p key={o.catalog} className="muted small">
          {o.label}: {o.sources.length} sources. {o.epoch_note}
        </p>
      ))}

      {current?.frame && <FrameDetails frame={current.frame} />}

      <details className="notes">
        <summary>
          How these images were made
          {result.skipped.length > 0 &&
            ` · ${result.skipped.length} images left out`}
        </summary>
        <p>
          {result.frames.length} of the {result.n_available} detector-
          {result.detector} images of this position, from{" "}
          {result.collections.join(" + ")}. North is up, east is left. All
          frames share one brightness scale.
        </p>
        <ul>
          {result.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        {result.skipped.length > 0 && (
          <ul>
            {result.skipped.map((s) => (
              <li key={`${s.obs_id}-${s.detector}`}>
                {s.obs_id}: {s.reason}
              </li>
            ))}
          </ul>
        )}
        <p>
          <a href={result.gif_url} download="spherex-blink.gif">
            Download the animation (GIF)
          </a>
        </p>
      </details>
    </section>
  );
}

/** Metadata of the image on screen: wavelength, date, quality, flags, link to the file. */
function FrameDetails({ frame }: { frame: FrameInfo }) {
  // Only the kinds of contamination that are present, as plain words (AIRGLOW_CONT → airglow).
  const contaminated = Object.entries(frame.contamination)
    .filter(([, on]) => on)
    .map(([name]) =>
      name.replace("_CONT", "").toLowerCase().replaceAll("_", " "),
    );
  const counts = Object.entries(frame.flag_counts).sort((a, b) => b[1] - a[1]);
  return (
    <details className="notes">
      <summary>
        About this image
        {frame.target_flags.length > 0 &&
          ` · flags on the target: ${frame.target_flags.join(", ")}`}
      </summary>
      <dl>
        <dt>Wavelength</dt>
        <dd>
          {frame.lambda_um.toFixed(4)} µm (band {frame.bandwidth_um.toFixed(4)}{" "}
          µm wide, approximate)
        </dd>
        <dt>Date</dt>
        <dd>
          {frame.date_utc} UTC (MJD {frame.mjd.toFixed(4)}),{" "}
          {frame.collection.replace("spherex_", "").toUpperCase()}
        </dd>
        <dt>Quality</dt>
        <dd>
          {frame.quality ?? "not given"}
          {frame.astrometry_flag ? ", astrometry partial" : ""}
          {contaminated.length > 0
            ? `, contaminated by ${contaminated.join(", ")}`
            : ", no contamination reported"}
        </dd>
        <dt>Sky level removed</dt>
        <dd>
          {frame.background_mjysr.toFixed(3)} MJy/sr (noise{" "}
          {frame.noise_mjysr.toFixed(3)})
        </dd>
        <dt>Flagged pixels</dt>
        <dd>
          {(frame.flagged_fraction * 100).toFixed(1)} % hidden.{" "}
          {counts.map(([name, n]) => `${name} ${n}`).join(", ")}
        </dd>
        <dt>Field covered</dt>
        <dd>{(frame.coverage_fraction * 100).toFixed(0)} %</dd>
        <dt>Original file</dt>
        <dd>
          <a href={frame.file_url}>{frame.obs_id} (FITS, 65 MB)</a>
        </dd>
      </dl>
    </details>
  );
}
