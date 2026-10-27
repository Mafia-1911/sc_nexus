"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { type GeoJSONSource, Map as MapLibre, type MapLayerMouseEvent, NavigationControl } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { EventItem } from "@/lib/c2";
import { MAP_STYLE, cssVar, onThemeChange, restyleBasemap, setMapWorker } from "@/lib/map-theme";

const OWN = new Set(["events", "events-hit"]);

function collection(events: EventItem[], selected: string | null) {
  return {
    type: "FeatureCollection" as const,
    features: events
      .filter((e) => e.geometry && (e.geometry as { type?: string }).type === "Point")
      .map((e) => ({
        type: "Feature" as const,
        geometry: e.geometry as unknown as GeoJSON.Point,
        properties: {
          id: e.id,
          news: e.source_id === "c2",
          radius: 5 + 10 * (e.severity ?? 0.3),
          selected: e.id === selected,
        },
      })),
  };
}

function paint(map: MapLibre) {
  restyleBasemap(map, OWN);
  if (!map.getLayer("events")) return;
  map.setPaintProperty("events", "circle-color", ["case", ["get", "news"], cssVar("--warn"), cssVar("--info")] as unknown as string);
  map.setPaintProperty("events", "circle-stroke-color", ["case", ["get", "selected"], cssVar("--text"), cssVar("--surface")] as unknown as string);
}

/** Event footprints (C2 §9): news events (amber) and feed events (blue), sized by severity. */
export function EventMap({ events, selected, onSelect }: { events: EventItem[]; selected: string | null; onSelect: (id: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const current = useRef({ events, selected, onSelect });

  useEffect(() => {
    current.current = { events, selected, onSelect };
    const source = mapRef.current?.getSource("events") as GeoJSONSource | undefined;
    source?.setData(collection(events, selected));
  }, [events, selected, onSelect]);

  useEffect(() => {
    if (!container.current) return;
    setMapWorker();
    const map = new MapLibre({ container: container.current, style: MAP_STYLE, center: [88, 18], zoom: 2.6, attributionControl: { compact: true } });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("events", { type: "geojson", data: collection(current.current.events, current.current.selected) });
      map.addLayer({
        id: "events",
        type: "circle",
        source: "events",
        paint: { "circle-radius": ["get", "radius"], "circle-opacity": 0.8, "circle-stroke-width": ["case", ["get", "selected"], 2.5, 1] },
      });
      map.addLayer({ id: "events-hit", type: "circle", source: "events", paint: { "circle-radius": 14, "circle-opacity": 0 } });
      paint(map);
      map.on("click", "events-hit", (ev: MapLayerMouseEvent) => {
        const id = ev.features?.[0]?.properties?.id;
        if (typeof id === "string") current.current.onSelect(id);
      });
      map.on("mouseenter", "events-hit", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "events-hit", () => (map.getCanvas().style.cursor = ""));
    });
    map.on("idle", () => container.current?.setAttribute("data-idle", "true"));
    const off = onThemeChange(() => {
      if (!map.isStyleLoaded()) return;
      paint(map);
      map.triggerRepaint();
    });
    return () => {
      off();
      map.remove();
    };
  }, []);

  return <div ref={container} className="h-full w-full" data-testid="event-map" />;
}
