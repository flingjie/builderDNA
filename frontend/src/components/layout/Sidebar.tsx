"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Executive Radar" },
  { href: "/trends", label: "Trend Landscape" },
  { href: "/opportunities", label: "Opportunity Map" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 min-h-screen bg-zinc-950 border-r border-zinc-800 flex flex-col">
      <div className="p-4 border-b border-zinc-800">
        <h1 className="text-sm font-bold tracking-tight text-zinc-100">BuilderDNA</h1>
        <p className="text-xs text-zinc-600 mt-0.5">AI Infrastructure Radar</p>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "block rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-zinc-800 text-zinc-100 font-medium"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-zinc-800">
        <p className="text-xs text-zinc-600">BuilderDNA v1.0</p>
      </div>
    </aside>
  );
}
