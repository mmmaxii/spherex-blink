import { useEffect, useRef } from "react";
import {
  loadAladin,
  QUIET_OPTIONS,
  type AladinGlobal,
  type AladinOverlay,
  type AladinView,
} from "../sky/aladin";

/** A spot on the sky with the size of the field to analyse. */
export interface SkySelection {
  raDeg: number;
  decDeg: number;
  fovArcmin: number;
}

/** A request to move the map (a new `id` triggers the move, even to the same place). */
export interface FlyTo {
  id: number;
  raDeg: number;
  decDeg: number;
  fovDeg: number;
}

interface Props {
  surveyUrl: string;
  initial: { raDeg: number; decDeg: number; fovDeg: number };
  selection: SkySelection | null; // drawn as a square on the map
  flyTo: FlyTo | null;
  onPointer: (raDeg: number, decDeg: number) => void; // cursor over the sky
  onView: (raDeg: number, decDeg: number, fovDeg: number) => void; // map moved or zoomed
  onPick: (raDeg: number, decDeg: number) => void; // a click (not a drag)
  onError: (message: string) => void;
}

const CLICK_TOLERANCE_PX = 5; // a pointer that moves more than this between press and release is a drag
const SELECTION_COLOR = "#ffd23f";

/** Corners of a square field of `fovArcmin` centred on (ra, dec), for Aladin's polygon. */
function squareCorners(
  raDeg: number,
  decDeg: number,
  fovArcmin: number,
): [number, number][] {
  const halfDeg = fovArcmin / 120;
  const cosDec = Math.max(Math.cos((decDeg * Math.PI) / 180), 0.01); // avoid dividing by ~0 at the poles
  const halfRa = halfDeg / cosDec;
  return [
    [raDeg - halfRa, decDeg - halfDeg],
    [raDeg + halfRa, decDeg - halfDeg],
    [raDeg + halfRa, decDeg + halfDeg],
    [raDeg - halfRa, decDeg + halfDeg],
  ];
}

/**
 * Full-size Aladin Lite map. It reports where the cursor is, how the view moves, and where the
 * person clicks; the page decides what to do with that. The selected field is drawn as a square.
 */
export function SkyMap(props: Props) {
  const box = useRef<HTMLDivElement>(null);
  const library = useRef<AladinGlobal | null>(null);
  const view = useRef<AladinView | null>(null);
  const overlay = useRef<AladinOverlay | null>(null);
  // Callbacks live in a ref so the map is created once, not on every render of the page.
  const callbacks = useRef(props);
  callbacks.current = props;

  // 1. Create the map once.
  useEffect(() => {
    let cancelled = false;
    loadAladin()
      .then((A) => {
        if (cancelled || !box.current || view.current) return;
        const { initial, surveyUrl } = callbacks.current;
        const map = A.aladin(box.current, {
          ...QUIET_OPTIONS,
          survey: surveyUrl,
          target: `${initial.raDeg} ${initial.decDeg}`,
          fov: initial.fovDeg,
        });
        const shapes = A.graphicOverlay({
          color: SELECTION_COLOR,
          lineWidth: 2,
        });
        map.addOverlay(shapes);
        library.current = A;
        view.current = map;
        overlay.current = shapes;

        const reportView = () => {
          const [ra, dec] = map.getRaDec();
          callbacks.current.onView(ra, dec, map.getFov()[0]);
        };
        map.on("positionChanged", reportView);
        map.on("zoomChanged", reportView);
        reportView();
        drawSelection();
      })
      .catch((e: unknown) => {
        if (!cancelled)
          callbacks.current.onError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. Pointer: live coordinates on hover, a pick on click (a drag only pans the map).
  useEffect(() => {
    const element = box.current;
    if (!element) return;
    let pressedAt: { x: number; y: number } | null = null;

    const skyAt = (event: PointerEvent) => {
      const rect = element.getBoundingClientRect();
      const coords = view.current?.pix2world(
        event.clientX - rect.left,
        event.clientY - rect.top,
      );
      return coords && Number.isFinite(coords[0]) && Number.isFinite(coords[1])
        ? coords
        : null;
    };
    const onMove = (event: PointerEvent) => {
      const coords = skyAt(event);
      if (coords) callbacks.current.onPointer(coords[0], coords[1]);
    };
    const onDown = (event: PointerEvent) => {
      pressedAt =
        event.button === 0 ? { x: event.clientX, y: event.clientY } : null;
    };
    const onUp = (event: PointerEvent) => {
      if (!pressedAt) return;
      const moved = Math.hypot(
        event.clientX - pressedAt.x,
        event.clientY - pressedAt.y,
      );
      pressedAt = null;
      const coords = moved <= CLICK_TOLERANCE_PX ? skyAt(event) : null;
      if (coords) callbacks.current.onPick(coords[0], coords[1]);
    };
    element.addEventListener("pointermove", onMove);
    element.addEventListener("pointerdown", onDown);
    element.addEventListener("pointerup", onUp);
    return () => {
      element.removeEventListener("pointermove", onMove);
      element.removeEventListener("pointerdown", onDown);
      element.removeEventListener("pointerup", onUp);
    };
  }, []);

  // 3. Survey (mission) chosen by the person.
  useEffect(() => {
    view.current?.setBaseImageLayer(props.surveyUrl);
  }, [props.surveyUrl]);

  // 4. The selected field, drawn as a square with a small circle at its centre.
  function drawSelection() {
    const A = library.current;
    const shapes = overlay.current;
    if (!A || !shapes) return;
    shapes.removeAll();
    const s = callbacks.current.selection;
    if (!s) return;
    shapes.add(A.polygon(squareCorners(s.raDeg, s.decDeg, s.fovArcmin)));
    shapes.add(A.circle(s.raDeg, s.decDeg, s.fovArcmin / 60 / 25));
  }
  useEffect(drawSelection, [props.selection]);

  // 5. Fly to a place asked for by the page (a name search, a recent analysis).
  useEffect(() => {
    const target = props.flyTo;
    if (!target || !view.current) return;
    view.current.gotoRaDec(target.raDeg, target.decDeg);
    view.current.setFoV(target.fovDeg);
  }, [props.flyTo]);

  return <div ref={box} className="sky-map" aria-label="Interactive sky map" />;
}
