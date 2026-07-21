"use client";
import type { VendorProfile, VendorDiff } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

export function VendorMatrix({
  profiles,
  diffs,
}: {
  profiles: VendorProfile[];
  diffs: VendorDiff[];
}) {
  const domestic = profiles.filter((p) => p.comparison_group === "domestic");
  const overseas = profiles.filter((p) => p.comparison_group === "overseas");

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-semibold mb-3">🇨🇳 国产厂商 ({domestic.length})</h2>
          <div className="space-y-2">
            {domestic.map((v) => (
              <div key={v.name} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{v.display_name || v.name}</p>
                  <p className="text-xs text-zinc-500">
                    {v.total_public_repos} repos · ★ {v.total_stars.toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-1 flex-wrap max-w-[200px] justify-end">
                  {v.active_directions.slice(0, 3).map((d) => (
                    <Badge key={d.topic} variant="secondary" className="text-xs">
                      {d.topic}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-3">🌍 海外厂商 ({overseas.length})</h2>
          <div className="space-y-2">
            {overseas.map((v) => (
              <div key={v.name} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{v.display_name || v.name}</p>
                  <p className="text-xs text-zinc-500">
                    {v.total_public_repos} repos · ★ {v.total_stars.toLocaleString()}
                  </p>
                </div>
                <div className="flex gap-1 flex-wrap max-w-[200px] justify-end">
                  {v.active_directions.slice(0, 3).map((d) => (
                    <Badge key={d.topic} variant="secondary" className="text-xs">
                      {d.topic}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {diffs.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">📊 战略差异对比</h2>
          {diffs.map((diff) => (
            <div key={diff.dimension} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 space-y-3">
              <h3 className="text-md font-semibold text-zinc-100">{diff.dimension}</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-zinc-500 mb-1">🇨🇳 国产</p>
                  <p className="text-zinc-300">{diff.domestic_summary}</p>
                </div>
                <div>
                  <p className="text-zinc-500 mb-1">🌍 海外</p>
                  <p className="text-zinc-300">{diff.overseas_summary}</p>
                </div>
              </div>
              <p className="text-xs text-zinc-600">
                📊 共性: {diff.common_patterns}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
