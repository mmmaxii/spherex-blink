/**
 * Page state <-> URL query string, so any view can be shared or embedded:
 *   ?ra=133.76&dec=-7.2422&fov=6&det=6&view=pass&layers=gaia,flags&embed=1
 *   ?target=WISE+0855
 * Coordinates are kept as typed strings here (decimal degrees or sexagesimal);
 * the backend's /api/resolve turns them into decimal degrees.
 */

export const VIEWS = ["channel", "pass", "all"] as const;
export type View = (typeof VIEWS)[number];

export const FOV_ARCMIN_OPTIONS = [3, 6, 12] as const;

export interface ViewState {
  ra: string | null;
  dec: string | null;
  target: string | null;
  fovArcmin: number;
  detector: number | null; // 1..6; null = let the backend choose
  view: View;
  layers: string[];
  embed: boolean;
}

export const DEFAULT_STATE: ViewState = {
  ra: null,
  dec: null,
  target: null,
  fovArcmin: 6, // WISE 0855 sits ~2.1' from its catalogue position: 3' would miss it
  detector: null,
  view: "channel",
  layers: [],
  embed: false,
};

export function readState(search: string = window.location.search): ViewState {
  const p = new URLSearchParams(search);
  const fov = Number(p.get("fov"));
  const det = Number(p.get("det"));
  const view = p.get("view") as View | null;
  return {
    ra: p.get("ra"),
    dec: p.get("dec"),
    target: p.get("target"),
    fovArcmin:
      Number.isFinite(fov) && fov > 0 && fov <= 30
        ? fov
        : DEFAULT_STATE.fovArcmin,
    detector: Number.isInteger(det) && det >= 1 && det <= 6 ? det : null,
    view: view && VIEWS.includes(view) ? view : DEFAULT_STATE.view,
    layers: (p.get("layers") ?? "").split(",").filter(Boolean),
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
  if (state.layers.length) p.set("layers", state.layers.join(","));
  if (state.embed) p.set("embed", "1");
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Update the address bar without reloading, so copying it shares the exact view. */
export function writeState(state: ViewState): void {
  const url = `${window.location.pathname}${toSearch(state)}`;
  window.history.replaceState(null, "", url);
}
