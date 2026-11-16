import { AuthForm } from "@/components/auth-form";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Log in");

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-12">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
        <p className="text-sm text-muted">Log in to open the control tower.</p>
      </div>
      <div className="rounded-[var(--radius-card)] border border-border bg-surface/90 p-5 shadow-sm backdrop-blur">
        <AuthForm mode="login" next={next} />
      </div>
    </div>
  );
}
