import type { AnalysisRequest, AnalysisResponse, Factor } from "@/types/analysis";

const API_BASE = "http://localhost:8000/api";

export async function fetchFactors(): Promise<Factor[]> {
  const res = await fetch(`${API_BASE}/analysis/factors`);
  if (!res.ok) throw new Error("ファクター取得失敗");
  const data = await res.json();
  return data.factors || data;
}

export async function fetchSegments(): Promise<{
  segments: { id: string; name: string; description: string }[];
}> {
  const res = await fetch(`${API_BASE}/analysis/segments`);
  if (!res.ok) throw new Error("セグメント取得失敗");
  return res.json();
}

export async function runAnalysis(request: AnalysisRequest): Promise<AnalysisResponse> {
  const res = await fetch(`${API_BASE}/analysis/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "不明なエラー" }));
    throw new Error(error.detail || "分析実行に失敗しました");
  }
  return res.json();
}
