"use client";
import { useState, useEffect } from "react";
import { fetchRadar } from "@/lib/api";
import type { RadarResponse } from "@/lib/types";

export function useRadar(domain: string = "agent", window: number = 60) {
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchRadar(domain, window)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [domain, window]);

  return { data, loading, error };
}
