// frontend/src/app/explorer/page.tsx
"use client";
import { useState, useEffect } from "react";
import { fetchExplorer } from "@/lib/api";
import type { DiscoveredTheme } from "@/lib/types";
import { ExplorerGrid } from "@/components/explorer/ExplorerGrid";
import { Skeleton } from "@/components/ui/skeleton";

export default function ExplorerPage() {
  const [themes, setThemes] = useState<DiscoveredTheme[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchExplorer()
      .then((res) => {
        if (!cancelled) setThemes(res.themes ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Theme Explorer</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 bg-zinc-800 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Theme Explorer</h1>
          <p className="text-zinc-500 text-sm mt-1">
            Auto-discovered emerging technology directions
          </p>
        </div>
        <span className="text-sm text-zinc-600">
          {themes.length} theme{themes.length !== 1 ? "s" : ""}
        </span>
      </div>
      <ExplorerGrid themes={themes} />
    </div>
  );
}
