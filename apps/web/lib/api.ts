/**
 * Thin fetch wrapper around the FastAPI service.
 * Adds `Authorization: Bearer <ID token>` automatically on the client.
 */
import { getIdToken } from "@/lib/auth";

import type { ApiResponse } from "@relief/shared-types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiCallError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiCallError";
  }
}

async function call<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const token = await getIdToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  let payload: ApiResponse<T> | null = null;
  try {
    payload = (await res.json()) as ApiResponse<T>;
  } catch {
    throw new ApiCallError("PARSE_ERROR", `Non-JSON response from ${path}`, res.status);
  }

  if (!res.ok || payload.error) {
    const err = payload.error ?? { code: `HTTP_${res.status}`, message: res.statusText };
    throw new ApiCallError(err.code, err.message, res.status);
  }

  return payload.data as T;
}

export const api = {
  get: <T>(path: string) => call<T>("GET", path),
  post: <T>(path: string, body?: unknown) => call<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => call<T>("PATCH", path, body),
  del: <T>(path: string) => call<T>("DELETE", path),
};
