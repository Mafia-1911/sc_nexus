import { Waves } from "lucide-react";
import { Suspense } from "react";

import { api } from "@/lib/api/server";
import { brandName } from "@/lib/brand";
import { SCENARIOS, currentScenario } from "@/lib/scenario";

import { NavRail } from "./nav-rail";
import { ScenarioSwitcher } from "./scenario-switcher";
import { ThemeToggle } from "./theme-toggle";

async function Brand() {
  const name = await brandName();
  return <span className="text-base font-semibold tracking-tight">{name}</span>;
}

async function Switcher() {
  return <ScenarioSwitcher current={await currentScenario()} options={SCENARIOS} />;
}

/** The real-name pack's banner (Q-05, ADR-014): shown whenever real company names are on. */
async function NamePackBanner() {
  const { data } = await (await api()).GET("/api/v1/meta");
  if (!data?.has_real_names || !data.banner) return null;
  return (
    <div role="note" className="border-b border-warn/40 bg-warn/10 px-4 py-2 text-xs text-warn">
      {data.banner}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      {/* The rail's surface spans the whole page; its contents stick to the viewport. */}
      <aside className="w-16 shrink-0 border-r border-border bg-surface lg:w-56">
        <div className="sticky top-0 flex h-screen flex-col gap-6 px-2 py-4 lg:px-3">
          <div className="flex items-center gap-2 px-2 text-primary">
            <Waves aria-hidden className="size-6 shrink-0" />
            <span className="hidden lg:inline">
              <Suspense fallback={<span className="skeleton inline-block h-4 w-24" />}>
                <Brand />
              </Suspense>
            </span>
          </div>
          <NavRail />
          <p className="mt-auto hidden px-2 text-[11px] leading-snug text-muted lg:block">
            Cportal prototype · synthetic firms are fictional · data modes on every card
          </p>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Suspense fallback={null}>
          <NamePackBanner />
        </Suspense>
        <header className="sticky top-0 z-10 flex h-14 items-center justify-end gap-3 border-b border-border bg-bg/90 px-4 backdrop-blur">
          <Suspense fallback={<span className="skeleton h-9 w-56" />}>
            <Switcher />
          </Suspense>
          <ThemeToggle />
        </header>
        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}
