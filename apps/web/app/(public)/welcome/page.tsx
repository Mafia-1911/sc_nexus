import { Anchor, ArrowRight, Database, Gauge, Network, Newspaper, Route, ScanSearch, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api/server";
import { currentUser } from "@/lib/auth";
import { brandName, titled } from "@/lib/brand";

export const generateMetadata = () => titled("Supply-chain resilience for Bangladesh");

const LENSES = [
  { icon: Anchor, title: "Port dwell", text: "When each ship berths and leaves Chattogram, with P10–P90 bands, from three years of real berthings." },
  { icon: Newspaper, title: "Trade-news intelligence", text: "Strikes, cyclones and closures pulled from the news, located, dated and cross-checked against hazard feeds." },
  { icon: Network, title: "Supplier risk graph", text: "Which mills and ports many orders depend on, and what breaks when one goes down." },
  { icon: Route, title: "Routing", text: "Fastest, cheapest or lowest-CO2e way from port or depot to your warehouse, with the odds of arriving on time." },
  { icon: ScanSearch, title: "Defect intelligence", text: "Image models flag defective lots and trace which orders and shipments they put at risk." },
  { icon: Sparkles, title: "Nexus", text: "Ties it together: door-to-door ETAs, fused evidence and costed actions you can accept or dismiss." },
];

const SOURCES = ["Chittagong Port Authority (TOS + PCS)", "Global Fishing Watch", "GDACS", "GDELT", "IMF PortWatch", "OpenStreetMap", "Open-Meteo", "ReliefWeb", "Mapbox Traffic"];

type Kpi = { key: string; value: number | null; unit?: string | null };

/** The free API host sleeps when idle: never hold the landing page for it (6 s, then a note). */
function within<T>(p: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([p, new Promise<null>((done) => setTimeout(() => done(null), ms))]);
}

async function LiveStats() {
  const client = await api();
  const both = await within(
    Promise.all([
      client.GET("/api/v1/kpis", { params: { query: { scenario: "" } } }),
      client.GET("/api/v1/ports/{locode}/gates", { params: { path: { locode: "BDCGP" }, query: { days: 2, scenario: "" } } }),
    ]),
    6000,
  );
  if (!both) {
    return (
      <p className="rounded-[var(--radius-card)] border border-border bg-surface/80 p-6 text-sm text-muted backdrop-blur" data-testid="landing-stats">
        The live data service is waking up (it sleeps when nobody is looking). Refresh in a minute for today&apos;s numbers.
      </p>
    );
  }
  const [k, g] = both;
  const kpis = Object.fromEntries(((k.data?.data.kpis ?? []) as Kpi[]).map((x) => [x.key, x]));
  const gates = (g.data?.data ?? []) as { date: string; in: number; out: number }[];
  const day = gates[1] ?? gates[0];
  const fmt = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : v.toLocaleString("en-US", { maximumFractionDigits: d }));
  const stats = [
    { label: "ships waiting off Chattogram", value: fmt(kpis.vessels_at_anchorage?.value) },
    { label: "median wait for a berth", value: kpis.mean_wait_24h?.value != null ? `${fmt(kpis.mean_wait_24h.value, 1)} h` : "—" },
    { label: `containers through the gates${day ? ` on ${day.date.slice(5)}` : ""}`, value: day ? fmt(day.in + day.out) : "—" },
    { label: "active disruptions in Bangladesh", value: fmt(kpis.active_disruptions?.value) },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3" data-testid="landing-stats">
      {stats.map((s) => (
        <div key={s.label} className="rounded-[var(--radius-card)] border border-border bg-surface/80 p-4 backdrop-blur">
          <dd className="tabular text-3xl font-semibold tracking-tight text-primary">{s.value}</dd>
          <dt className="mt-1 text-xs text-muted">{s.label}</dt>
        </div>
      ))}
    </dl>
  );
}

export default async function WelcomePage() {
  const [brand, user] = await Promise.all([brandName(), currentUser()]);
  return (
    <div className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
      {/* Hero */}
      <section className="grid items-center gap-10 py-10 lg:grid-cols-[1.15fr_1fr] lg:py-16">
        <div className="flex flex-col gap-6">
          <span className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs text-muted backdrop-blur">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--success,#2f9e6b)]" />
            Live from Chattogram, polled every 15 minutes
          </span>
          <h1 className="text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            See port delays{" "}
            <span className="bg-gradient-to-r from-[var(--primary)] to-[var(--series-2)] bg-clip-text text-transparent">before they reach your orders.</span>
          </h1>
          <p className="max-w-xl text-base text-muted sm:text-lg">
            {brand} watches ships, berths, yards, gates, news and weather on the Chattogram–Dhaka corridor and turns them into
            decisions for garment and pharma shippers: when cargo will really arrive, what is at risk, and what to do about it.
          </p>
          <div className="flex flex-wrap gap-3">
            {user ? (
              <Link href="/" className="inline-flex items-center gap-2 rounded-[var(--radius-control)] bg-primary px-5 py-3 font-medium text-on-primary shadow-sm">
                Open the control tower <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <>
                <Link href="/signup" className="inline-flex items-center gap-2 rounded-[var(--radius-control)] bg-primary px-5 py-3 font-medium text-on-primary shadow-sm">
                  Create a free account <ArrowRight className="h-4 w-4" />
                </Link>
                <Link href="/login" className="inline-flex items-center rounded-[var(--radius-control)] border border-border bg-surface/70 px-5 py-3 font-medium backdrop-blur">
                  Log in
                </Link>
              </>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <Suspense fallback={<div className="skeleton h-56 w-full rounded-[var(--radius-card)]" />}>
            <LiveStats />
          </Suspense>
          <p className="text-xs text-muted">Real numbers from public sources right now; the app badges every figure LIVE, REPLAY or SYNTHETIC.</p>
        </div>
      </section>

      {/* Lenses */}
      <section className="py-10">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Five lenses, one decision</h2>
        <p className="mt-2 max-w-2xl text-muted">Each model is tested against a simple baseline on held-out time, and every recommendation shows its cost, benefit, confidence and evidence.</p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {LENSES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="group rounded-[var(--radius-card)] border border-border bg-surface/80 p-5 backdrop-blur transition hover:-translate-y-0.5 hover:shadow-md">
              <Icon className="h-6 w-6 text-primary" aria-hidden />
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="grid gap-4 py-10 md:grid-cols-3">
        {[
          { icon: Database, title: "Open data, probed first", text: "Port schedules, berth reports, satellite AIS visits, hazard alerts and news, each with its licence and freshness on record." },
          { icon: Gauge, title: "Models that earn their place", text: "Baselines first; a model replaces one only when it wins on a time-based holdout. Misses are reported, not hidden." },
          { icon: ShieldCheck, title: "Decisions with evidence", text: "Scenarios replay a cyclone or a strike with and without the recommended actions, so you see what each one is worth." },
        ].map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-[var(--radius-card)] border border-border bg-surface/60 p-5 backdrop-blur">
            <Icon className="h-5 w-5 text-[var(--series-2)]" aria-hidden />
            <h3 className="mt-2 font-semibold">{title}</h3>
            <p className="mt-1 text-sm text-muted">{text}</p>
          </div>
        ))}
      </section>

      {/* Sources */}
      <section className="py-8">
        <p className="text-xs uppercase tracking-wider text-muted">Built on public data</p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {SOURCES.map((s) => (
            <li key={s} className="rounded-full border border-border bg-surface/70 px-3 py-1 text-xs backdrop-blur">
              {s}
            </li>
          ))}
        </ul>
      </section>

      {/* Closing CTA */}
      <section className="mt-6 rounded-[var(--radius-card)] border border-border bg-gradient-to-br from-[var(--primary)] to-[var(--series-2)] p-8 text-on-primary shadow-sm sm:p-10">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Know where your containers are stuck.</h2>
        <p className="mt-2 max-w-xl opacity-90">Free for this prototype. Real data where it exists; fictional companies in the scenarios, clearly marked.</p>
        <Link href={user ? "/" : "/signup"} className="mt-5 inline-flex items-center gap-2 rounded-[var(--radius-control)] bg-surface px-5 py-3 font-medium text-text">
          {user ? "Open the control tower" : "Get started"} <ArrowRight className="h-4 w-4" />
        </Link>
      </section>
      <p className="mt-8 text-center text-xs text-muted">
        Research prototype. Global Fishing Watch and MVTec data are non-commercial (CC BY-NC); scenario companies are fictional.
      </p>
    </div>
  );
}
