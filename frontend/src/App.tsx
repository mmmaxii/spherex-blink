import { useEffect, useState } from "react";
import { AnalysisPage } from "./pages/AnalysisPage";
import { ExplorePage } from "./pages/ExplorePage";
import { hasQuery, readState } from "./state/urlState";

/**
 * Two pages on one address:
 *   /                    the sky map, to pick a field (ExplorePage)
 *   /?ra=…&dec=… or ?target=…   the full analysis of that field (AnalysisPage)
 * Old shared links keep working, because they always carry a position. The browser's back button
 * moves between the two pages (pushState + popstate).
 */
function App() {
  const [search, setSearch] = useState(window.location.search);
  const [visit, setVisit] = useState(0); // new value = a fresh page (state is read from the URL again)

  useEffect(() => {
    const onBack = () => {
      setSearch(window.location.search);
      setVisit((n) => n + 1);
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);

  const navigate = (next: string) => {
    window.history.pushState(null, "", `${window.location.pathname}${next}`);
    setSearch(next);
    setVisit((n) => n + 1);
    window.scrollTo(0, 0);
  };

  return hasQuery(readState(search)) ? (
    <AnalysisPage key={visit} onHome={() => navigate("")} />
  ) : (
    <ExplorePage key={visit} onOpen={navigate} />
  );
}

export default App;
