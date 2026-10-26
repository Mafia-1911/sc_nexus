import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badge = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
  {
    variants: {
      tone: {
        neutral: "border-border bg-surface-2 text-muted",
        ok: "border-ok/40 bg-ok/10 text-ok",
        info: "border-info/40 bg-info/10 text-info",
        warn: "border-warn/40 bg-warn/10 text-warn",
        danger: "border-danger/40 bg-danger/10 text-danger",
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
