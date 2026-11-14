import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api/client";
import { readState } from "./state/urlState";

/** Placeholder shell: confirms the frontend can reach the backend. Real views come next. */
function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const state = readState();

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(setHealth)
      .catch((e: unknown) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="shell">
      <h1>SPHEREx Blink</h1>
      <p>Watch the infrared sky change over time.</p>
      <p className="status">
        Backend:{" "}
        {health
          ? `${health.status} (v${health.version}; ${health.collections.join(", ")})`
          : error
            ? `unreachable (${error})`
            : "checking…"}
      </p>
      <pre className="status">{JSON.stringify(state, null, 2)}</pre>
    </main>
  );
}

export default App;
