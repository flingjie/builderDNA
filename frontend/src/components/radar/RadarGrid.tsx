"use client";
import type { TopicTrend } from "@/lib/types";
import { RadarCard } from "./RadarCard";

export function RadarGrid({ topics }: { topics: TopicTrend[] }) {
  if (topics.length === 0) {
    return <div className="text-zinc-500 p-8 text-center">No trend data available</div>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {topics.map((topic) => (
        <RadarCard key={topic.topic} topic={topic} />
      ))}
    </div>
  );
}
