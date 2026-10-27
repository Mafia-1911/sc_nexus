"use client";

import { type Map as MapLibre, setWorkerUrl } from "maplibre-gl";

export const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
// Copied into public/ by scripts/vendor-maplibre.mjs: the default URL is relative to the bundle chunk.
const WORKER_URL = "/vendor/maplibre-gl-worker.mjs";

export function setMapWorker() {
  setWorkerUrl(WORKER_URL);
}

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Restyle the OpenFreeMap base for the active theme: teal-navy water, quiet land and labels. */
export function restyleBasemap(map: MapLibre, own: Set<string> = new Set()) {
  const water = cssVar("--map-water");
  const land = cssVar("--map-land");
  const muted = cssVar("--text-muted");
  const halo = cssVar("--bg");
  const line = cssVar("--border");
  for (const layer of map.getStyle().layers ?? []) {
    const id = layer.id;
    if (own.has(id)) continue;
    try {
      if (layer.type === "background") map.setPaintProperty(id, "background-color", land);
      else if (layer.type === "fill") {
        map.setPaintProperty(id, "fill-color", id.includes("water") ? water : land);
        if (!id.includes("water")) map.setPaintProperty(id, "fill-opacity", 0.6);
      } else if (layer.type === "line") {
        map.setPaintProperty(id, "line-color", id.includes("water") ? water : line);
      } else if (layer.type === "symbol") {
        map.setPaintProperty(id, "text-color", muted);
        map.setPaintProperty(id, "text-halo-color", halo);
      }
    } catch {
      // some layers use data-driven paint we leave alone
    }
  }
}

/** Re-run `apply` when the theme changes (toggle or OS setting). Returns a cleanup. */
export function onThemeChange(apply: () => void): () => void {
  window.addEventListener("themechange", apply);
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", apply);
  return () => {
    window.removeEventListener("themechange", apply);
    media.removeEventListener("change", apply);
  };
}
