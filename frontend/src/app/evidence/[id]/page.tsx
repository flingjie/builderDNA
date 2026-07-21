"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchEvidence } from "@/lib/api";
import type { OpportunityCard as OpportunityCardType } from "@/lib/types";
import { OpportunityCard } from "@/components/opportunity/OpportunityCard";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TrendingUp,
  Layers,
  GitBranch,
  FileText,
} from "lucide-react";

function EvidenceSection({
  icon,
  title,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-emerald-400">{icon}</span>
        <h3 className="text-sm font-semibold text-zinc-200">{title}</h3>
        <Badge variant="outline" className="ml-auto text-xs">
          {items.length}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((item, i) => (
          <Badge key={i} variant="secondary" className="text-xs">
            {item}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export default function EvidencePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const [card, setCard] = useState<OpportunityCardType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchEvidence(id)
      .then((res) => {
        if (!cancelled) {
          setCard(res.card ?? res);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load evidence");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      </div>
    );
  }

  if (error || !card) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Evidence</h1>
        <div className="text-zinc-500 p-8 text-center border border-zinc-800 rounded-lg">
          <p className="text-lg mb-2">Evidence not found</p>
          <p className="text-sm">
            {error ?? `No evidence found for opportunity "${id}".`}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="text-sm text-zinc-500">
        <a href="/opportunities" className="hover:text-emerald-400 transition-colors">
          Opportunities
        </a>
        <span className="mx-2">/</span>
        <span className="text-zinc-300">{card.title}</span>
      </div>

      {/* Full opportunity card */}
      <OpportunityCard card={card} />

      {/* Evidence section */}
      <h2 className="text-xl font-bold text-zinc-200 mt-8">Evidence Details</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EvidenceSection
          icon={<TrendingUp className="size-4" />}
          title="Trends"
          items={card.evidence.trends}
        />
        <EvidenceSection
          icon={<Layers className="size-4" />}
          title="Pain Clusters"
          items={card.evidence.pain_clusters}
        />
        <EvidenceSection
          icon={<FileText className="size-4" />}
          title="Key Issues"
          items={card.evidence.key_issues}
        />
        <EvidenceSection
          icon={<GitBranch className="size-4" />}
          title="Key Repositories"
          items={card.evidence.key_repos}
        />
      </div>
    </div>
  );
}
