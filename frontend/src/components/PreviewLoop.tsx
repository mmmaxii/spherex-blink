import { useEffect, useState } from "react";
import type { BlinkResult } from "../api/client";

const FRAME_MS = 600; // time each image stays on screen

/**
 * A small looping preview of the blink: every image in date order, with its date and wavelength.
 * The full player (views, layers, speed) is on the analysis page.
 */
export function PreviewLoop({ result }: { result: BlinkResult }) {
  const frames = result.frames;
  const [index, setIndex] = useState(0);

  // Load every picture first, so the loop does not flicker.
  useEffect(() => {
    for (const frame of frames) new Image().src = frame.url;
  }, [frames]);

  useEffect(() => {
    if (frames.length < 2) return;
    const timer = window.setInterval(
      () => setIndex((i) => (i + 1) % frames.length),
      FRAME_MS,
    );
    return () => window.clearInterval(timer);
  }, [frames.length]);

  const frame = frames[Math.min(index, frames.length - 1)];
  if (!frame) return null;
  return (
    <figure className="preview">
      <div className="preview-picture">
        <img
          src={frame.url}
          alt={`SPHEREx image of ${frame.date_utc.slice(0, 10)}`}
        />
        {Number.isFinite(frame.target_x_frac) &&
          Number.isFinite(frame.target_y_frac) && (
            <span
              className="preview-marker"
              style={{
                left: `${frame.target_x_frac * 100}%`,
                top: `${frame.target_y_frac * 100}%`,
              }}
              aria-hidden="true"
            />
          )}
      </div>
      <figcaption>
        {frame.date_utc.slice(0, 10)} · {frame.lambda_um.toFixed(3)} µm · pass{" "}
        {frame.pass_index + 1}{" "}
        <span className="muted">
          ({index + 1}/{frames.length})
        </span>
      </figcaption>
    </figure>
  );
}
