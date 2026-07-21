"use client";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { TopicTrend } from "@/lib/types";

const stageConfig: Record<string, { emoji: string; color: string }> = {
  accelerating: { emoji: "\u{1F680}", color: "bg-emerald-500/10 text-emerald-400" },
  emerging: { emoji: "↑", color: "bg-amber-500/10 text-amber-400" },
  mainstream: { emoji: "→", color: "bg-zinc-500/10 text-zinc-400" },
  declining: { emoji: "↓", color: "bg-red-500/10 text-red-400" },
};

export function RadarCard({ topic, vendorCount }: { topic: TopicTrend; vendorCount?: number }) {
  const cfg = stageConfig[topic.stage] || stageConfig.mainstream;

  return (
    <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg font-semibold">{topic.topic}</span>
              <Badge className={cfg.color}>{topic.stage}</Badge>
              {vendorCount != null && vendorCount > 0 && (
                <Badge variant="outline" className="text-xs text-zinc-500">
                  {vendorCount} vendor{vendorCount > 1 ? "s" : ""}
                </Badge>
              )}
            </div>
            <div className="text-sm text-zinc-500">
              {topic.evidence_count} repos &middot; {topic.growth_velocity.toFixed(1)} stars/day
            </div>
          </div>
          <div className="text-2xl font-bold text-zinc-100">
            {topic.growth_velocity.toFixed(0)}
          </div>
        </div>

        {/* Growth bar */}
        <div className="w-full bg-zinc-800 rounded-full h-1.5 mb-3">
          <div
            className="bg-emerald-500 h-1.5 rounded-full transition-all"
            style={{ width: `${Math.min(topic.growth_velocity * 2, 100)}%` }}
          />
        </div>

        {/* Top repos */}
        <div className="space-y-1">
          {topic.top_repos.slice(0, 3).map((repo) => (
            <div key={repo.full_name} className="flex justify-between text-xs text-zinc-400">
              <span className="truncate max-w-[200px]">{repo.full_name}</span>
              <span className="text-zinc-500">&#11088; {repo.stars.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
