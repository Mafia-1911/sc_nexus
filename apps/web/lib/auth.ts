import "server-only";

import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";

import { cookies } from "next/headers";
import { Pool } from "pg";

import { SESSION_COOKIE, SESSION_DAYS, type Session, authEnabled, readSession, signSession } from "@/lib/session";

const scryptAsync = promisify(scrypt) as (pw: string, salt: Buffer, len: number) => Promise<Buffer>;
// A well-formed hash of nothing: verifying against it costs the same as a real account.
const DUMMY = `scrypt$${Buffer.alloc(16).toString("base64")}$${Buffer.alloc(64).toString("base64")}`;
let pool: Pool | null = null;

/** The accounts table lives in the platform database (Neon when deployed): `app_user`. */
function db(): Pool {
  pool ??= new Pool({ connectionString: process.env.AUTH_DATABASE_URL, max: 3 });
  return pool;
}

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const hash = await scryptAsync(password, salt, 64);
  return `scrypt$${salt.toString("base64")}$${hash.toString("base64")}`;
}

export async function checkPassword(password: string, stored: string): Promise<boolean> {
  const [kind, salt, hash] = stored.split("$");
  if (kind !== "scrypt" || !salt || !hash) return false;
  const want = Buffer.from(hash, "base64");
  const got = await scryptAsync(password, Buffer.from(salt, "base64"), want.length);
  return timingSafeEqual(want, got);
}

export async function createUser(email: string, name: string, password: string): Promise<Session | "taken"> {
  const hash = await hashPassword(password);
  const res = await db().query<{ id: string }>(
    "INSERT INTO app_user (email, name, password_hash) VALUES ($1, $2, $3) ON CONFLICT (email) DO NOTHING RETURNING id",
    [email, name, hash],
  );
  if (!res.rowCount) return "taken";
  return { sub: res.rows[0].id, email, name };
}

export async function verifyUser(email: string, password: string): Promise<Session | null> {
  const res = await db().query<{ id: string; name: string; password_hash: string }>(
    "SELECT id, name, password_hash FROM app_user WHERE email = $1",
    [email],
  );
  const row = res.rows[0];
  // Same work whether or not the account exists: no timing hint about registered emails.
  const ok = await checkPassword(password, row?.password_hash ?? DUMMY);
  if (!row || !ok) return null;
  await db().query("UPDATE app_user SET last_login_at = now() WHERE id = $1", [row.id]);
  return { sub: row.id, email, name: row.name };
}

export async function startSession(s: Session): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, await signSession(s), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DAYS * 24 * 3600,
  });
}

export async function endSession(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}

export async function currentUser(): Promise<Session | null> {
  if (!authEnabled()) return null;
  return readSession((await cookies()).get(SESSION_COOKIE)?.value);
}
