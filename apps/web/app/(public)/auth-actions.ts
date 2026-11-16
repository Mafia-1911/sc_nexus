"use server";

import { redirect } from "next/navigation";

import { createUser, endSession, startSession, verifyUser } from "@/lib/auth";
import { authEnabled } from "@/lib/session";

export type FormState = { error?: string };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Only same-site paths after login (no open redirect). */
function safeNext(value: FormDataEntryValue | null): string {
  const next = typeof value === "string" ? value : "/";
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export async function signup(_: FormState, form: FormData): Promise<FormState> {
  if (!authEnabled()) redirect("/");
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const name = String(form.get("name") ?? "").trim().slice(0, 120);
  const password = String(form.get("password") ?? "");
  if (!EMAIL.test(email) || email.length > 254) return { error: "Enter a valid email address." };
  if (!name) return { error: "Tell us your name." };
  if (password.length < 10) return { error: "Use a password of at least 10 characters." };
  const user = await createUser(email, name, password);
  if (user === "taken") return { error: "An account with this email exists. Log in instead." };
  await startSession(user);
  redirect(safeNext(form.get("next")));
}

export async function login(_: FormState, form: FormData): Promise<FormState> {
  if (!authEnabled()) redirect("/");
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  const password = String(form.get("password") ?? "");
  const user = EMAIL.test(email) ? await verifyUser(email, password) : null;
  if (!user) return { error: "Email or password is not right." };
  await startSession(user);
  redirect(safeNext(form.get("next")));
}

export async function logout(): Promise<void> {
  await endSession();
  redirect("/welcome");
}
