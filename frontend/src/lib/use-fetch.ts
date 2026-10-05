"use client";

import { useEffect, useState } from "react";
import type { Fetched } from "@/lib/api";

// Client-side wrapper over the existing api.ts fetchers ({ data, source }
// envelope). api.ts is frozen — this hook only consumes it.

export type FetchState<T> =
  | { status: "loading" }
  | { status: "live"; data: T }
  | { status: "error"; error: Error; retry: () => void };

/** Drives a `Fetched<T>` fetcher through loading → live/error. `retry`
 *  re-runs the fetcher; a generation counter ignores out-of-date resolutions
 *  (StrictMode double-invoke, rapid dep changes).
 *
 *  There is no "demo" state. Fetchers used to fall back to bundled fixtures and tag the
 *  result `source: "demo"`, which this hook mapped straight to an error — so the fixture
 *  was built, then discarded, on every failure. Fetchers now throw and the fixtures are
 *  gone; the only paths are live data, a skeleton, or error+retry. */
export function useFetch<T>(fn: () => Promise<Fetched<T>>, deps: React.DependencyList = []): FetchState<T> {
  const [state, setState] = useState<FetchState<T>>({ status: "loading" });
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    let stale = false;
    const load = async () => {
      setState({ status: "loading" });
      try {
        const { data } = await fn();
        if (!stale) {
          // A resolved fetcher is live by construction — the fixture-fallback branch it used
          // to guard against no longer exists (fetchers throw instead), and `DataSource` has
          // a single member so it cannot come back without a type error.
          setState({ status: "live", data });
        }
      } catch (e) {
        if (!stale) {
          setState({
            status: "error",
            error: e instanceof Error ? e : new Error(String(e)),
            retry: () => setGeneration((g) => g + 1),
          });
        }
      }
    };
    void load();
    return () => {
      stale = true;
    };
    // `fn` is intentionally excluded: callers pass inline closures; `deps` is
    // the caller-declared dependency list (useEffect semantics).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generation, ...deps]);

  return state;
}
