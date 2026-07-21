import type { PainResponse, RadarResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchRadar(
  domain: string,
  window: number = 60,
  refresh: boolean = false
): Promise<RadarResponse> {
  const params = new URLSearchParams({ domain, window: String(window) });
  if (refresh) params.set("refresh", "true");
  const res = await fetch(`${API_BASE}/api/radar?${params}`);
  if (!res.ok) throw new Error(`Radar fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchPain(domain: string = "agent"): Promise<PainResponse> {
  const res = await fetch(`${API_BASE}/api/pain?domain=${domain}`);
  if (!res.ok) return { clusters: [], issue_count: 0, repos_analyzed: [], id: "", domain };
  return res.json();
}

export async function fetchOpportunities(domain: string = "agent") {
  const res = await fetch(`${API_BASE}/api/opportunities?domain=${domain}`);
  if (!res.ok) return { cards: [] };
  return res.json();
}

export async function fetchEvidence(id: string, domain: string = "agent") {
  const res = await fetch(`${API_BASE}/api/evidence/${id}?domain=${domain}`);
  if (!res.ok) throw new Error("Not found");
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}
