/**
 * Aladin Lite (CDS, Strasbourg): the interactive sky map.
 *
 * It is installed from npm (aladin-lite 3.8.2) and bundled with the page, instead of being loaded
 * from the CDS server: on 15 Nov 2026 that server answered 404 and the map could not open at all.
 * The package is ~2.4 MB, so it is imported only when a map is shown (a separate chunk).
 *
 * Aladin needs WebGL2. `A.init` rejects when the browser cannot provide it; the page then shows
 * a sentence instead of an empty box (see `loadAladin`).
 */

/** The parts of an Aladin view this app uses (the package has no TypeScript types). */
export interface AladinView {
  getRaDec(): [number, number];
  getFov(): [number, number];
  pix2world(x: number, y: number): [number, number] | undefined;
  gotoRaDec(ra: number, dec: number): void;
  setFoV(fovDeg: number): void;
  setBaseImageLayer(urlOrId: string): void;
  getBaseImageLayer(): AladinImageLayer;
  addOverlay(overlay: AladinOverlay): void;
  on(event: string, callback: (...args: unknown[]) => void): void;
}

/** A sky survey layer. Cube surveys (several wavelengths) can show one channel at a time. */
export interface AladinImageLayer {
  added?: boolean; // true once its properties are loaded and it is on the map
  cubeDepth?: number; // number of channels, for cube surveys
  setSliceNumber?(slice: number): void;
}

export interface AladinOverlay {
  add(shape: unknown): void;
  removeAll(): void;
}

export interface AladinGlobal {
  init: Promise<void>;
  aladin(element: HTMLElement, options: Record<string, unknown>): AladinView;
  graphicOverlay(options: Record<string, unknown>): AladinOverlay;
  circle(
    ra: number,
    dec: number,
    radiusDeg: number,
    options?: Record<string, unknown>,
  ): unknown;
  polygon(
    points: [number, number][],
    options?: Record<string, unknown>,
  ): unknown;
}

let loading: Promise<AladinGlobal> | null = null;

/** The Aladin library, ready to create maps. Rejects with a readable Error. */
export function loadAladin(): Promise<AladinGlobal> {
  loading ??= import("aladin-lite")
    .then(async (module) => {
      const A = module.default as unknown as AladinGlobal;
      await A.init; // compiles the WebGL2 core; throws when WebGL2 is missing
      return A;
    })
    .catch((e: unknown) => {
      loading = null; // allow a retry
      const text = String(e);
      throw new Error(
        text.includes("WebGL2")
          ? "This browser cannot draw the sky map (it needs WebGL2). You can still type coordinates or a name."
          : "The sky map could not be loaded. You can still type coordinates or a name.",
      );
    });
  return loading;
}

/** Map options shared by every view: no Aladin chrome, the page draws its own controls. */
export const QUIET_OPTIONS = {
  cooFrame: "ICRSd",
  projection: "SIN",
  showReticle: false,
  showZoomControl: false,
  showFullscreenControl: false,
  showLayersControl: false,
  showFrame: false,
  showFov: false,
  showCooLocation: false,
  showProjectionControl: false,
  showStatusBar: false,
  showSimbadPointerControl: false,
  showCooGridControl: false,
  showSettingsControl: false,
  showShareControl: false,
  showContextMenu: false,
  backgroundColor: "rgb(4,6,10)",
  log: false, // no usage report to the CDS logger (the request failed while CDS was down)
};

/**
 * Show a survey on a map. For a cube survey, `slice` picks the channel once the layer is ready
 * (Aladin loads the survey's properties first, so this waits for up to a few seconds).
 */
export function showSurvey(
  view: AladinView,
  url: string,
  slice?: number,
): void {
  view.setBaseImageLayer(url);
  if (slice === undefined) return;
  let tries = 0;
  const timer = window.setInterval(() => {
    const layer = view.getBaseImageLayer();
    tries += 1;
    if (layer.added && layer.cubeDepth && layer.setSliceNumber) {
      layer.setSliceNumber(slice);
      window.clearInterval(timer);
    } else if (tries > 50) {
      window.clearInterval(timer); // give up quietly: the default channel stays
    }
  }, 100);
}
