import { CircleSlash, FlaskConical, History, Layers, Radio } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { dhakaTime } from "@/lib/utils";

type Mode = "live" | "replay" | "synthetic" | "mixed" | "none" | string;

const LOOK: Record<string, { label: string; tone: "ok" | "info" | "warn" | "neutral"; Icon: typeof Radio }> = {
  live: { label: "Live", tone: "ok", Icon: Radio },
  replay: { label: "Replay", tone: "info", Icon: History },
  synthetic: { label: "Synthetic", tone: "warn", Icon: FlaskConical },
  mixed: { label: "Mixed", tone: "neutral", Icon: Layers },
  none: { label: "No data", tone: "neutral", Icon: CircleSlash },
};

/** The LIVE / REPLAY / SYNTHETIC badge (AGENTS.md rule 3): icon + label, never colour alone. */
export function DataBadge({
  mode,
  sources,
  asOf,
  modes,
}: {
  mode: Mode;
  sources?: string[];
  asOf?: string | null;
  modes?: Record<string, number>;
}) {
  const look = LOOK[mode] ?? LOOK.none;
  const breakdown = modes && Object.keys(modes).length > 1
    ? Object.entries(modes).map(([m, n]) => `${m} ${n}`).join(" · ")
    : null;
  const title = [
    sources?.length ? `Sources: ${sources.join(", ")}` : null,
    breakdown,
    asOf ? `As of ${dhakaTime(asOf)}` : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <Badge tone={look.tone} title={title || undefined} data-mode={mode}>
      <look.Icon aria-hidden className="size-3" />
      {look.label}
    </Badge>
  );
}

/** Footer line: badge, sources and "as of" (05 §3 card anatomy). */
export function Provenance({
  meta,
}: {
  meta: { mode: string; sources?: string[]; as_of?: string | null; modes?: Record<string, number>; note?: string | null };
}) {
  return (
    <>
      <DataBadge mode={meta.mode} sources={meta.sources} asOf={meta.as_of} modes={meta.modes} />
      {meta.sources?.length ? <span>{meta.sources.join(", ")}</span> : null}
      {meta.as_of ? <span className="tabular">as of {dhakaTime(meta.as_of)}</span> : null}
      {meta.note ? <span className="italic">{meta.note}</span> : null}
    </>
  );
}
