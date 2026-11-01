"use client";

import { CloudLightning, Factory, Flame, Gavel, Pill, Ship, TriangleAlert, Truck, Users, Zap } from "lucide-react";
import Link from "next/link";
import { useCallback, useState, useTransition } from "react";

import { loadEvent } from "@/app/radar/actions";
import { DataBadge } from "@/components/data-badge";
import { EventDrawer } from "@/components/radar/event-drawer";
import { EventMap } from "@/components/radar/event-map";
import { Card, CardHeader } from "@/components/ui/card";
import type { Meta } from "@/lib/c1";
import { type EventDetail, type EventItem, hours, typeName } from "@/lib/c2";
import { cn, dhakaTime, fmt } from "@/lib/utils";

const ICON: Record<string, typeof Ship> = {
  CYCLONE_STORM: CloudLightning,
  FLOOD: CloudLightning,
  PORT_OPERATIONS_SUSPENDED: Ship,
  PORT_CONGESTION: Ship,
  CHOKEPOINT_DISRUPTION: Ship,
  LABOR_STRIKE_BLOCKADE: Users,
  FIRE_EXPLOSION: Flame,
  ENERGY_UTILITY_SHORTAGE: Zap,
  INLAND_TRANSPORT_DISRUPTION: Truck,
  TRADE_POLICY_SANCTION: Gavel,
  PHARMA_REGULATORY_QUALITY: Pill,
  SUPPLIER_INCIDENT: Factory,
};

const SOURCES = [
  { key: "news", label: "From news (C2)" },
  { key: "all", label: "All" },
  { key: "feeds", label: "Feeds" },
] as const;

export function RadarWorkbench({
  events,
  meta,
  scenario,
  source,
}: {
  events: EventItem[];
  meta: Meta;
  scenario: string;
  source: "news" | "feeds" | "all";
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [, start] = useTransition();
  const select = useCallback(
    (id: string | null) => {
      setSelected(id);
      if (!id) return setDetail(null);
      start(async () => setDetail((await loadEvent(scenario, id)).data ?? null));
    },
    [scenario],
  );
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Event source" className="flex gap-1">
          {SOURCES.map((s) => (
            <Link
              key={s.key}
              href={`?source=${s.key}`}
              scroll={false}
              aria-current={s.key === source ? "page" : undefined}
              className={cn(
                "rounded-full border px-3 py-1 text-xs",
                s.key === source ? "border-primary bg-primary text-on-primary" : "border-border text-muted hover:text-text",
              )}
            >
              {s.label}
            </Link>
          ))}
        </nav>
        <span className="ml-auto">
          <DataBadge mode={meta.mode} sources={meta.sources} asOf={meta.as_of} modes={meta.modes} />
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="flex flex-col xl:col-span-2 xl:h-[560px]">
          <CardHeader title="What happened" subtitle={`${events.length} events, newest first; one event per story, however many reports`} />
          <ol className="flex min-h-0 flex-1 flex-col divide-y divide-border overflow-y-auto" data-testid="event-feed">
            {events.map((e) => {
              const Icon = ICON[e.type] ?? TriangleAlert;
              return (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() => select(e.id)}
                    aria-pressed={e.id === selected}
                    className={cn("flex w-full gap-2 px-1 py-2 text-left hover:bg-surface-2", e.id === selected && "bg-surface-2")}
                  >
                    <Icon className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium" title={e.title}>{e.title}</span>
                      <span className="block text-xs text-muted">
                        {typeName(e.type)} · {e.status} · {dhakaTime(e.start_est)}
                        {e.mentions ? ` · ${e.mentions} report(s)` : ` · ${e.source_id}`} · {hours(e.duration_p50_h)}
                      </span>
                      <span className="mt-1 flex items-center gap-2 text-[11px] text-muted">
                        <span className="h-1.5 w-16 rounded-full bg-surface-2" aria-hidden>
                          <span className="block h-1.5 rounded-full bg-warn" style={{ width: `${(e.severity ?? 0) * 100}%` }} />
                        </span>
                        severity {fmt((e.severity ?? 0) * 100)} · confidence {fmt((e.confidence ?? 0) * 100)}%
                        {e.confidence_fused != null && e.confidence_fused !== e.confidence ? (
                          <span data-testid="fused" className="text-ok">
                            → {fmt(e.confidence_fused * 100)}% corroborated
                          </span>
                        ) : null}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </Card>
        <Card className="xl:col-span-3">
          <CardHeader title="Where" subtitle="News events (amber) and hazard or regulatory feeds (blue), sized by severity" />
          <div className="relative h-[480px] overflow-hidden rounded-[var(--radius-control)] border border-border">
            <EventMap events={events} selected={selected} onSelect={select} />
          </div>
        </Card>
      </div>
      {detail && detail.event.id === selected ? (
        <EventDrawer detail={detail} scenario={scenario} onClose={() => select(null)} />
      ) : null}
    </div>
  );
}
