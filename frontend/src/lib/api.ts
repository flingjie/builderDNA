import type { ExplorerResponse, PainResponse, RadarResponse, VendorProfile, VendorDiff } from "./types";

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

export async function fetchExplorer(
  domain: string = "agent",
  window: number = 30,
  refresh: boolean = false
): Promise<ExplorerResponse> {
  const params = new URLSearchParams({ domain, window: String(window) });
  if (refresh) params.set("refresh", "true");
  const res = await fetch(`${API_BASE}/api/explorer?${params}`);
  if (!res.ok) return { domain: "global", snapshot_id: "", generated_at: "", window_days: window, themes: [] };
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

export async function fetchVendors(tag?: string): Promise<{ profiles: VendorProfile[]; count: number }> {
  const params = tag ? `?tag=${tag}` : "";
  const res = await fetch(`${API_BASE}/api/vendors${params}`);
  if (!res.ok) return { profiles: [], count: 0 };
  return res.json();
}

export async function fetchVendorDetail(name: string): Promise<VendorProfile> {
  const res = await fetch(`${API_BASE}/api/vendors/${name}`);
  if (!res.ok) throw new Error("Vendor not found");
  return res.json();
}

export async function fetchCompare(): Promise<{ diffs: VendorDiff[] }> {
  const res = await fetch(`${API_BASE}/api/compare`);
  if (!res.ok) return { diffs: [] };
  return res.json();
}
