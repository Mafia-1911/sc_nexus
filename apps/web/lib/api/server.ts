import "server-only";

import { connection } from "next/server";
import createClient from "openapi-fetch";

import { currentAsOf, currentScenario } from "@/lib/scenario";

import type { components, paths } from "./types";

export type Meta = components["schemas"]["Meta"];
export type Schemas = components["schemas"];

/** The API base URL, read at request time so one image works locally and in compose. */
export function apiBase(): string {
  return process.env.API_URL ?? "http://127.0.0.1:8000";
}

/** The deployed API is a private Hugging Face Space: server-side calls carry its token
 *  (API_TOKEN, never sent to the browser). Locally there is none. */
export function apiHeaders(): Record<string, string> {
  return process.env.API_TOKEN ? { Authorization: `Bearer ${process.env.API_TOKEN}` } : {};
}

/** A typed client for server components. Every call is fresh (no Next data cache): the
 *  dashboard shows the data mode and "as of" of what it actually read. Awaiting `connection()`
 *  first makes every data read request-time under Cache Components (never at prerender). */
export async function api() {
  await connection();
  const [asOf, scenario] = await Promise.all([currentAsOf(), currentScenario()]);
  return createClient<paths>({
    baseUrl: apiBase(),
    fetch: (request: Request) => {
      // Every read carries the real-data view time (scenarios ignore it: their own clock) and the
      // data selector's choice, so a call that names no scenario follows the page (A-111).
      const url = new URL(request.url);
      if (!url.searchParams.has("day")) url.searchParams.set("day", asOf);
      if (!url.searchParams.has("scenario")) url.searchParams.set("scenario", scenario);
      const out = new Request(url, request);
      for (const [k, v] of Object.entries(apiHeaders())) out.headers.set(k, v);
      return fetch(out, { cache: "no-store" });
    },
  });
}
