import "server-only";

import { connection } from "next/server";
import createClient from "openapi-fetch";

import type { components, paths } from "./types";

export type Meta = components["schemas"]["Meta"];
export type Schemas = components["schemas"];

/** The API base URL, read at request time so one image works locally and in compose. */
export function apiBase(): string {
  return process.env.API_URL ?? "http://127.0.0.1:8000";
}

/** A typed client for server components. Every call is fresh (no Next data cache): the
 *  dashboard shows the data mode and "as of" of what it actually read. Awaiting `connection()`
 *  first makes every data read request-time under Cache Components (never at prerender). */
export async function api() {
  await connection();
  return createClient<paths>({
    baseUrl: apiBase(),
    fetch: (request: Request) => fetch(request, { cache: "no-store" }),
  });
}
