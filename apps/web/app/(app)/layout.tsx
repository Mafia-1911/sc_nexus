import { AppShell } from "@/components/shell/app-shell";

/** The dashboard: navigation rail, data selector and theme toggle around every app page. */
export default function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AppShell>{children}</AppShell>;
}
