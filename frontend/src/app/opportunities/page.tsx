"use client";
import { useEffect, useState } from "react";
import { fetchPain } from "@/lib/api";
import type { PainCluster } from "@/lib/types";
import { PainCard } from "@/components/opportunity/PainCard";

export default function OpportunitiesPage() {
  const [clusters, setClusters] = useState<PainCluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchPain()
      .then((res) => {
        if (!cancelled) {
          setClusters(res.clusters ?? []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load pain data");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Opportunity Map</h1>
        <div className="text-zinc-500 p-8 text-center">
          <p className="text-lg mb-2">Loading pain data...</p>
          <p className="text-sm">Fetching developer pain patterns from the radar engine</p>
        </div>
      </div>
    );
  }

  if (error || clusters.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Opportunity Map</h1>
        <div className="text-zinc-500 p-8 text-center border border-zinc-800 rounded-lg">
          <p className="text-lg mb-2">No pain data yet</p>
          <p className="text-sm">
            {error
              ? `${error} — ensure the backend is running.`
              : "Run builderdna radar agent first to discover developer pain patterns."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Opportunity Map</h1>
        <span className="text-sm text-zinc-500">
          {clusters.length} pain pattern{clusters.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {clusters.map((cluster) => (
          <PainCard key={cluster.id} cluster={cluster} />
        ))}
      </div>
    </div>
  );
}
