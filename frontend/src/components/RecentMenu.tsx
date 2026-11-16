import type { RecentAnalysis } from "../state/recent";

interface Props {
  open: boolean;
  recent: RecentAnalysis[];
  onToggle: () => void;
  onOpen: (search: string) => void; // go to the full analysis page
  onShow: (entry: RecentAnalysis) => void; // fly the map there
}

/** Menu button (top left) and the drawer with the last analyses kept in this browser. */
export function RecentMenu({ open, recent, onToggle, onOpen, onShow }: Props) {
  return (
    <>
      <button
        className="glass menu-button"
        aria-expanded={open}
        aria-controls="recent-drawer"
        onClick={onToggle}
      >
        <span aria-hidden="true">☰</span> History
      </button>
      {open && (
        <aside
          id="recent-drawer"
          className="glass drawer"
          aria-label="Recent analyses"
        >
          <h2>Recent analyses</h2>
          {recent.length === 0 ? (
            <p className="muted small">
              Nothing yet. Pick a spot on the sky and analyse it: the last five
              are kept here, in this browser only.
            </p>
          ) : (
            <ol className="recent-list">
              {recent.map((entry) => (
                <li key={entry.search}>
                  <button
                    className="recent-open"
                    onClick={() => onOpen(entry.search)}
                  >
                    <strong>{entry.label}</strong>
                    <small>
                      {entry.fovArcmin}′ field
                      {entry.nImages !== null &&
                        ` · ${entry.nImages} images`} ·{" "}
                      {entry.savedAt.slice(0, 10)}
                    </small>
                  </button>
                  <button
                    className="link-button small"
                    onClick={() => onShow(entry)}
                    title="Move the map to this field"
                  >
                    Show on the map
                  </button>
                </li>
              ))}
            </ol>
          )}
          <p className="muted small">
            Each opens its full analysis on its own page, with an address you
            can share.
          </p>
        </aside>
      )}
    </>
  );
}
