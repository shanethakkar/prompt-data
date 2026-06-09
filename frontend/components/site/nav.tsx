"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Ask" },
  { href: "/gallery", label: "Gallery" },
  { href: "/evals", label: "Evals" },
  { href: "/methodology", label: "Methodology" },
  { href: "/limitations", label: "Limitations" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="-mr-1 flex items-center gap-1 overflow-x-auto">
      {LINKS.map((l) => {
        const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={cn(
              "rounded-md px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
              active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
