"use client";

import {
  Anchor,
  Database,
  FlaskConical,
  LayoutDashboard,
  Network,
  Radar,
  Route,
  ScanSearch,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export const PAGES = [
  { href: "/", label: "Control Tower", Icon: LayoutDashboard },
  { href: "/ports", label: "Ports & Vessels", Icon: Anchor },
  { href: "/network", label: "Supplier Network", Icon: Network },
  { href: "/radar", label: "Disruption Radar", Icon: Radar },
  { href: "/routes", label: "Route Planner", Icon: Route },
  { href: "/quality", label: "Quality Lab", Icon: ScanSearch },
  { href: "/scenarios", label: "Scenario Studio", Icon: FlaskConical },
  { href: "/data", label: "Data & Models", Icon: Database },
] as const;

/** Left rail with icons and labels (05 §3). */
export function NavRail() {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {PAGES.map(({ href, label, Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 text-sm",
              active ? "bg-primary text-on-primary" : "text-muted hover:bg-surface-2 hover:text-text",
            )}
          >
            <Icon aria-hidden className="size-4 shrink-0" />
            <span className="hidden lg:inline">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
