"use client";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowUp, AlertTriangle, Sparkles, Lightbulb, Target } from "lucide-react";
import type { OpportunityCard as OpportunityCardType } from "@/lib/types";
import { ValidationBadge } from "./ValidationBadge";

function scoreColor(score: number): string {
  if (score >= 8) return "bg-emerald-500/10 text-emerald-400";
  if (score >= 6) return "bg-amber-500/10 text-amber-400";
  return "bg-red-500/10 text-red-400";
}

function riskColor(risk: "low" | "medium" | "high"): string {
  switch (risk) {
    case "low":
      return "bg-emerald-500/10 text-emerald-400";
    case "medium":
      return "bg-amber-500/10 text-amber-400";
    case "high":
      return "bg-red-500/10 text-red-400";
  }
}

function scoreBarColor(score: number): string {
  if (score >= 8) return "bg-emerald-500";
  if (score >= 6) return "bg-amber-500";
  return "bg-red-500";
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="border-t border-zinc-800 pt-3 mt-1">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="text-zinc-400 shrink-0">{icon}</span>
        <span className="text-xs text-zinc-500 font-medium uppercase tracking-wider">{title}</span>
      </div>
      <div className="text-sm text-zinc-300 leading-relaxed">{children}</div>
    </div>
  );
}

export function OpportunityCard({ card }: { card: OpportunityCardType }) {
  const scorePct = Math.min((card.score / 10) * 100, 100);

  return (
    <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-5">
        {/* Header: title + badges */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg font-semibold truncate">{card.title}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge className={scoreColor(card.score)}>
                Score: {card.score.toFixed(1)}
              </Badge>
              <Badge className={riskColor(card.risk)}>
                {card.risk} risk
              </Badge>
              <ValidationBadge validation={card.validation} />
            </div>
          </div>
        </div>

        {/* Score bar */}
        <div className="w-full bg-zinc-800 rounded-full h-1.5 mb-3">
          <div
            className={`${scoreBarColor(card.score)} h-1.5 rounded-full transition-all`}
            style={{ width: `${scorePct}%` }}
          />
        </div>

        {/* Why Now */}
        <Section icon={<Sparkles className="size-3.5" />} title="Why Now">
          {card.why_now}
        </Section>

        {/* Problem */}
        <Section icon={<AlertTriangle className="size-3.5" />} title="Problem">
          {card.problem}
        </Section>

        {/* Existing Solutions */}
        {card.existing_solutions.length > 0 && (
          <Section icon={<Target className="size-3.5" />} title="Existing Solutions">
            <ul className="list-disc list-inside space-y-0.5">
              {card.existing_solutions.map((s, i) => (
                <li key={i} className="text-zinc-400 text-xs">{s}</li>
              ))}
            </ul>
          </Section>
        )}

        {/* Gap */}
        <Section icon={<Lightbulb className="size-3.5" />} title="Gap">
          {card.gap}
        </Section>

        {/* MVP */}
        <Section icon={<ArrowUp className="size-3.5" />} title="MVP">
          {card.mvp}
        </Section>
      </CardContent>
    </Card>
  );
}
