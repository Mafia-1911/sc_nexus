"use client";

import Graph from "graphology";
import { useEffect, useRef } from "react";
import Sigma from "sigma";

import { BAND_VAR, type GraphEdge, type GraphNode } from "@/lib/c1";
import { cssVar, onThemeChange } from "@/lib/map-theme";

/** Left-to-right tiers (05 §6 "layered flow layout"): where material starts, to where it ships. */
function tier(n: GraphNode): number {
  if (n.type === "hub") return 1;
  if (n.type === "gateway") return 4.6;
  if (n.type === "customer_site") return 5.6;
  if (n.country !== "BD") return 0;
  if (n.type === "spinning_mill") return 2;
  if (n.type === "garment_factory" || n.type === "pharma_plant") return 4;
  return 3;
}

/** Positions: x by tier; y by industry, then by the mean position of each node's neighbours
 *  (one barycentre pass from the plants outwards, which removes most crossings). */
function layout(nodes: GraphNode[], edges: GraphEdge[]): Map<string, { x: number; y: number }> {
  const byTier = new Map<number, GraphNode[]>();
  for (const n of nodes) byTier.set(tier(n), [...(byTier.get(tier(n)) ?? []), n]);
  const pos = new Map<string, { x: number; y: number }>();
  const neighbours = new Map<string, string[]>();
  for (const e of edges) {
    neighbours.set(e.source, [...(neighbours.get(e.source) ?? []), e.target]);
    neighbours.set(e.target, [...(neighbours.get(e.target) ?? []), e.source]);
  }
  const industryRank = (n: GraphNode) => (n.industry === "pharma" ? 1 : 0);
  const place = (t: number, ordered: GraphNode[]) => {
    ordered.forEach((n, i) => pos.set(n.id, { x: t * 320, y: ((i + 0.5) / ordered.length) * 1000 }));
  };
  const plants = (byTier.get(4) ?? []).sort(
    (a, b) => industryRank(a) - industryRank(b) || (a.cluster ?? "").localeCompare(b.cluster ?? "") || a.name.localeCompare(b.name),
  );
  place(4, plants);
  const bary = (n: GraphNode) => {
    const ys = (neighbours.get(n.id) ?? []).map((m) => pos.get(m)?.y).filter((y): y is number => y !== undefined);
    return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : 500 + industryRank(n) * 400;
  };
  // Within a tier: industry, then type (mills apart from trims), then barycentre.
  for (const t of [3, 2, 5.6, 0, 1]) {
    const ordered = (byTier.get(t) ?? []).sort(
      (a, b) => industryRank(a) - industryRank(b) || a.type.localeCompare(b.type) || bary(a) - bary(b),
    );
    place(t, ordered);
  }
  for (const n of byTier.get(4.6) ?? []) pos.set(n.id, { x: 4.6 * 320, y: 500 });
  return pos;
}

export type Highlight = { disrupted: Set<string>; impacted: Set<string> };

export function GraphCanvas({
  nodes,
  edges,
  selected,
  highlight,
  labelled,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  highlight: Highlight | null;
  labelled: Set<string>;
  onSelect: (id: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const state = useRef({ selected, highlight, labelled, onSelect });

  useEffect(() => {
    state.current = { selected, highlight, labelled, onSelect };
    sigmaRef.current?.refresh();
  }, [selected, highlight, labelled, onSelect]);

  useEffect(() => {
    if (!container.current) return;
    const graph = new Graph({ multi: false, type: "directed" });
    const pos = layout(nodes, edges);
    const maxValue = Math.max(1, ...nodes.map((n) => n.downstream_open_order_value_usd));
    for (const n of nodes) {
      const port = n.kind === "port";
      graph.addNode(n.id, {
        ...pos.get(n.id),
        label: n.name,
        // Sigma draws sizes against the viewport; these read as roughly 4–18 px.
        size: port ? 28 : n.type === "customer_site" ? 8 : 9 + 26 * Math.sqrt(n.downstream_open_order_value_usd / maxValue),
        band: n.risk_band,
        kind: n.kind,
        type: n.type,
      });
    }
    for (const e of edges) {
      if (!graph.hasNode(e.source) || !graph.hasNode(e.target) || graph.hasEdge(e.source, e.target)) continue;
      graph.addEdge(e.source, e.target, { size: 0.4 + e.share * 1.2, kind: e.kind });
    }
    const colors = { ink: "", muted: "", line: "", flow: "", primary: "", warn: "", danger: "", band: {} as Record<string, string> };
    const readColors = () => {
      colors.ink = cssVar("--text");
      colors.muted = cssVar("--text-muted");
      colors.line = cssVar("--border");
      colors.flow = cssVar("--info");
      colors.primary = cssVar("--primary");
      colors.warn = cssVar("--warn");
      colors.danger = cssVar("--danger");
      colors.band = Object.fromEntries(Object.entries(BAND_VAR).map(([k, v]) => [k, cssVar(v)]));
    };
    readColors();
    const sigma = new Sigma(graph, container.current, {
      settings: {
        labelRenderedSizeThreshold: 100, // only forced labels: ports, the leaders, the selection
        enableEdgeEvents: false,
        stagePadding: 24,
        allowInvalidContainer: true, // the view toggle can unmount it mid-resize
        zoomToSizeRatioFunction: (ratio) => Math.sqrt(ratio),
      },
      nodeReducer: (node, data, attrs) => {
        const { selected: sel, highlight: hl, labelled: lab } = state.current;
        const port = attrs.kind === "port";
        let color = port ? colors.primary : attrs.type === "customer_site" ? colors.muted : (colors.band[attrs.band as string] ?? colors.muted);
        let opacity = 1;
        let label: "visible" | "auto" | "hidden" = port || lab.has(node) ? "visible" : "hidden";
        if (hl) {
          if (hl.disrupted.has(node)) {
            color = colors.danger;
            label = "visible";
          } else if (hl.impacted.has(node)) color = colors.warn;
          else opacity = 0.25;
        }
        if (sel === node) label = "visible";
        return {
          ...data,
          color,
          opacity,
          labelColor: colors.ink,
          labelVisibility: label,
          zIndex: sel === node || hl?.disrupted.has(node) ? 2 : port ? 1 : 0,
          size: sel === node ? data.size * 1.35 : data.size,
        };
      },
      edgeReducer: (edge, data, attrs) => {
        const { selected: sel, highlight: hl } = state.current;
        const [s, t] = graph.extremities(edge);
        const touches = sel !== null && (s === sel || t === sel);
        // The ripple: links from a disrupted node to plants whose orders it delays.
        const affected = hl !== null && hl.disrupted.has(s) && hl.impacted.has(t);
        return {
          ...data,
          color: affected ? colors.danger : touches ? colors.primary : attrs.kind === "supply" ? colors.line : colors.flow,
          opacity: touches || affected ? 0.9 : sel || hl ? 0.1 : attrs.kind === "supply" ? 0.45 : attrs.kind === "import" ? 0.4 : 0.12,
          size: touches ? data.size + 0.8 : data.size,
          zIndex: touches || affected ? 1 : 0,
        };
      },
    });
    sigma.on("clickNode", ({ node }) => state.current.onSelect(node));
    sigma.on("clickStage", () => state.current.onSelect(null));
    sigmaRef.current = sigma;
    const off = onThemeChange(() => {
      readColors();
      sigma.refresh();
    });
    container.current.dataset.ready = "true";
    return () => {
      off();
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [nodes, edges]);

  return <div ref={container} className="h-full w-full" data-testid="supply-graph" />;
}
