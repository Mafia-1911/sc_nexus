"use client";

import Link from "next/link";
import { useCallback, useState, useTransition } from "react";

import { loadProduct } from "@/app/(app)/tariffs/actions";
import { DataBadge, Provenance } from "@/components/data-badge";
import { Activity } from "@/components/tariffs/activity";
import { DetailCard } from "@/components/tariffs/detail-card";
import { Legend, Matrix, type Selection } from "@/components/tariffs/matrix";
import { Badge } from "@/components/ui/badge";
import { Card, CardFooter, CardHeader } from "@/components/ui/card";
import type { Meta } from "@/lib/c1";
import {
  FEED_LOOK,
  type ProductDetail,
  type TariffChange,
  type TariffMatrix,
  type TariffNews,
  type TariffOverview,
  type TradeNotice,
  countryName,
} from "@/lib/c6";
import { cn, dhakaTime, fmt } from "@/lib/utils";

type Params = { industry: string; view: string; origin: string; market: string };

function href(p: Params, change: Partial<Params>): string {
  const q = new URLSearchParams({ ...p, ...change });
  return `?${q.toString()}`;
}

function Chips({ label, items, current, make }: { label: string; items: { key: string; label: string }[]; current: string; make: (key: string) => string }) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-1">
      {items.map((s) => (
        <Link
          key={s.key}
          href={make(s.key)}
          scroll={false}
          aria-current={s.key === current ? "page" : undefined}
          className={cn(
            "rounded-full border px-3 py-1 text-xs",
            s.key === current ? "border-primary bg-primary text-on-primary" : "border-border text-muted hover:text-text",
          )}
        >
          {s.label}
        </Link>
      ))}
    </nav>
  );
}

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-[var(--radius-card)] border border-border bg-surface/85 p-4 shadow-sm backdrop-blur-md">
      <span className="text-xs text-muted">{label}</span>
      <span className="tabular text-2xl font-semibold">{value}</span>
      {detail ? <span className="text-xs text-muted">{detail}</span> : null}
    </div>
  );
}

export function TariffWorkbench({
  overview,
  overviewMeta,
  matrix,
  matrixMeta,
  changes,
  notices,
  news,
  industry,
  view,
  origin,
  market,
  initialDetail,
}: {
  overview: TariffOverview;
  overviewMeta: Meta;
  matrix: TariffMatrix;
  matrixMeta: Meta;
  changes: TariffChange[];
  notices: TradeNotice[];
  news: TariffNews[];
  industry: "garments" | "pharma";
  view: "markets" | "origins";
  origin: string;
  market: string;
  initialDetail: ProductDetail | null;
}) {
  const params: Params = { industry, view, origin, market };
  // A link from another page (/tariffs?hs6=…&market=…&origin=…) arrives with its detail loaded.
  const [selected, setSelected] = useState<Selection | null>(
    initialDetail ? { hs6: initialDetail.product.hs6, market, origin } : null,
  );
  const [detail, setDetail] = useState<ProductDetail | null>(initialDetail);
  const [pending, start] = useTransition();
  const select = useCallback((s: Selection | null) => {
    setSelected(s);
    if (!s) return setDetail(null);
    start(async () => setDetail((await loadProduct(s.hs6, s.market)).data ?? null));
  }, []);
  const live = overview.markets.filter((m) => m.live_source).length;
  const missing = overview.feeds.filter((f) => f.status === "missing").length;
  const fixedName = view === "markets" ? countryName(overview.origins, origin) : overview.markets.find((m) => m.code === market)?.name;
  const unresolved = matrix.cells.filter((c) => !c.is_resolved && c.n_lines > 0).length;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chips label="Industry" current={industry} items={[{ key: "garments", label: "Garments" }, { key: "pharma", label: "Pharma" }]} make={(k) => href(params, { industry: k })} />
        <Chips label="Compare" current={view} items={[{ key: "markets", label: "Compare markets" }, { key: "origins", label: "Compare origins" }]} make={(k) => href(params, { view: k })} />
        <span className="ml-auto">
          <DataBadge mode={matrixMeta.mode} sources={matrixMeta.sources} asOf={matrixMeta.as_of} modes={matrixMeta.modes} />
        </span>
      </div>
      {view === "markets" ? (
        <Chips label="Goods from" current={origin} items={overview.origins.map((o) => ({ key: o.iso3, label: o.name }))} make={(k) => href(params, { origin: k })} />
      ) : (
        <Chips label="Sold into" current={market} items={overview.markets.map((m) => ({ key: m.code, label: m.name }))} make={(k) => href(params, { market: k })} />
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="tariff-kpis">
        <Tile label="Schedule changes, 30 days" value={fmt(overview.changes_30d)} detail={overview.latest_change_at ? `latest ${dhakaTime(overview.latest_change_at)}` : "none detected yet"} />
        <Tile label="Tariff news, 30 days" value={fmt(overview.news_30d)} detail="from RSS and GDELT, read by C2" />
        <Tile label="Official notices, 30 days" value={fmt(overview.notices_30d)} detail="US Federal Register" />
        <Tile label="Markets with a live schedule" value={`${live} of ${overview.markets.length}`} detail={`${missing} feeds still missing`} />
      </div>

      {/* five market columns need the width: side by side only on very wide screens */}
      <div className="grid grid-cols-1 gap-4 2xl:grid-cols-5">
        <Card className="2xl:col-span-3">
          <CardHeader
            title={view === "markets" ? `Duty on ${industry} from ${fixedName}, by market` : `Duty on ${industry} into ${fixedName}, by origin`}
            subtitle={`Effective rate per product: base, minus preferences, plus country surcharges · ${unresolved} cell(s) have no single number`}
          />
          <div className="mb-3">
            <Legend />
          </div>
          <Matrix matrix={matrix} overview={overview} view={view} origin={origin} market={market} selected={selected} onSelect={select} />
          <p className="mt-2 text-xs text-muted">Click a cell for how the rate is made up. {pending ? "Loading…" : ""}</p>
          <CardFooter>
            <Provenance meta={matrixMeta} />
          </CardFooter>
        </Card>
        <Card className="flex max-h-[640px] flex-col 2xl:col-span-2 2xl:max-h-none">
          <CardHeader title="What changed" subtitle="News first, then the schedule changes and notices that confirm or explain it" />
          <Activity news={news} changes={changes} notices={notices} names={Object.fromEntries(overview.origins.map((o) => [o.iso3, o.name]))} />
        </Card>
      </div>

      {detail && selected && detail.product.hs6 === selected.hs6 ? (
        <DetailCard detail={detail} origin={selected.origin} overview={overview} onOrigin={(o) => setSelected({ ...selected, origin: o })} onClose={() => select(null)} />
      ) : null}

      <details className="rounded-[var(--radius-card)] border border-border bg-surface p-3 text-sm" data-testid="feed-status">
        <summary className="cursor-pointer font-medium">Data feeds: what is live, hand-kept and missing</summary>
        <ul className="mt-2 flex flex-col gap-2 text-xs">
          {overview.feeds.map((f) => {
            const look = FEED_LOOK[f.status] ?? FEED_LOOK.missing;
            return (
              <li key={f.id} className="flex flex-wrap items-start gap-2">
                <Badge tone={look.tone}>{look.label}</Badge>
                <span className="font-semibold">{f.id}</span>
                <span>{f.what}</span>
                {f.cadence ? <span className="text-muted">· {f.cadence}</span> : null}
                {f.note ? <span className="text-muted">· {f.note}</span> : null}
                {f.todo ? <span className="w-full text-muted">To do: {f.todo}</span> : null}
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-xs text-muted">
          <Provenance meta={overviewMeta} />
        </p>
      </details>
    </div>
  );
}
