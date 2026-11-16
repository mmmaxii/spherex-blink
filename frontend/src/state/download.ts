/**
 * Files the person takes away: names that say what they hold, and CSV tables built in the browser
 * from data the page already has (nothing is asked again from the server).
 */
import type { Target } from "../api/client";

/** Short name for downloaded files: the object's name, or its position. */
export function fileStem(target: Target | null): string {
  if (!target) return "field";
  const name = target.name?.replace(/^V\*\s*/, "").trim(); // SIMBAD's "V* R Dra" → "R Dra"
  return name
    ? name.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "")
    : `${target.ra_deg.toFixed(4)}_${target.dec_deg.toFixed(4)}`;
}

type Cell = string | number | boolean | null | undefined;

/** One CSV cell: quoted when it holds a comma, a quote or a line break. */
function csvCell(value: Cell): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** Comment lines (starting with #) first, then the header and one line per row. */
export function toCsv(
  comments: string[],
  header: string[],
  rows: Cell[][],
): string {
  return [
    ...comments.map((c) => `# ${c}`),
    header.map(csvCell).join(","),
    ...rows.map((row) => row.map(csvCell).join(",")),
  ].join("\n");
}

/** Hand a text file to the browser's download. */
export function downloadText(
  filename: string,
  text: string,
  type = "text/csv",
): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
