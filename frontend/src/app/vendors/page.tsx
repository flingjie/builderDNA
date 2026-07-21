"use client";
import { useState, useEffect } from "react";
import { fetchVendors, fetchCompare } from "@/lib/api";
import type { VendorProfile, VendorDiff } from "@/lib/types";
import { VendorMatrix } from "@/components/vendor/VendorMatrix";
import { Skeleton } from "@/components/ui/skeleton";

export default function VendorsPage() {
  const [profiles, setProfiles] = useState<VendorProfile[]>([]);
  const [diffs, setDiffs] = useState<VendorDiff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchVendors(), fetchCompare()])
      .then(([vendorRes, diffRes]) => {
        if (!cancelled) {
          setProfiles(vendorRes.profiles ?? []);
          setDiffs(diffRes.diffs ?? []);
        }
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
        <h1 className="text-2xl font-bold">Vendor Radar</h1>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Vendor Radar</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Track what domestic and overseas AI vendors are building on GitHub
        </p>
      </div>
      <VendorMatrix profiles={profiles} diffs={diffs} />
    </div>
  );
}
