import { Waves } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { OceanBackdrop } from "@/components/shell/ocean-backdrop";
import { brandName } from "@/lib/brand";

async function Brand() {
  return <>{await brandName()}</>;
}

/** Landing, sign-up and login: no dashboard chrome, the same ocean backdrop and tokens. Runtime
 *  reads (brand, cookies, query) stay inside Suspense (Cache Components). */
export default function PublicLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="relative min-h-screen bg-bg text-text">
      <OceanBackdrop />
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Link href="/welcome" className="flex items-center gap-2 font-semibold text-primary">
          <Waves className="h-5 w-5" aria-hidden />
          <Suspense fallback="Cportal">
            <Brand />
          </Suspense>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link href="/login" className="rounded-[var(--radius-control)] px-3 py-1.5 text-muted hover:text-text">
            Log in
          </Link>
          <Link href="/signup" className="rounded-[var(--radius-control)] bg-primary px-3 py-1.5 font-medium text-on-primary">
            Sign up
          </Link>
        </nav>
      </header>
      <main className="relative z-10">
        <Suspense fallback={<div className="skeleton mx-auto mt-10 h-96 max-w-6xl" />}>{children}</Suspense>
      </main>
    </div>
  );
}
