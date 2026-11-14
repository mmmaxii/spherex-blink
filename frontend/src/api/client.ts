/**
 * Thin client for the FastAPI backend. Paths are relative (/api/...): in development Vite
 * proxies them to localhost:8000, in production vercel.json rewrites them to Render.
 *
 * Request/response types will come from `npm run gen:api` (src/api/schema.d.ts, generated
 * from the backend's /openapi.json) so frontend and backend cannot drift apart.
 */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

export interface Health {
  status: string;
  version: string;
  collections: string[];
}

export const getHealth = (signal?: AbortSignal) =>
  getJson<Health>("/api/health", signal);
