/**
 * Client for the FastAPI backend. Paths are relative (/api/...): in development Vite proxies
 * them to localhost:8000, in production vercel.json rewrites them to Render.
 *
 * Types come from src/api/schema.d.ts, generated from the backend's /openapi.json with
 * `npm run gen:api` (backend running). Regenerate after changing backend/app/schemas.py.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Health = Schemas["Health"];
export type Target = Schemas["Target"];
export type Coverage = Schemas["Coverage"];
export type JobStatus = Schemas["JobStatus"];
export type BlinkResult = Schemas["BlinkResult"];
export type FrameInfo = Schemas["FrameInfo"];
export type StackInfo = Schemas["StackInfo"];
export type DifferenceInfo = Schemas["DifferenceInfo"];
export type SpectrumResult = Schemas["SpectrumResult"];
export type SpectrumPoint = Schemas["SpectrumPoint"];
export type Overlay = Schemas["Overlay"];
export type Catalog = Overlay["catalog"];

type Params = Record<string, string | number | null | undefined>;

/** Every backend error arrives as {error: {code, message, detail}}; `code` is stable. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    detail: Record<string, unknown> = {},
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

function withParams(path: string, params: Params): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== null && value !== undefined && value !== "")
      query.set(key, String(value));
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export async function getJson<T>(
  path: string,
  params: Params = {},
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(withParams(path, params), { signal });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError(
      0,
      "network",
      "Could not reach the server. Check your connection and try again.",
    );
  }
  if (response.ok) return (await response.json()) as T;
  const body = (await response.json().catch(() => null)) as {
    error?: {
      code?: string;
      message?: string;
      detail?: Record<string, unknown>;
    };
  } | null;
  const error = body?.error;
  throw new ApiError(
    response.status,
    error?.code ?? "http_error",
    error?.message ?? `The server answered ${response.status}.`,
    error?.detail ?? {},
  );
}

const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });

/**
 * Start a long request (frames, spectrum) and wait for its result. The backend answers at once
 * with a job; this polls /api/jobs/{id} and reports progress (0..1 and a sentence).
 */
export async function runJob<R>(
  path: string,
  params: Params,
  onProgress: (progress: number, stage: string) => void,
  signal?: AbortSignal,
): Promise<R> {
  let job = await getJson<JobStatus>(path, params, signal);
  let restarts = 0;
  while (job.status === "queued" || job.status === "running") {
    onProgress(job.progress, job.stage);
    await wait(700, signal);
    try {
      job = await getJson<JobStatus>(`/api/jobs/${job.job_id}`, {}, signal);
    } catch (e) {
      // The server restarted and forgot the job: ask again once.
      if (e instanceof ApiError && e.status === 404 && restarts++ < 1)
        job = await getJson<JobStatus>(path, params, signal);
      else throw e;
    }
  }
  if (job.status === "failed" || !job.result) {
    const error = job.error;
    throw new ApiError(
      200,
      error?.code ?? "job_failed",
      error?.message ?? "The request could not be completed.",
      (error?.detail as Record<string, unknown>) ?? {},
    );
  }
  onProgress(1, "Done");
  return job.result as R;
}

export const getHealth = (signal?: AbortSignal) =>
  getJson<Health>("/api/health", {}, signal);

/** A name, or coordinates in any usual format, to a position SPHEREx can be asked for. */
export const resolveTarget = (
  query: { name?: string | null; ra?: string | null; dec?: string | null },
  signal?: AbortSignal,
) => getJson<Target>("/api/resolve", query, signal);

export const getCoverage = (target: Target, signal?: AbortSignal) =>
  getJson<Coverage>(
    "/api/coverage",
    { ra_deg: target.ra_deg, dec_deg: target.dec_deg },
    signal,
  );

/** Parameters shared by /frames and /spectrum: where the target is and how it moves. */
function targetParams(target: Target): Params {
  return {
    ra_deg: target.ra_deg,
    dec_deg: target.dec_deg,
    pm_ra_masyr: target.pm_ra_masyr ?? 0,
    pm_dec_masyr: target.pm_dec_masyr ?? 0,
    epoch_mjd: target.pm_ra_masyr !== null ? target.epoch_mjd : null,
  };
}

export const getBlink = (
  target: Target,
  options: { fovArcmin: number; detector: number },
  onProgress: (progress: number, stage: string) => void,
  signal?: AbortSignal,
) =>
  runJob<BlinkResult>(
    "/api/frames",
    {
      ...targetParams(target),
      fov_arcmin: options.fovArcmin,
      detector: options.detector,
    },
    onProgress,
    signal,
  );

export const getSpectrum = (
  target: Target,
  onProgress: (progress: number, stage: string) => void,
  signal?: AbortSignal,
) =>
  runJob<SpectrumResult>(
    "/api/spectrum",
    { ...targetParams(target), mode: "pass" },
    onProgress,
    signal,
  );

export const getOverlay = (
  target: Target,
  fovArcmin: number,
  catalog: Catalog,
  signal?: AbortSignal,
) =>
  getJson<Overlay>(
    "/api/overlay",
    {
      ra_deg: target.ra_deg,
      dec_deg: target.dec_deg,
      fov_arcmin: fovArcmin,
      catalog,
    },
    signal,
  );
