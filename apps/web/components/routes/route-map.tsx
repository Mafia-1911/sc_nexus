"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { type GeoJSONSource, LngLatBounds, Map as MapLibre, NavigationControl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { type Plan, MODE_VAR } from "@/lib/c3";
import { MAP_STYLE, cssVar, onThemeChange, restyleBasemap, setMapWorker } from "@/lib/map-theme";

function lines(plan: Plan | null) {
  return {
    type: "FeatureCollection" as const,
    features: (plan?.legs ?? [])
      .filter((l) => l.coords.length >= 2 && l.mode !== "transfer")
      .map((l) => ({
        type: "Feature" as const,
        geometry: { type: "LineString" as const, coordinates: l.coords },
        properties: { mode: l.mode, dashed: l.mode !== "road" },
      })),
  };
}

function paint(map: MapLibre) {
  restyleBasemap(map, new Set(["legs"]));
  if (map.getLayer("legs"))
    map.setPaintProperty("legs", "line-color", ["match", ["get", "mode"], ...Object.entries(MODE_VAR).flatMap(([k, v]) => [k, cssVar(v)]), cssVar("--text-muted")] as unknown as string);
}

type Traffic = "live" | "modelled" | "off";
type Modelled = { hour: number; corridor_factor: number; geojson: GeoJSON.FeatureCollection };

const CONGESTION = ["match", ["get", "congestion"], "low", "#2f9e6b", "moderate", "#e0a800", "heavy", "#e8590c", "severe", "#c92a2a", "#8a94a6"];

/** Traffic under the route: live congestion lines (Mapbox, proxied) or C3's own model. */
function addTraffic(map: MapLibre, modelled: Modelled | null) {
  if (!map.getSource("traffic-live")) {
    map.addSource("traffic-live", {
      type: "vector",
      tiles: [`${window.location.origin}/traffic/tiles/{z}/{x}/{y}.pbf`],
      minzoom: 6,
      maxzoom: 16,
      attribution: "© Mapbox",
    });
    map.addLayer(
      {
        id: "traffic-live",
        type: "line",
        source: "traffic-live",
        "source-layer": "traffic",
        layout: { visibility: "none" },
        paint: {
          "line-color": CONGESTION as unknown as string,
          "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.8, 12, 2.5, 16, 5],
          "line-opacity": 0.85,
        },
      },
      map.getLayer("legs") ? "legs" : undefined,
    );
  }
  if (modelled && !map.getSource("traffic-model")) {
    map.addSource("traffic-model", { type: "geojson", data: modelled.geojson });
    map.addLayer(
      {
        id: "traffic-model-zone",
        type: "fill",
        source: "traffic-model",
        filter: ["==", ["get", "zone"], "dhaka"],
        layout: { visibility: "none" },
        paint: { "fill-color": "#e8590c", "fill-opacity": ["*", 0.5, ["-", 1, ["get", "factor"]]] },
      },
      map.getLayer("legs") ? "legs" : undefined,
    );
    map.addLayer({
      id: "traffic-model-ban",
      type: "line",
      source: "traffic-model",
      filter: ["all", ["==", ["get", "zone"], "truck_ban"], ["==", ["get", "active"], true]],
      layout: { visibility: "none" },
      paint: { "line-color": "#c92a2a", "line-width": 2, "line-dasharray": [2, 2] },
    });
  }
}

function showTraffic(map: MapLibre, mode: Traffic) {
  const set = (id: string, on: boolean) => map.getLayer(id) && map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
  set("traffic-live", mode === "live");
  set("traffic-model-zone", mode === "modelled");
  set("traffic-model-ban", mode === "modelled");
}

export function RouteMap({ plan }: { plan: Plan | null }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const current = useRef(plan);
  const [live, setLive] = useState<boolean | null>(null);
  const [modelled, setModelled] = useState<Modelled | null>(null);
  const [mode, setMode] = useState<Traffic>("modelled");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let gone = false;
    Promise.all([
      fetch("/traffic/status").then((r) => (r.ok ? r.json() : null)),
      fetch("/traffic/modelled").then((r) => (r.ok ? r.json() : null)),
    ]).then(([status, model]) => {
      if (gone) return;
      const isLive = Boolean(status?.data?.live);
      setLive(isLive);
      setModelled(model?.data ?? null);
      setMode(isLive ? "live" : "modelled");
    });
    return () => {
      gone = true;
    };
  }, []);


  useEffect(() => {
    current.current = plan;
    const map = mapRef.current;
    const source = map?.getSource("legs") as GeoJSONSource | undefined;
    if (!map || !source) return;
    source.setData(lines(plan));
    const pts = plan?.legs.flatMap((l) => l.coords) ?? [];
    if (pts.length) {
      const b = new LngLatBounds();
      pts.forEach((c) => b.extend(c as [number, number]));
      map.fitBounds(b, { padding: 40, duration: 0 });
    }
  }, [plan]);

  useEffect(() => {
    if (!container.current) return;
    setMapWorker();
    const map = new MapLibre({ container: container.current, style: MAP_STYLE, center: [90.9, 23.1], zoom: 6.6, attributionControl: { compact: true } });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("legs", { type: "geojson", data: lines(current.current) });
      map.addLayer({ id: "legs", type: "line", source: "legs", paint: { "line-width": 4, "line-dasharray": [1, 0] } });
      paint(map);
      setReady(true);
      const pts = current.current?.legs.flatMap((l) => l.coords) ?? [];
      if (pts.length) {
        const b = new LngLatBounds();
        pts.forEach((c) => b.extend(c as [number, number]));
        map.fitBounds(b, { padding: 40, duration: 0 });
      }
    });
    map.on("idle", () => container.current?.setAttribute("data-idle", "true"));
    const off = onThemeChange(() => map.isStyleLoaded() && paint(map));
    return () => {
      off();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    addTraffic(map, modelled);
    showTraffic(map, mode);
  }, [ready, mode, modelled]);

  const legend =
    mode === "live"
      ? "Live congestion (Mapbox): low · moderate · heavy · severe; grey = no live data"
      : mode === "modelled" && modelled
        ? `Modelled at ${String(modelled.hour).padStart(2, "0")}:00 Dhaka: trucks at ${Math.round(
            (modelled.geojson.features[0]?.properties?.factor ?? 1) * 100,
          )}% of free flow in the shaded zone, ${Math.round(modelled.corridor_factor * 100)}% on the corridor; dashed = truck ban in force (C3 estimates, not live)`
        : null;

  return (
    <div className="relative h-full w-full">
      <div ref={container} className="h-full w-full" data-testid="route-map" />
      <div className="absolute left-2 top-2 z-10 flex max-w-[22rem] flex-col gap-1 text-xs" data-testid="traffic-control">
        <div className="flex overflow-hidden rounded-[var(--radius-control)] border border-border bg-surface shadow-sm" role="group" aria-label="Traffic layer">
          {(["live", "modelled", "off"] as const).map((m) => (
            <button
              key={m}
              type="button"
              disabled={m === "live" && !live}
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              title={m === "live" && !live ? "No live traffic source configured" : undefined}
              className={`px-2 py-1 capitalize disabled:opacity-40 ${mode === m ? "bg-primary text-on-primary" : "text-muted hover:text-text"}`}
            >
              {m === "live" ? "Live traffic" : m === "modelled" ? "Modelled" : "Off"}
            </button>
          ))}
        </div>
        {legend ? (
          <p className="rounded-[var(--radius-control)] bg-surface/90 px-2 py-1 text-muted shadow-sm" data-testid="traffic-legend">
            {legend}
          </p>
        ) : null}
      </div>
    </div>
  );
}
