"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

type Option = { key: string; label: string };

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax`;
}

/** What the app shows: real data at a moment (cookie `asof`: today, yesterday, tomorrow or a
 *  date), or a synthetic scenario (cookie `scenario`; "" = real data). */
export function ScenarioSwitcher({
  current,
  asOf,
  scenarios,
  days,
}: {
  current: string;
  asOf: string;
  scenarios: ReadonlyArray<Option>;
  days: ReadonlyArray<Option>;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const isDate = /^\d{4}-\d{2}-\d{2}$/.test(asOf);
  const [custom, setCustom] = useState(isDate);
  const value = current ? `scn:${current}` : custom || isDate ? "real:custom" : `real:${asOf}`;
  const apply = (scenario: string, day: string) => {
    setCookie("scenario", scenario);
    setCookie("asof", day);
    start(() => router.refresh());
  };
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span className="hidden md:inline">Showing</span>
      <select
        aria-label="Data"
        data-testid="data-select"
        className="h-9 rounded-[var(--radius-control)] border border-border-strong bg-surface px-2 text-sm text-text"
        value={value}
        disabled={pending}
        onChange={(e) => {
          const [kind, key] = e.target.value.split(":");
          if (kind === "scn") {
            setCustom(false);
            apply(key, asOf);
          } else if (key === "custom") {
            setCustom(true);
          } else {
            setCustom(false);
            apply("", key);
          }
        }}
      >
        <optgroup label="Real data">
          {days.map((d) => (
            <option key={d.key} value={`real:${d.key}`}>
              {d.label}
            </option>
          ))}
          <option value="real:custom">Custom date…</option>
        </optgroup>
        <optgroup label="Synthetic scenarios (fictional firms)">
          {scenarios.map((s) => (
            <option key={s.key} value={`scn:${s.key}`}>
              {s.label}
            </option>
          ))}
        </optgroup>
      </select>
      {!current && (custom || isDate) ? (
        <input
          type="date"
          aria-label="Date"
          data-testid="data-date"
          className="h-9 rounded-[var(--radius-control)] border border-border-strong bg-surface px-2 text-sm text-text"
          defaultValue={isDate ? asOf : ""}
          disabled={pending}
          onChange={(e) => e.target.value && apply("", e.target.value)}
        />
      ) : null}
    </div>
  );
}
