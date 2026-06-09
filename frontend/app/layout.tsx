import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { Nav } from "@/components/site/nav";
import "./globals.css";

// Variable names match the @theme mapping in globals.css (--font-sans, --font-geist-mono).
const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Prompt Data — Trust-Layer Analytics Copilot",
  description:
    "Ask the Olist e-commerce database in plain English. Prompt Data surfaces its assumptions, "
    + "asks when a question is ambiguous, and attaches a calibrated confidence signal.",
};

function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-5">
        <Link href="/" className="group flex shrink-0 items-center gap-2.5">
          <span
            className="size-2 rounded-full bg-primary shadow-[0_0_12px_2px_var(--color-primary)]"
            aria-hidden
          />
          <span className="font-mono text-sm font-medium tracking-[0.18em] text-foreground">
            PROMPT DATA
          </span>
        </Link>
        <Nav />
      </div>
    </header>
  );
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <TooltipProvider delayDuration={200}>
          <SiteHeader />
          <main className="flex-1">{children}</main>
          <Toaster position="bottom-center" />
        </TooltipProvider>
      </body>
    </html>
  );
}
