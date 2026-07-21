"use client";
import { useRadar } from "@/hooks/use-radar";
import { TrendMap } from "@/components/charts/TrendMap";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function TrendsPage() {
  const { data, loading } = useRadar("agent", 60);

  const allRepos = (data?.topics || []).flatMap((t) =>
    t.top_repos.map((r) => ({ ...r, topic: t.topic }))
  );
  allRepos.sort((a, b) => b.trend_score - a.trend_score);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trend Landscape</h1>

      <TrendMap topics={data?.topics || []} />

      {loading ? (
        <div className="text-zinc-500 p-8 text-center">Loading trends...</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Repo</TableHead>
              <TableHead>Topic</TableHead>
              <TableHead className="text-right">Stars</TableHead>
              <TableHead className="text-right">Velocity</TableHead>
              <TableHead className="text-right">Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {allRepos.map((repo) => (
              <TableRow key={repo.full_name}>
                <TableCell className="font-mono text-sm">{repo.full_name}</TableCell>
                <TableCell>{repo.topic}</TableCell>
                <TableCell className="text-right">{repo.stars.toLocaleString()}</TableCell>
                <TableCell className="text-right">{repo.velocity.toFixed(1)}</TableCell>
                <TableCell className="text-right">{repo.trend_score.toFixed(0)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
