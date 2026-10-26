"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import {
  type GeoJSONSource,
  Map as MapLibre,
  type MapLayerMouseEvent,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { DataBadge } from "@/components/data-badge";
import { dhakaTime } from "@/lib/utils";

const STYLE = "https://tiles.openfreemap.org/styles/positron";
// Copied into public/ by scripts/vendor-maplibre.mjs: the default URL is relative to the bundle chunk.
const WORKER_URL = "/vendor/maplibre-gl-worker.mjs";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://127.0.0.1:8000/ws/live";
const CHATTOGRAM: [number, number] = [91.74, 22.08];

type Snapshot = { ts: string | null; mode: string; features: GeoJSON.Feature[]; scenario: string | null };

// Vessel states use chart slots 1–3 (validated all-pairs in both themes, 05 §2), with a legend.
const STATES = [
  { status: 0, label: "Under way", color: "--series-1" },
  { status: 1, label: "At anchor", color: "--series-2" },
  { status: 5, label: "Moored", color: "--series-3" },
] as const;

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Restyle the OpenFreeMap base for the active theme: teal-navy water, quiet land and labels. */
function restyle(map: MapLibre) {
  const water = cssVar("--map-water");
  const land = cssVar("--map-land");
  const muted = cssVar("--text-muted");
  const halo = cssVar("--bg");
  const line = cssVar("--border");
  for (const layer of map.getStyle().layers ?? []) {
    const id = layer.id;
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
  const colors = ["match", ["get", "nav_status"], ...STATES.flatMap((s) => [s.status, cssVar(s.color)]), muted];
  if (map.getLayer("vessels")) {
    map.setPaintProperty("vessels", "circle-color", colors as unknown as string);
    map.setPaintProperty("vessels", "circle-stroke-color", cssVar("--surface"));
  }
}

export function VesselMap({ scenario }: { scenario: string }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  // The first snapshot can arrive before the map's style loads; keep it for the load handler.
  const latest = useRef<GeoJSON.Feature[]>([]);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!container.current) return;
    setWorkerUrl(WORKER_URL);
    const map = new MapLibre({
      container: container.current,
      style: STYLE,
      center: CHATTOGRAM,
      zoom: 8.6,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      map.addSource("vessels", { type: "geojson", data: { type: "FeatureCollection", features: latest.current } });
      map.addLayer({
        id: "vessels",
        type: "circle",
        source: "vessels",
        paint: { "circle-radius": 4.5, "circle-stroke-width": 1, "circle-color": "#888" },
      });
      // A larger invisible target for hover (05 §5: hit target larger than the mark).
      map.addLayer({
        id: "vessels-hit",
        type: "circle",
        source: "vessels",
        paint: { "circle-radius": 11, "circle-opacity": 0 },
      });
      restyle(map);
      const popup = new Popup({ closeButton: false, closeOnClick: false });
      map.on("mouseenter", "vessels-hit", (e: MapLayerMouseEvent) => {
        map.getCanvas().style.cursor = "pointer";
        const f = e.features?.[0];
        if (!f || f.geometry.type !== "Point") return;
        const p = f.properties as Record<string, string | number | null>;
        const state = STATES.find((s) => s.status === Number(p.nav_status))?.label ?? "Unknown";
        popup
          .setLngLat(f.geometry.coordinates as [number, number])
          .setHTML(
            `<strong>${p.name ?? p.mmsi}</strong><br/>${state} · ${Number(p.sog_kn ?? 0).toFixed(1)} kn<br/>` +
              `<span style="opacity:.7">${p.data_mode} · MMSI ${p.mmsi}</span>`,
          )
          .addTo(map);
      });
      map.on("mouseleave", "vessels-hit", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
    });
    // Every tile drawn and nothing animating: the e2e screenshots wait for this.
    map.on("idle", () => container.current?.setAttribute("data-idle", "true"));
    const onTheme = () => {
      if (!map.isStyleLoaded()) return;
      restyle(map);
      map.triggerRepaint(); // unchanged paint is a no-op; repaint anyway so "idle" follows
    };
    window.addEventListener("themechange", onTheme);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", onTheme);
    return () => {
      window.removeEventListener("themechange", onTheme);
      media.removeEventListener("change", onTheme);
      map.remove();
    };
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let delay = 1000;
    let closed = false;
    const connect = () => {
      socket = new WebSocket(`${WS_URL}?scenario=${encodeURIComponent(scenario)}`);
      socket.onopen = () => {
        setConnected(true);
        delay = 1000;
      };
      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data as string);
        if (msg.type !== "positions") return;
        setSnap(msg as Snapshot);
        latest.current = msg.features;
        const source = mapRef.current?.getSource("vessels") as GeoJSONSource | undefined;
        source?.setData({ type: "FeatureCollection", features: msg.features });
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, (delay = Math.min(delay * 2, 15000)));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [scenario]);

  const counts = STATES.map((s) => ({
    ...s,
    n: snap?.features.filter((f) => Number(f.properties?.nav_status) === s.status).length ?? 0,
  }));

  return (
    <div className="relative h-[460px] overflow-hidden rounded-[var(--radius-control)] border border-border">
      {/* Sized with h-full, not inset-0: maplibre-gl.css makes .maplibregl-map position: relative. */}
      <div ref={container} className="h-full w-full" data-testid="vessel-map" />
      <div className="absolute left-3 top-3 flex flex-col gap-2 rounded-[var(--radius-control)] border border-border bg-surface/95 p-3 text-xs shadow-sm">
        <div className="flex items-center gap-2">
          <DataBadge mode={snap?.mode ?? "none"} sources={["DS-AIS-01"]} asOf={snap?.ts} />
          <span className="tabular text-muted" data-testid="vessel-count">
            {snap ? `${snap.features.length} vessels` : connected ? "waiting for positions…" : "connecting…"}
          </span>
        </div>
        {snap?.ts ? <span className="tabular text-muted">Replay clock {dhakaTime(snap.ts)}</span> : null}
        <ul className="flex flex-col gap-1">
          {counts.map((s) => (
            <li key={s.status} className="flex items-center gap-2">
              <span aria-hidden className="size-2.5 rounded-full" style={{ background: `var(${s.color})` }} />
              <span>{s.label}</span>
              <span className="tabular ml-auto text-muted">{s.n}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
