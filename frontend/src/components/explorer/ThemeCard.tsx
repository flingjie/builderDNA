// frontend/src/components/explorer/ThemeCard.tsx
"use client";
import type { DiscoveredTheme } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

const stageConfig: Record<string, { label: string; color: string }> = {
  accelerating: { label: "🔥 Accelerating", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" },
  emerging: { label: "🆕 Emerging", color: "bg-amber-500/10 text-amber-400 border-amber-500/30" },
  stable: { label: "➡️ Stable", color: "bg-zinc-500/10 text-zinc-400 border-zinc-500/30" },
  cooling: { label: "📉 Cooling", color: "bg-red-500/10 text-red-400 border-red-500/30" },
};

export function ThemeCard({ theme }: { theme: DiscoveredTheme }) {
  const stage = stageConfig[theme.stage] || stageConfig.stable;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3 hover:border-zinc-700 transition-colors">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-100">{theme.topic}</h3>
        <div className="flex gap-2">
          {theme.is_new && <Badge variant="secondary" className="text-xs">New</Badge>}
          <Badge className={`text-xs border ${stage.color}`}>{stage.label}</Badge>
        </div>
      </div>

      <p className="text-sm text-zinc-400">{theme.description}</p>

      <div className="flex gap-4 text-xs text-zinc-500">
        <span>{theme.repo_count} repos</span>
        <span>★ {theme.avg_stars.toFixed(0)} avg</span>
        <span>↑ {theme.velocity.toFixed(1)}/day</span>
      </div>

      {theme.sample_repos.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-zinc-600 font-medium">Sample repos</p>
          {theme.sample_repos.map((repo) => (
            <a
              key={repo}
              href={`https://github.com/${repo}`}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-xs font-mono text-blue-400 hover:text-blue-300 truncate"
            >
              {repo}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
