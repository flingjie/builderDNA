"use client";
import ReactECharts from "echarts-for-react";
import type { TopicTrend } from "@/lib/types";

interface EChartsItemParams {
  name: string;
  value: number[];
  dataIndex: number;
  color?: string;
}

export function TrendMap({ topics }: { topics: TopicTrend[] }) {
  const data = topics.map((t) => ({
    name: t.topic,
    value: [t.confidence * 100, t.growth_velocity],
    stage: t.stage,
  }));

  const option = {
    backgroundColor: "transparent",
    grid: { top: 40, right: 40, bottom: 40, left: 60 },
    xAxis: {
      name: "Market Maturity →",
      nameLocation: "center",
      nameGap: 30,
      nameTextStyle: { color: "#71717a" },
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: "#3f3f46" } },
      splitLine: { lineStyle: { color: "#27272a" } },
    },
    yAxis: {
      name: "Growth Velocity ↑",
      nameLocation: "center",
      nameGap: 40,
      nameTextStyle: { color: "#71717a" },
      axisLine: { lineStyle: { color: "#3f3f46" } },
      splitLine: { lineStyle: { color: "#27272a" } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: (val: number[]) => Math.max(20, val[1] * 2),
        data: data,
        itemStyle: {
          color: (params: EChartsItemParams) => {
            const stage = data[params.dataIndex]?.stage;
            switch (stage) {
              case "accelerating": return "#10b981";
              case "emerging": return "#f59e0b";
              case "mainstream": return "#71717a";
              default: return "#ef4444";
            }
          },
        },
        label: {
          show: true,
          formatter: "{b}",
          position: "right",
          color: "#a1a1aa",
          fontSize: 12,
        },
      },
    ],
    tooltip: {
      trigger: "item",
      formatter: (params: EChartsItemParams) =>
        `<strong>${params.name}</strong><br/>Maturity: ${params.value[0].toFixed(0)}<br/>Velocity: ${params.value[1].toFixed(1)}`,
    },
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-zinc-300 mb-4">Trend Landscape</h2>
      <ReactECharts option={option} style={{ height: 400 }} theme="dark" />
    </div>
  );
}
