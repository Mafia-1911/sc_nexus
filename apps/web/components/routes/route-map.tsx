"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { type GeoJSONSource, LngLatBounds, Map as MapLibre, NavigationControl } from "maplibre-gl";
import { useEffect, useRef } from "react";

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

export function RouteMap({ plan }: { plan: Plan | null }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const current = useRef(plan);

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

  return <div ref={container} className="h-full w-full" data-testid="route-map" />;
}
