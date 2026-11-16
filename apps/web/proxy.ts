import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, authEnabled, readSession } from "@/lib/session";

/** Accounts (A-118): with AUTH_SECRET set, every app page needs a session; others land on the
 *  welcome page. Without it (local stack, e2e) the app stays open. */
export async function proxy(request: NextRequest) {
  if (!authEnabled()) return NextResponse.next();
  const session = await readSession(request.cookies.get(SESSION_COOKIE)?.value);
  if (session) return NextResponse.next();
  const url = new URL("/welcome", request.url);
  if (request.nextUrl.pathname !== "/") url.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = {
  // Everything except the public pages, Next's assets, the map and vendor files, the keep-alive.
  matcher: ["/((?!welcome|login|signup|_next|favicon.ico|vendor|map|healthz).*)"],
};
