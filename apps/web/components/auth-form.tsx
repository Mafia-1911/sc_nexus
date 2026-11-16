"use client";

import Link from "next/link";
import { useActionState } from "react";

import { type FormState, login, signup } from "@/app/(public)/auth-actions";

const FIELD =
  "w-full rounded-[var(--radius-control)] border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-primary";

/** Sign-up and login share one form; the server actions validate and set the session. */
export function AuthForm({ mode, next }: { mode: "login" | "signup"; next?: string }) {
  const [state, action, pending] = useActionState<FormState, FormData>(mode === "login" ? login : signup, {});
  return (
    <form action={action} className="flex flex-col gap-3" data-testid={`${mode}-form`}>
      <input type="hidden" name="next" value={next ?? "/"} />
      {mode === "signup" ? (
        <label className="flex flex-col gap-1 text-sm">
          Name
          <input name="name" required autoComplete="name" className={FIELD} />
        </label>
      ) : null}
      <label className="flex flex-col gap-1 text-sm">
        Email
        <input name="email" type="email" required autoComplete="email" className={FIELD} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Password
        <input
          name="password"
          type="password"
          required
          minLength={mode === "signup" ? 10 : undefined}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          className={FIELD}
        />
      </label>
      {state.error ? (
        <p role="alert" className="text-sm text-danger">
          {state.error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="rounded-[var(--radius-control)] bg-primary px-4 py-2 text-sm font-medium text-on-primary disabled:opacity-60"
      >
        {pending ? "One moment…" : mode === "login" ? "Log in" : "Create account"}
      </button>
      <p className="text-center text-xs text-muted">
        {mode === "login" ? (
          <>
            New here? <Link className="text-primary underline" href={`/signup${next ? `?next=${encodeURIComponent(next)}` : ""}`}>Create an account</Link>
          </>
        ) : (
          <>
            Have an account? <Link className="text-primary underline" href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`}>Log in</Link>
          </>
        )}
      </p>
    </form>
  );
}
