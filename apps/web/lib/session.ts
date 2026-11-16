import { SignJWT, jwtVerify } from "jose";

/** Signed session cookie (A-118). Edge-safe: used by proxy.ts and server code alike. */
export const SESSION_COOKIE = "cportal_session";
export const SESSION_DAYS = 7;

/** Accounts are on only when AUTH_SECRET is set (the deployed site); locally the app is open. */
export function authEnabled(): boolean {
  return Boolean(process.env.AUTH_SECRET);
}

export type Session = { sub: string; email: string; name: string };

const key = () => new TextEncoder().encode(process.env.AUTH_SECRET ?? "");

export async function signSession(s: Session): Promise<string> {
  return new SignJWT({ email: s.email, name: s.name })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(s.sub)
    .setIssuedAt()
    .setExpirationTime(`${SESSION_DAYS}d`)
    .sign(key());
}

export async function readSession(token: string | undefined): Promise<Session | null> {
  if (!token || !authEnabled()) return null;
  try {
    const { payload } = await jwtVerify(token, key(), { algorithms: ["HS256"] });
    return { sub: String(payload.sub), email: String(payload.email), name: String(payload.name) };
  } catch {
    return null;
  }
}
