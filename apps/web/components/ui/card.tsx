import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("rounded-[var(--radius-card)] border border-border bg-surface p-4", className)}
      {...props}
    />
  );
}

/** Card anatomy (05 §3): title, a one-line "so what" subtitle, content, footer. */
export function CardHeader({
  title,
  subtitle,
  aside,
}: {
  title: string;
  subtitle?: string;
  aside?: React.ReactNode;
}) {
  return (
    <header className="mb-3 flex items-start justify-between gap-3">
      <div>
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-muted">{subtitle}</p> : null}
      </div>
      {aside}
    </header>
  );
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <footer
      className={cn(
        "mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted",
        className,
      )}
      {...props}
    />
  );
}
