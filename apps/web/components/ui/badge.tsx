import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badge = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
  {
    variants: {
      tone: {
        // Opaque fills (the tone mixed into the surface): a translucent fill let the ocean
        // backdrop show through and dropped the ink below 4.5:1 in toolbars (axe, 2026-11-18).
        neutral: "border-border bg-surface-2 text-muted",
        ok: "border-ok/40 bg-[color-mix(in_srgb,var(--ok)_10%,var(--surface))] text-ok",
        info: "border-info/40 bg-[color-mix(in_srgb,var(--info)_10%,var(--surface))] text-info",
        warn: "border-warn/40 bg-[color-mix(in_srgb,var(--warn)_10%,var(--surface))] text-warn",
        danger: "border-danger/40 bg-[color-mix(in_srgb,var(--danger)_10%,var(--surface))] text-danger",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}
