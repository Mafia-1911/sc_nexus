"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

/** Which synthetic scenario sits next to the real data (cookie `scenario`; API `?scenario=`). */
export function ScenarioSwitcher({
  current,
  options,
}: {
  current: string;
  options: ReadonlyArray<{ key: string; label: string }>;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      <span className="hidden md:inline">Scenario</span>
      <select
        aria-label="Scenario"
        className="h-9 rounded-[var(--radius-control)] border border-border-strong bg-surface px-2 text-sm text-text"
        value={current}
        disabled={pending}
        onChange={(e) => {
          document.cookie = `scenario=${encodeURIComponent(e.target.value)}; path=/; max-age=31536000; samesite=lax`;
          start(() => router.refresh());
        }}
      >
        {options.map((o) => (
          <option key={o.key || "real"} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
