/**
 * The last analyses this person opened, kept in their own browser (localStorage), newest first.
 * Only five: enough to come back to something, short enough to read at a glance.
 *
 * Storage can be missing or blocked (private windows, blocked site data): every access is wrapped
 * so the page keeps working, just without the list.
 */

export interface RecentAnalysis {
  label: string; // object name, or the coordinates
  search: string; // the analysis page's query string, e.g. "?ra=79.17&dec=30.44&fov=6"
  raDeg: number;
  decDeg: number;
  fovArcmin: number;
  nImages: number | null;
  savedAt: string; // ISO date
}

const KEY = "spherex-blink:recent";
export const MAX_RECENT = 5;

export function loadRecent(): RecentAnalysis[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed)
      ? (parsed as RecentAnalysis[]).slice(0, MAX_RECENT)
      : [];
  } catch {
    return [];
  }
}

/** Put an analysis at the top of the list (once: the same view is not repeated). */
export function rememberAnalysis(entry: RecentAnalysis): RecentAnalysis[] {
  const others = loadRecent().filter((r) => r.search !== entry.search);
  const list = [entry, ...others].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // storage blocked: the list simply is not kept
  }
  return list;
}
