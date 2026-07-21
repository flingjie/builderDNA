"use client";
import { useEffect, useState } from "react";
import { fetchOpportunities } from "@/lib/api";
import type { OpportunityCard as OpportunityCardType } from "@/lib/types";
import { OpportunityCard } from "@/components/opportunity/OpportunityCard";
import { Skeleton } from "@/components/ui/skeleton";

export default function OpportunitiesPage() {
  const [cards, setCards] = useState<OpportunityCardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchOpportunities()
      .then((res) => {
        if (!cancelled) {
          setCards(res.cards ?? []);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load opportunities");
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
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Opportunity Map</h1>
          <Skeleton className="h-5 w-24" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3">
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-1.5 w-full" />
              <div className="space-y-2">
                <Skeleton className="h-3 w-1/5" />
                <Skeleton className="h-4 w-full" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-3 w-1/5" />
                <Skeleton className="h-4 w-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error || cards.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Opportunity Map</h1>
        <div className="text-zinc-500 p-8 text-center border border-zinc-800 rounded-lg">
          <p className="text-lg mb-2">No opportunities yet</p>
          <p className="text-sm">
            {error
              ? `${error} — ensure the backend is running.`
              : "Run builderdna radar agent first."}
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
          {cards.length} opportunit{cards.length !== 1 ? "ies" : "y"}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map((card) => (
          <OpportunityCard key={card.id} card={card} />
        ))}
      </div>
    </div>
  );
}
