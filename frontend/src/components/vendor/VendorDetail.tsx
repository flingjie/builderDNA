"use client";
import { useEffect, useState } from "react";
import { fetchVendorDetail } from "@/lib/api";
import type { VendorProfile } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export function VendorDetail({ name }: { name: string }) {
  const [vendor, setVendor] = useState<VendorProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchVendorDetail(name)
      .then((data) => {
        if (!cancelled) setVendor(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load vendor");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [name]);

  if (loading) return <Skeleton className="h-48 w-full" />;
  if (error) return <div className="text-red-400 p-4">Error: {error}</div>;
  if (!vendor) return null;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
      <div>
        <h2 className="text-xl font-bold text-zinc-100">{vendor.display_name || vendor.name}</h2>
        <div className="flex gap-2 mt-2">
          {vendor.tags.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">{tag}</Badge>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <p className="text-zinc-500">Public Repos</p>
          <p className="text-zinc-200 font-semibold">{vendor.total_public_repos}</p>
        </div>
        <div>
          <p className="text-zinc-500">Total Stars</p>
          <p className="text-zinc-200 font-semibold">★ {vendor.total_stars.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-zinc-500">Group</p>
          <p className="text-zinc-200 font-semibold">{vendor.comparison_group === "domestic" ? "🇨🇳 Domestic" : "🌍 Overseas"}</p>
        </div>
      </div>

      {vendor.active_directions.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-zinc-400 mb-2">Active Directions</h3>
          <div className="space-y-1">
            {vendor.active_directions.map((d) => (
              <div key={d.topic} className="flex items-center justify-between text-sm">
                <span className="text-zinc-300">{d.topic}</span>
                <span className="text-zinc-500">
                  {d.trend} intensity: {d.intensity}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {vendor.recent_signals.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-zinc-400 mb-2">Recent Signals</h3>
          <div className="space-y-1 text-xs text-zinc-500">
            {vendor.recent_signals.slice(0, 5).map((s, i) => (
              <p key={i}>{s.type} — {s.repo} ({new Date(s.timestamp).toLocaleDateString()})</p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
