"use client";
import { useRadar } from "@/hooks/use-radar";
import { RadarGrid } from "@/components/radar/RadarGrid";
import { TrendMap } from "@/components/charts/TrendMap";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  const { data, loading, error } = useRadar("agent", 60);

  if (error) return <div className="text-red-400 p-8">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Executive Radar</h1>
        <p className="text-zinc-500 text-sm mt-1">
          What to watch in AI infrastructure — last 60 days
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 bg-zinc-800 rounded-lg" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <RadarGrid topics={data?.topics || []} />
            </div>
            <div>
              <TrendMap topics={data?.topics || []} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
