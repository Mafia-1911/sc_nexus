"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { Map as MapLibre, type MapLayerMouseEvent, NavigationControl, Popup } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { MAP_STYLE, cssVar, onThemeChange, restyleBasemap, setMapWorker } from "@/lib/map-theme";

type FC = GeoJSON.FeatureCollection;

/** Text from CPA's pages goes into popups: escape it (it is someone else's content). */
function esc(v: unknown): string {
  return String(v ?? "—").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}

function when(v: unknown): string {
  if (!v) return "—";
  return new Date(String(v)).toLocaleString("en-GB", { timeZone: "Asia/Dhaka", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function paint(map: MapLibre) {
  restyleBasemap(map, new Set(["berths", "ships", "ships-hit"]));
  map.setPaintProperty("berths", "circle-color", ["case", ["get", "occupied"], cssVar("--ok"), cssVar("--border-strong")] as unknown as string);
  map.setPaintProperty("ships", "circle-color", ["match", ["get", "status"], "at_berth", cssVar("--ok"), "at_anchorage", cssVar("--warn"), cssVar("--info")] as unknown as string);
  map.setPaintProperty("ships", "circle-stroke-color", cssVar("--surface"));
}

/** Chattogram now (CPA TOS + PCS): ships at berth at approximate berth positions, ships at the
 *  outer anchorage at illustrative spots among GFW anchorage cells. */
export function PortLiveMap({ vessels, berths }: { vessels: FC; berths: FC }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    setMapWorker();
    const map = new MapLibre({ container: container.current, style: MAP_STYLE, center: [91.79, 22.2], zoom: 10.2, attributionControl: { compact: true } });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("berths", { type: "geojson", data: berths });
      map.addSource("ships", { type: "geojson", data: vessels });
      map.addLayer({ id: "berths", type: "circle", source: "berths", paint: { "circle-radius": 3, "circle-opacity": 0.9 } });
      map.addLayer({ id: "ships", type: "circle", source: "ships", paint: { "circle-radius": 5, "circle-stroke-width": 1 } });
      map.addLayer({ id: "ships-hit", type: "circle", source: "ships", paint: { "circle-radius": 11, "circle-opacity": 0 } });
      paint(map);
      const popup = new Popup({ closeButton: false, closeOnClick: false, maxWidth: "320px" });
      map.on("mouseenter", "ships-hit", (e: MapLayerMouseEvent) => {
        map.getCanvas().style.cursor = "pointer";
        const f = e.features?.[0];
        if (!f || f.geometry.type !== "Point") return;
        const p = f.properties as Record<string, unknown>;
        const imp = typeof p.import === "string" ? JSON.parse(p.import) : (p.import as Record<string, number> | null);
        const exp = typeof p.export === "string" ? JSON.parse(p.export) : (p.export as Record<string, number> | null);
        const cargo = imp?.total_teu || exp?.total_teu
          ? `<br/>${esc(imp?.total_teu ?? 0)} TEU import (${esc(imp?.discharged_teu ?? 0)} discharged) · ${esc(exp?.total_teu ?? 0)} TEU export`
          : "";
        popup
          .setLngLat(f.geometry.coordinates as [number, number])
          .setHTML(
            `<strong>${esc(p.name)}</strong> · ${esc(p.status === "at_berth" ? `at ${p.berth}` : "outer anchorage")}` +
              `<br/>arrived ${esc(when(p.ata))}${p.berthed ? ` · berthed ${esc(when(p.berthed))}` : ""}<br/>ETD ${esc(when(p.etd))} · agent ${esc(p.agent)}` +
              cargo +
              `<br/><span style="opacity:.7">${esc(p.position)}</span>`,
          )
          .addTo(map);
      });
      map.on("mouseleave", "ships-hit", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
    });
    map.on("idle", () => container.current?.setAttribute("data-idle", "true"));
    const off = onThemeChange(() => map.isStyleLoaded() && paint(map));
    return () => {
      off();
      map.remove();
    };
  }, [vessels, berths]);
  return <div ref={container} className="h-[440px] w-full rounded-[var(--radius-control)]" data-testid="port-live-map" />;
}
