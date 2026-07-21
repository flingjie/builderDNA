"use client";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { PainCluster } from "@/lib/types";

function severityColor(severity: number): string {
  if (severity >= 4) return "bg-red-500";
  if (severity >= 3) return "bg-amber-500";
  if (severity >= 2) return "bg-emerald-500";
  return "bg-zinc-500";
}

function severityLabel(severity: number): string {
  if (severity >= 4) return "bg-red-500/10 text-red-400";
  if (severity >= 3) return "bg-amber-500/10 text-amber-400";
  if (severity >= 2) return "bg-emerald-500/10 text-emerald-400";
  return "bg-zinc-500/10 text-zinc-400";
}

export function PainCard({ cluster }: { cluster: PainCluster }) {
  const barColor = severityColor(cluster.severity);
  const severityPct = Math.min((cluster.severity / 5) * 100, 100);

  return (
    <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-5">
        {/* Header: title + severity badge */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg font-semibold truncate">{cluster.title}</span>
              <Badge className={severityLabel(cluster.severity)}>
                {cluster.severity.toFixed(1)}
              </Badge>
            </div>
            <div className="text-sm text-zinc-500">
              {cluster.frequency} issues &middot; {cluster.affected_repos.length} repos
            </div>
          </div>
        </div>

        {/* Severity bar */}
        <div className="w-full bg-zinc-800 rounded-full h-1.5 mb-3">
          <div
            className={`${barColor} h-1.5 rounded-full transition-all`}
            style={{ width: `${severityPct}%` }}
          />
        </div>

        {/* Root cause description */}
        <p className="text-sm text-zinc-300 mb-3 leading-relaxed">{cluster.description}</p>

        {/* Affected repos */}
        {cluster.affected_repos.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {cluster.affected_repos.map((repo) => (
              <Badge key={repo} variant="outline" className="text-xs">
                {repo}
              </Badge>
            ))}
          </div>
        )}

        {/* Top evidence issues */}
        {cluster.evidence.length > 0 && (
          <div className="space-y-1.5 border-t border-zinc-800 pt-3 mt-1">
            <span className="text-xs text-zinc-500 font-medium uppercase tracking-wider">Evidence</span>
            {cluster.evidence.slice(0, 3).map((issue) => (
              <div key={`${issue.repo}-${issue.issue_number}`} className="flex items-start gap-2">
                <a
                  href={issue.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-zinc-400 hover:text-emerald-400 truncate flex-1 transition-colors"
                >
                  {issue.repo}#{issue.issue_number}: {issue.title}
                </a>
                <span className="text-xs text-zinc-600 shrink-0">
                  {issue.comments} 💬
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
