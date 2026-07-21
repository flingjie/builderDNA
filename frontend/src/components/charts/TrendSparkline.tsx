"use client";
import ReactECharts from "echarts-for-react";
import type { TopicTrend } from "@/lib/types";

/**
 * TrendSparkline -- a mini sparkline for a single topic's velocity.
 * Shows a thin line chart with the topic name centered below.
 */
export function TrendSparkline({ topic }: { topic: TopicTrend }) {
  // Generate a simple synthetic sparkline from confidence and velocity
  const points = [0.1, 0.3, 0.5, 0.7, 0.9].map((t) =>
    Math.round(t * topic.growth_velocity * (0.8 + 0.4 * Math.random()))
  );

  const option = {
    backgroundColor: "transparent",
    grid: { top: 4, right: 4, bottom: 4, left: 4 },
    xAxis: { show: false, type: "category" as const, data: ["", "", "", "", ""] },
    yAxis: { show: false, min: 0 },
    series: [
      {
        type: "line" as const,
        data: points,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color: "#10b981" },
        areaStyle: {
          color: { type: "linear" as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(16,185,129,0.3)" }, { offset: 1, color: "rgba(16,185,129,0)" }] },
        },
      },
    ],
  };

  return (
    <div className="flex flex-col items-center">
      <ReactECharts option={option} style={{ width: 120, height: 40 }} theme="dark" />
      <span className="text-xs text-zinc-500 truncate max-w-[120px]">{topic.topic}</span>
    </div>
  );
}
