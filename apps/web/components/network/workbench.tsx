"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useMemo, useState, useTransition } from "react";

import { loadNode } from "@/app/network/actions";
import { DataBadge } from "@/components/data-badge";
import { GeoMap } from "@/components/network/geo-map";
import type { Highlight } from "@/components/network/graph-canvas";
import { Leaderboard } from "@/components/network/leaderboard";
import { NodeDrawer } from "@/components/network/node-drawer";
import { Card, CardHeader } from "@/components/ui/card";
import { BAND_VAR, type Critical, type Meta, type Metric, type NodeDetail, type SupplyGraph, type WhatIf } from "@/lib/c1";
import { cn } from "@/lib/utils";

// Sigma touches WebGL at import time: client only.
const GraphCanvas = dynamic(() => import("@/components/network/graph-canvas").then((m) => m.GraphCanvas), {
  ssr: false,
  loading: () => <div className="skeleton h-full w-full" />,
});

const INDUSTRIES = [
  { key: null, label: "All" },
  { key: "garments", label: "Garments" },
  { key: "pharma", label: "Pharma" },
] as const;

function Legend() {
  const items = [
    { label: "High risk", color: `var(${BAND_VAR.high})` },
    { label: "Medium", color: `var(${BAND_VAR.medium})` },
    { label: "Low", color: `var(${BAND_VAR.low})` },
    { label: "Port", color: "var(--primary)" },
    { label: "Buyer DC", color: "var(--text-muted)" },
  ];
  return (
    <ul className="flex flex-wrap items-center gap-3 text-xs text-muted" aria-label="Legend">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-full" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
      <li>size = open-order value that depends on it</li>
    </ul>
  );
}

export function NetworkWorkbench({
  graph,
  meta,
  critical,
  scenario,
  industry,
  metric,
}: {
  graph: SupplyGraph;
  meta: Meta;
  critical: Critical;
  scenario: string;
  industry: string | null;
  metric: Metric;
}) {
  const [view, setView] = useState<"network" | "map">("network");
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [whatIf, setWhatIf] = useState<WhatIf | null>(null);
  const [, start] = useTransition();

  const select = useCallback(
    (id: string | null) => {
      setSelected(id);
      setWhatIf(null);
      if (!id) {
        setDetail(null);
        return;
      }
      start(async () => {
        const out = await loadNode(scenario, id);
        setDetail(out.data ?? null);
        setError(out.error ?? null);
      });
    },
    [scenario],
  );

  const highlight: Highlight | null = useMemo(() => {
    if (!whatIf) return null;
    return {
      disrupted: new Set(whatIf.disrupted.map((d) => d.node_id)),
      impacted: new Set(whatIf.impacted_orders.map((o) => o.facility)),
    };
  }, [whatIf]);
  const labelled = useMemo(() => new Set(critical.items.slice(0, 4).map((m) => m.node_id)), [critical]);
  const href = (key: string | null) => `?${new URLSearchParams({ ...(key ? { industry: key } : {}), metric })}`;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <nav aria-label="Industry" className="flex gap-1">
          {INDUSTRIES.map((i) => (
            <Link
              key={i.label}
              href={href(i.key)}
              scroll={false}
              aria-current={i.key === industry ? "page" : undefined}
              className={cn(
                "rounded-full border px-3 py-1 text-xs",
                i.key === industry ? "border-primary bg-primary text-on-primary" : "border-border text-muted hover:text-text",
              )}
            >
              {i.label}
            </Link>
          ))}
        </nav>
        <div role="group" aria-label="View" className="flex rounded-full border border-border p-0.5">
          {(["network", "map"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cn("rounded-full px-3 py-0.5 text-xs capitalize", view === v ? "bg-surface-2 font-medium" : "text-muted")}
              data-testid={`view-${v}`}
            >
              {v}
            </button>
          ))}
        </div>
        <span className="ml-auto">
          <DataBadge mode={meta.mode} sources={meta.sources} asOf={meta.as_of} modes={meta.modes} />
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title={view === "network" ? "Supply network" : "Where it sits"}
            subtitle={`${graph.nodes.length} nodes, ${graph.edges.length} links; sea imports and every export run through Chattogram. Click a node.`}
          />
          <div className="relative h-[540px] overflow-hidden rounded-[var(--radius-control)] border border-border bg-[var(--chart-surface)]">
            {view === "network" ? (
              <GraphCanvas nodes={graph.nodes} edges={graph.edges} selected={selected} highlight={highlight} labelled={labelled} onSelect={select} />
            ) : (
              <GeoMap nodes={graph.nodes} edges={graph.edges} selected={selected} highlight={highlight} onSelect={select} />
            )}
            {whatIf ? (
              <p className="absolute left-2 top-2 rounded-[var(--radius-control)] border border-border bg-surface/95 px-2 py-1 text-xs">
                What-if: <span className="text-danger">disrupted</span> and <span className="text-warn">plants with delayed orders</span>
              </p>
            ) : null}
          </div>
          <div className="mt-3">
            <Legend />
          </div>
        </Card>
        <Card className="flex flex-col xl:h-[688px]">
          <CardHeader title="Where are we fragile?" subtitle="Ranked by what breaks elsewhere if the node fails" />
          <Leaderboard
            items={critical.items}
            metric={metric}
            industry={industry}
            ttsBelowTtr={critical.tts_below_ttr}
            selected={selected}
            onSelect={select}
          />
        </Card>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : null}
      {detail && selected === detail.metrics.node_id ? (
        <NodeDrawer detail={detail} scenario={scenario} onClose={() => select(null)} onResult={setWhatIf} />
      ) : null}
    </div>
  );
}
