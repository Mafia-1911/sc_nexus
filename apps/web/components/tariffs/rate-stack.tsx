import { pct } from "@/lib/c6";

/** Base rate vs what this origin pays (duty + surcharges): hand-written SVG, theme variables. */
export function RateStack({
  base,
  duty,
  surcharge,
  resolved,
}: {
  base: number | null | undefined;
  duty: number | null | undefined; // base or the preference that replaces it
  surcharge: number | null | undefined;
  resolved: boolean;
}) {
  const b = base ?? 0;
  const d = duty ?? b;
  const s = surcharge ?? 0;
  const max = Math.max(b, d + s, 1);
  const W = 320;
  const x = (v: number) => (v / max) * (W - 2);
  const rows = [
    { y: 4, label: "Base rate (MFN)", parts: [{ w: x(b), fill: "var(--border-strong)" }], total: b },
    {
      y: 34,
      label: resolved ? "This origin pays" : "This origin pays (at least)",
      parts: [
        { w: x(d), fill: "var(--series-1)" },
        { w: x(s), fill: "var(--series-2)" },
      ],
      total: d + s,
    },
  ];
  return (
    <figure className="flex flex-col gap-1" data-testid="rate-stack">
      <svg viewBox={`0 0 ${W + 80} 58`} className="w-full max-w-[26rem]" role="img" aria-label={`Base ${pct(b)}; this origin pays ${pct(d)} duty plus ${pct(s)} surcharge`}>
        {rows.map((r) => {
          let at = 1;
          return (
            <g key={r.label}>
              {r.parts.map((p, i) => {
                const rect = p.w > 0 ? <rect key={i} x={at} y={r.y + 12} width={Math.max(p.w - (i ? 2 : 0), 0)} height={10} rx={2} fill={p.fill} /> : null;
                at += p.w;
                return rect;
              })}
              <text x={1} y={r.y + 8} className="fill-[var(--text-muted)] text-[9px]">{r.label}</text>
              <text x={Math.max(at, 1) + 6} y={r.y + 21} className="tabular fill-[var(--text)] text-[10px] font-semibold">{pct(r.total)}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-3 text-xs text-muted">
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-border-strong" aria-hidden />Base rate</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-series-1" aria-hidden />Duty after preferences</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-series-2" aria-hidden />Country surcharge</span>
      </figcaption>
    </figure>
  );
}
