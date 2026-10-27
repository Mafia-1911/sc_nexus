"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { type GeoJSONSource, Map as MapLibre, type MapLayerMouseEvent, NavigationControl } from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { Highlight } from "@/components/network/graph-canvas";
import { BAND_VAR, type GraphEdge, type GraphNode } from "@/lib/c1";
import { MAP_STYLE, cssVar, onThemeChange, restyleBasemap, setMapWorker } from "@/lib/map-theme";

const BANGLADESH: [[number, number], [number, number]] = [
  [88.6, 21.0],
  [92.4, 25.4],
];
const OWN = new Set(["links", "nodes", "nodes-hit"]);

function data(nodes: GraphNode[], edges: GraphEdge[], highlight: Highlight | null, selected: string | null) {
  const at = new Map(nodes.filter((n) => n.lat !== null && n.lon !== null).map((n) => [n.id, [n.lon!, n.lat!]]));
  const maxValue = Math.max(1, ...nodes.map((n) => n.downstream_open_order_value_usd));
  const state = (id: string) =>
    highlight?.disrupted.has(id) ? "disrupted" : highlight?.impacted.has(id) ? "impacted" : highlight ? "faded" : "normal";
  return {
    nodes: {
      type: "FeatureCollection" as const,
      features: nodes
        .filter((n) => at.has(n.id))
        .map((n) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: at.get(n.id)! },
          properties: {
            id: n.id,
            name: n.name,
            kind: n.kind,
            band: n.kind === "port" ? "port" : n.type === "customer_site" ? "customer" : (n.risk_band ?? "low"),
            radius: n.kind === "port" ? 9 : 3 + 7 * Math.sqrt(n.downstream_open_order_value_usd / maxValue),
            state: state(n.id),
            selected: n.id === selected,
          },
        })),
    },
    links: {
      type: "FeatureCollection" as const,
      features: edges
        .filter((e) => at.has(e.source) && at.has(e.target))
        .map((e) => ({
          type: "Feature" as const,
          geometry: { type: "LineString" as const, coordinates: [at.get(e.source)!, at.get(e.target)!] },
          properties: { kind: e.kind, share: e.share, touches: e.source === selected || e.target === selected },
        })),
    },
  };
}

function paint(map: MapLibre) {
  restyleBasemap(map, OWN);
  if (!map.getLayer("nodes")) return;
  const band = ["match", ["get", "band"], "port", cssVar("--primary"), "customer", cssVar("--text-muted"),
    ...Object.entries(BAND_VAR).flatMap(([k, v]) => [k, cssVar(v)]), cssVar("--text-muted")];
  map.setPaintProperty("nodes", "circle-color", [
    "match", ["get", "state"], "disrupted", cssVar("--danger"), "impacted", cssVar("--warn"), band,
  ] as unknown as string);
  map.setPaintProperty("nodes", "circle-stroke-color", ["case", ["get", "selected"], cssVar("--text"), cssVar("--surface")] as unknown as string);
  map.setPaintProperty("links", "line-color", ["case", ["get", "touches"], cssVar("--primary"),
    ["==", ["get", "kind"], "supply"], cssVar("--border-strong"), cssVar("--info")] as unknown as string);
}

export function GeoMap({
  nodes,
  edges,
  selected,
  highlight,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  highlight: Highlight | null;
  onSelect: (id: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const select = useRef(onSelect);
  const current = useRef({ nodes, edges, highlight, selected });

  useEffect(() => {
    select.current = onSelect;
    current.current = { nodes, edges, highlight, selected };
    const map = mapRef.current;
    if (!map?.isStyleLoaded() || !map.getSource("nodes")) return;
    const d = data(nodes, edges, highlight, selected);
    (map.getSource("nodes") as GeoJSONSource).setData(d.nodes);
    (map.getSource("links") as GeoJSONSource).setData(d.links);
  }, [nodes, edges, highlight, selected, onSelect]);

  useEffect(() => {
    if (!container.current) return;
    setMapWorker();
    const map = new MapLibre({ container: container.current, style: MAP_STYLE, bounds: BANGLADESH, attributionControl: { compact: true } });
    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      const { nodes: n, edges: e, highlight: h, selected: s } = current.current;
      const d = data(n, e, h, s);
      map.addSource("links", { type: "geojson", data: d.links });
      map.addSource("nodes", { type: "geojson", data: d.nodes });
      map.addLayer({
        id: "links",
        type: "line",
        source: "links",
        paint: {
          "line-width": ["case", ["get", "touches"], 2, ["+", 0.4, ["*", ["get", "share"], 1.2]]],
          "line-opacity": ["case", ["get", "touches"], 0.9, ["==", ["get", "kind"], "export"], 0.12, 0.4],
        },
      });
      map.addLayer({
        id: "nodes",
        type: "circle",
        source: "nodes",
        paint: {
          "circle-radius": ["get", "radius"],
          "circle-stroke-width": ["case", ["get", "selected"], 2.5, 1],
          "circle-opacity": ["case", ["==", ["get", "state"], "faded"], 0.25, 1],
        },
      });
      map.addLayer({ id: "nodes-hit", type: "circle", source: "nodes", paint: { "circle-radius": 12, "circle-opacity": 0 } });
      paint(map);
      map.on("click", "nodes-hit", (ev: MapLayerMouseEvent) => {
        const id = ev.features?.[0]?.properties?.id;
        if (typeof id === "string") select.current(id);
      });
      map.on("mouseenter", "nodes-hit", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "nodes-hit", () => (map.getCanvas().style.cursor = ""));
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
      mapRef.current = null;
    };
  }, []);

  return <div ref={container} className="h-full w-full" data-testid="supply-map" />;
}
