import { LogOut } from "lucide-react";

import { logout } from "@/app/(public)/auth-actions";
import { currentUser } from "@/lib/auth";

/** Signed-in name and a sign-out button (only when accounts are on, A-118). */
export async function UserMenu() {
  const user = await currentUser();
  if (!user) return null;
  return (
    <form action={logout} className="flex items-center gap-2 text-sm">
      <span className="hidden text-muted sm:inline">{user.name}</span>
      <button type="submit" title="Sign out" className="rounded-[var(--radius-control)] border border-border p-2 text-muted hover:text-text">
        <LogOut className="h-4 w-4" aria-hidden />
        <span className="sr-only">Sign out</span>
      </button>
    </form>
  );
}
