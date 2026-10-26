import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Noto_Sans_Bengali } from "next/font/google";

import { AppShell } from "@/components/shell/app-shell";
import { brandName } from "@/lib/brand";

import "./globals.css";

// Self-hosted at build time: no font requests at runtime (venue Wi-Fi, 05 §10).
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const bengali = Noto_Sans_Bengali({ subsets: ["bengali"], variable: "--font-bengali", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export async function generateMetadata(): Promise<Metadata> {
  const brand = await brandName();
  return {
    // Pages compose "<Page> · <Brand>" themselves (lib/brand.ts `titled`): no template here.
    title: brand,
    description: "Supply-chain resilience for the Chattogram–Dhaka corridor (Cportal prototype).",
  };
}

// Apply a forced theme before first paint (no flash); the OS setting applies otherwise.
const THEME_INIT = `try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t}}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${bengali.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
