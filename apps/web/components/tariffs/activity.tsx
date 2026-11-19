"use client";

import { ArrowDownRight, ArrowUpRight, ExternalLink, Gavel, Minus, Newspaper, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { DIRECTION, MARKET_NAME, NOTICE_KIND, type TariffChange, type TariffNews, type TradeNotice, pct } from "@/lib/c6";
import { cn, dhakaTime } from "@/lib/utils";

const DIR_ICON = { raise: ArrowUpRight, cut: ArrowDownRight, exempt: ShieldCheck, unknown: Minus } as const;

function NewsItem({ n, names }: { n: TariffNews; names: Record<string, string> }) {
  const look = DIRECTION[n.direction] ?? DIRECTION.unknown;
  const Icon = DIR_ICON[n.direction as keyof typeof DIR_ICON] ?? Minus;
  const where = [n.markets.map((m) => MARKET_NAME[m] ?? m).join(", "), n.origins.length ? `on goods from ${n.origins.map((o) => names[o] ?? o).join(", ")}` : ""]
    .filter(Boolean)
    .join(" ");
  const rate =
    n.rate_pct !== null && n.rate_pct !== undefined
      ? n.previous_pct !== null && n.previous_pct !== undefined
        ? `${pct(n.previous_pct)} → ${pct(n.rate_pct)}`
        : pct(n.rate_pct)
      : null;
  return (
    <li className="flex flex-col gap-1 py-2" data-testid="news-item" data-direction={n.direction}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={look.tone}>
          <Icon className="size-3" aria-hidden />
          {look.label}
          {n.status === "threatened" ? " (threatened)" : ""}
        </Badge>
        <Badge tone={n.confirmed ? "ok" : "info"} title={n.confirmation ? `${n.confirmation.market} ${n.confirmation.measure_ref}: ${n.confirmation.old_duty_text} → ${n.confirmation.new_duty_text}` : undefined}>
          {n.confirmed ? "In the schedule" : "Announced, not in the schedule yet"}
        </Badge>
      </div>
      {n.url ? (
        <a href={n.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 text-sm font-medium hover:underline">
          {n.title}
          <ExternalLink className="mt-1 size-3 shrink-0" aria-hidden />
        </a>
      ) : (
        <span className="text-sm font-medium">{n.title}</span>
      )}
      <span className="text-xs text-muted">
        {dhakaTime(n.published)} · {n.reports} report{n.reports === 1 ? "" : "s"}
        {n.outlets.length ? ` (${n.outlets.slice(0, 3).join(", ")})` : ""}
        {where ? ` · ${where}` : ""}
        {rate ? ` · ${rate}` : ""}
        {n.industries.length ? ` · ${n.industries.join(", ")}` : ""}
        {n.effective ? ` · effective ${n.effective}` : ""}
      </span>
      {n.quote ? <span className="text-xs italic text-muted">Read from: “{n.quote}”</span> : null}
    </li>
  );
}

function ChangeItem({ c }: { c: TariffChange }) {
  const up = (c.delta_pp ?? 0) > 0;
  const down = (c.delta_pp ?? 0) < 0;
  return (
    <li className="flex flex-col gap-1 py-2" data-testid="change-item">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={up ? "warn" : down ? "ok" : "neutral"}>
          {up ? <ArrowUpRight className="size-3" aria-hidden /> : down ? <ArrowDownRight className="size-3" aria-hidden /> : <Minus className="size-3" aria-hidden />}
          {c.change}
          {c.delta_pp ? ` ${up ? "+" : ""}${c.delta_pp} pp` : ""}
        </Badge>
        <span className="text-sm font-medium">
          {MARKET_NAME[c.market] ?? c.market} · {c.measure_ref} · {c.origin_code === "*" ? "all origins" : c.origin_code}
        </span>
      </div>
      <span className="text-xs">
        {c.old_duty_text ?? "—"} → {c.new_duty_text ?? "—"}
        {c.old_status !== c.new_status && c.new_status ? ` (${c.old_status ?? "new"} → ${c.new_status})` : ""}
      </span>
      <span className="text-xs text-muted">
        detected {dhakaTime(c.detected_at)}
        {c.effective_from ? ` · effective ${c.effective_from}` : ""} · {c.source_id}
      </span>
    </li>
  );
}

function NoticeItem({ n }: { n: TradeNotice }) {
  return (
    <li className="flex flex-col gap-1 py-2" data-testid="notice-item">
      <a href={n.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 text-sm font-medium hover:underline">
        {n.title}
        <ExternalLink className="mt-1 size-3 shrink-0" aria-hidden />
      </a>
      <span className="text-xs text-muted">
        {n.publication_date} · {NOTICE_KIND[n.kind] ?? n.kind}
        {n.countries.length ? ` · ${n.countries.join(", ")}` : ""}
        {n.hts_refs.length ? ` · HTS ${n.hts_refs.slice(0, 3).join(", ")}` : ""}
      </span>
    </li>
  );
}

type Tab = "news" | "changes" | "notices";

/** The right-hand card: tariff news, detected schedule changes and official notices. */
export function Activity({
  news,
  changes,
  notices,
  names,
}: {
  news: TariffNews[];
  changes: TariffChange[];
  notices: TradeNotice[];
  names: Record<string, string>;
}) {
  const [tab, setTab] = useState<Tab>(news.length ? "news" : changes.length ? "changes" : "notices");
  const tabs: { key: Tab; label: string; n: number; Icon: typeof Newspaper }[] = [
    { key: "news", label: "News", n: news.length, Icon: Newspaper },
    { key: "changes", label: "Schedule changes", n: changes.length, Icon: ArrowUpRight },
    { key: "notices", label: "Official notices", n: notices.length, Icon: Gavel },
  ];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2" id="news">
      <div role="tablist" aria-label="Tariff activity" className="flex flex-wrap gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs",
              tab === t.key ? "border-primary bg-primary text-on-primary" : "border-border text-muted hover:text-text",
            )}
          >
            <t.Icon className="size-3" aria-hidden />
            {t.label} <span className="tabular">({t.n})</span>
          </button>
        ))}
      </div>
      <div role="tabpanel" className="min-h-0 flex-1 overflow-y-auto">
        {tab === "news" ? (
          news.length ? (
            <ol className="divide-y divide-border" data-testid="news-list">{news.map((n) => <NewsItem key={n.id} n={n} names={names} />)}</ol>
          ) : (
            <p className="py-2 text-sm text-muted">No tariff news in the last 60 days from the news feeds (RSS, GDELT).</p>
          )
        ) : null}
        {tab === "changes" ? (
          changes.length ? (
            <ol className="divide-y divide-border" data-testid="change-list">{changes.map((c) => <ChangeItem key={c.id} c={c} />)}</ol>
          ) : (
            <p className="py-2 text-sm text-muted">No change detected yet: changes appear from the second daily fetch of a schedule.</p>
          )
        ) : null}
        {tab === "notices" ? (
          notices.length ? (
            <ol className="divide-y divide-border" data-testid="notice-list">{notices.map((n) => <NoticeItem key={n.document_number} n={n} />)}</ol>
          ) : (
            <p className="py-2 text-sm text-muted">No official notices fetched yet.</p>
          )
        ) : null}
      </div>
    </div>
  );
}
