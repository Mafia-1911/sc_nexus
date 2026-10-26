"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

function snapshot(): Theme {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  window.addEventListener("themechange", onChange);
  return () => {
    media.removeEventListener("change", onChange);
    window.removeEventListener("themechange", onChange);
  };
}

/** Abyss (dark) follows the OS setting by default; the toggle forces either theme. */
export function ThemeToggle() {
  const theme = useSyncExternalStore<Theme | null>(subscribe, snapshot, () => null);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} theme`}
      data-testid="theme-toggle"
      className="inline-flex size-9 items-center justify-center rounded-[var(--radius-control)] border border-border-strong text-muted hover:text-text"
      onClick={() => {
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem("theme", next);
        } catch {}
        window.dispatchEvent(new CustomEvent("themechange", { detail: next }));
      }}
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
