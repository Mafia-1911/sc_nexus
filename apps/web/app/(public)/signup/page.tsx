import { AuthForm } from "@/components/auth-form";
import { titled } from "@/lib/brand";

export const generateMetadata = () => titled("Sign up");

export default async function SignupPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const { next } = await searchParams;
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-4 px-4 py-12">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
        <p className="text-sm text-muted">Free for this prototype. We store your name, email and a hashed password, nothing else.</p>
      </div>
      <div className="rounded-[var(--radius-card)] border border-border bg-surface/90 p-5 shadow-sm backdrop-blur">
        <AuthForm mode="signup" next={next} />
      </div>
    </div>
  );
}
