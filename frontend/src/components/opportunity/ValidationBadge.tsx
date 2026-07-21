"use client";
import type { ValidationResult } from "@/lib/types";

const config = {
  high: { label: "🟢 高确定", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" },
  medium: { label: "🟡 中等", color: "bg-amber-500/10 text-amber-400 border-amber-500/30" },
  low: { label: "🔴 低确定", color: "bg-red-500/10 text-red-400 border-red-500/30" },
};

export function ValidationBadge({ validation }: { validation?: ValidationResult | null }) {
  if (!validation) return null;

  const c = config[validation.confidence] || config.low;

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-xs ${c.color}`}
         title={validation.summary}>
      {c.label}
    </div>
  );
}
