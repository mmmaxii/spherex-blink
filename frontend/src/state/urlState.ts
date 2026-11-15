/**
 * Page state <-> URL query string, so any view can be shared or embedded:
 *   ?target=WISE+0855-0714&fov=6&det=6&view=passes&layers=marker,gaia&embed=1
 *   ?ra=08h55m10.831s&dec=-7d14m42.53s
 * Coordinates are kept as typed (decimal degrees or sexagesimal); the backend's /api/resolve
 * turns them into decimal degrees.
 */

/** frames = every exposure; passes = one stack per survey pass; difference = pass minus first pass. */
export const VIEWS = ["frames", "passes", "difference"] as const;
export type View = (typeof VIEWS)[number];

export const FOV_ARCMIN_OPTIONS = [3, 6, 12, 20] as const;

/** marker = expected target position; raw = show flagged pixels; flags = paint them; gaia, wise = catalogues. */
export const LAYERS = ["marker", "raw", "flags", "gaia", "wise"] as const;
export type Layer = (typeof LAYERS)[number];

export interface ViewState {
  ra: string | null;
  dec: string | null;
  target: string | null;
  fovArcmin: number;
  detector: number | null; // 1..6; null = the page picks the detector with most images
  view: View;
  layers: Layer[];
  embed: boolean;
}

export const DEFAULT_STATE: ViewState = {
  ra: null,
  dec: null,
  target: null,
  fovArcmin: 6,
  detector: null,
  view: "frames",
  layers: ["marker"],
  embed: false,
};

export function readState(search: string = window.location.search): ViewState {
  const p = new URLSearchParams(search);
  const fov = Number(p.get("fov"));
  const det = Number(p.get("det"));
  const view = p.get("view") as View | null;
  const layers = p.get("layers");
  return {
    ra: p.get("ra"),
    dec: p.get("dec"),
    target: p.get("target"),
    fovArcmin:
      Number.isFinite(fov) && fov >= 1 && fov <= 20
        ? fov
        : DEFAULT_STATE.fovArcmin,
    detector: Number.isInteger(det) && det >= 1 && det <= 6 ? det : null,
    view: view && VIEWS.includes(view) ? view : DEFAULT_STATE.view,
    layers:
      layers === null
        ? DEFAULT_STATE.layers
        : (layers
            .split(",")
            .filter((l) =>
              (LAYERS as readonly string[]).includes(l),
            ) as Layer[]),
    embed: p.get("embed") === "1",
  };
}

export function toSearch(state: ViewState): string {
  const p = new URLSearchParams();
  if (state.target) p.set("target", state.target);
  if (state.ra) p.set("ra", state.ra);
  if (state.dec) p.set("dec", state.dec);
  if (state.fovArcmin !== DEFAULT_STATE.fovArcmin)
    p.set("fov", String(state.fovArcmin));
  if (state.detector) p.set("det", String(state.detector));
  if (state.view !== DEFAULT_STATE.view) p.set("view", state.view);
  if (state.layers.join(",") !== DEFAULT_STATE.layers.join(","))
    p.set("layers", state.layers.join(","));
  if (state.embed) p.set("embed", "1");
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Update the address bar without reloading, so copying it shares the exact view. */
export function writeState(state: ViewState): void {
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${toSearch(state)}`,
  );
}

/** Does the state name a place in the sky? */
export const hasQuery = (state: ViewState) =>
  Boolean(state.target || (state.ra && state.dec));
