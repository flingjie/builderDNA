// frontend/src/components/explorer/ExplorerGrid.tsx
"use client";
import type { DiscoveredTheme } from "@/lib/types";
import { ThemeCard } from "./ThemeCard";

export function ExplorerGrid({ themes }: { themes: DiscoveredTheme[] }) {
  if (themes.length === 0) {
    return (
      <div className="text-zinc-500 p-12 text-center border border-zinc-800 rounded-lg">
        <p className="text-lg mb-2">No new themes discovered yet</p>
        <p className="text-sm">Run discovery with refresh=true to scan for emerging directions.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {themes.map((theme) => (
        <ThemeCard key={theme.topic} theme={theme} />
      ))}
    </div>
  );
}
