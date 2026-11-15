/** Coordinates and fields of view as people read them. */

const pad = (value: number, width: number, decimals = 0) =>
  value.toFixed(decimals).padStart(width + (decimals ? decimals + 1 : 0), "0");

/** Right ascension in hours, minutes, seconds: 05h16m41.4s */
export function formatRa(raDeg: number): string {
  const hours = (((raDeg % 360) + 360) % 360) / 15;
  let h = Math.floor(hours);
  let m = Math.floor((hours - h) * 60);
  let s = (hours - h - m / 60) * 3600;
  if (s >= 59.95) {
    s = 0;
    m += 1;
  }
  if (m >= 60) {
    m = 0;
    h = (h + 1) % 24;
  }
  return `${pad(h, 2)}h${pad(m, 2)}m${pad(s, 2, 1)}s`;
}

/** Declination in degrees, arcminutes, arcseconds: +45°59′53″ */
export function formatDec(decDeg: number): string {
  const sign = decDeg < 0 ? "−" : "+";
  const abs = Math.abs(decDeg);
  let d = Math.floor(abs);
  let m = Math.floor((abs - d) * 60);
  let s = Math.round((abs - d - m / 60) * 3600);
  if (s === 60) {
    s = 0;
    m += 1;
  }
  if (m === 60) {
    m = 0;
    d += 1;
  }
  return `${sign}${pad(d, 2)}°${pad(m, 2)}′${pad(s, 2)}″`;
}

/** A field of view in the unit that reads best: 2.5°, 14′, 40″ */
export function formatFov(fovDeg: number): string {
  if (fovDeg >= 1) return `${fovDeg.toFixed(fovDeg >= 10 ? 0 : 1)}°`;
  const arcmin = fovDeg * 60;
  if (arcmin >= 1) return `${arcmin.toFixed(arcmin >= 10 ? 0 : 1)}′`;
  return `${(arcmin * 60).toFixed(0)}″`;
}
