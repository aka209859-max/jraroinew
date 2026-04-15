"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { fetchFactors, runAnalysis } from "@/lib/api";
import type {
  Factor,
  AnalysisRequest,
  AnalysisResponse,
  BinRow,
  SegmentResult,
} from "@/types/analysis";

// ─────────────────────────────────────────────
// 定数
// ─────────────────────────────────────────────
const YEARS = Array.from({ length: 10 }, (_, i) => 2016 + i);

const DEFAULT_YEAR_WEIGHTS: Record<string, number> = {
  "2016": 1, "2017": 2, "2018": 3, "2019": 4, "2020": 5,
  "2021": 6, "2022": 7, "2023": 8, "2024": 9, "2025": 10,
};

const SEGMENTS = [
  { id: "GLOBAL",    label: "全体 (GLOBAL)" },
  { id: "SURFACE_2", label: "芝/ダート (SURFACE_2)" },
  { id: "COURSE_27", label: "27コース分類 (COURSE_27)" },
];

const PREV_RACE_TYPES = [
  { value: "none",     label: "なし" },
  { value: "global",   label: "条件問わず直近走" },
  { value: "course27", label: "同一コース分類" },
];

// ─────────────────────────────────────────────
// 検索可能ドロップダウン
// ─────────────────────────────────────────────
function FactorSelect({
  value,
  onChange,
  factors,
  placeholder = "カラムを選択",
  nullable = false,
}: {
  value: string;
  onChange: (v: string) => void;
  factors: Factor[];
  placeholder?: string;
  nullable?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const filtered = query.length === 0
    ? factors.slice(0, 100)
    : factors
        .filter((f) =>
          `${f.table_name}.${f.column_name}`.toLowerCase().includes(query.toLowerCase())
        )
        .slice(0, 100);

  const label = value
    ? factors.find((f) => f.column_name === value)
        ? `${factors.find((f) => f.column_name === value)!.table_name}.${value}`
        : value
    : placeholder;

  // 外側クリックで閉じる
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-left text-gray-200 hover:border-gray-500 focus:outline-none focus:border-blue-500"
      >
        <span className={value ? "text-gray-200" : "text-gray-500"}>
          {label}
        </span>
        <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-gray-700 bg-gray-900 shadow-xl">
          <div className="p-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="検索..."
              autoFocus
              className="w-full rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          <ul className="max-h-56 overflow-y-auto">
            {nullable && (
              <li
                className="cursor-pointer px-3 py-1.5 text-sm text-gray-400 hover:bg-gray-800"
                onClick={() => { onChange(""); setOpen(false); setQuery(""); }}
              >
                ─ なし ─
              </li>
            )}
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-gray-500">見つかりません</li>
            )}
            {filtered.map((f) => (
              <li
                key={`${f.table_name}.${f.column_name}`}
                className={`cursor-pointer px-3 py-1.5 text-sm hover:bg-gray-800 ${
                  value === f.column_name ? "text-blue-400 bg-gray-800" : "text-gray-300"
                }`}
                onClick={() => { onChange(f.column_name); setOpen(false); setQuery(""); }}
              >
                <span className="text-gray-500">{f.table_name}.</span>
                <span>{f.column_name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// 結果テーブル
// ─────────────────────────────────────────────
function fmt1(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toFixed(1);
}
function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toFixed(1) + "%";
}
function fmtConf(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toFixed(3);
}

function downloadCsv(data: BinRow[], filename: string) {
  const header = [
    "ビン", "単勝件数", "単勝的中", "単勝的中率", "単勝回収率",
    "複勝件数", "複勝的中", "複勝的中率", "複勝回収率",
    "単勝補正回収率", "複勝補正回収率", "信頼度",
  ];
  const rows = data.map((r) => [
    r.bin_label, r.tansho_count, r.tansho_hit, fmt1(r.tansho_hit_rate), fmt1(r.tansho_roi),
    r.fukusho_count, r.fukusho_hit, fmt1(r.fukusho_hit_rate), fmt1(r.fukusho_roi),
    fmt1(r.tansho_corrected_roi), fmt1(r.fukusho_corrected_roi), fmtConf(r.confidence),
  ]);
  const csv = [header, ...rows].map((r) => r.join(",")).join("\n");
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function ResultTable({ seg }: { seg: SegmentResult }) {
  const data = seg.data as BinRow[];
  const aboveThr = data.filter((r) => r.confidence >= 0.25).length;

  return (
    <div>
      {/* サマリーバー */}
      <div className="flex flex-wrap gap-3 mb-3 items-center">
        <span className="rounded-full bg-green-900/60 border border-green-700 px-3 py-1 text-xs text-green-300">
          単勝エッジ: {seg.edge_bins_tansho}件 / {seg.total_bins}件中
        </span>
        <span className="rounded-full bg-emerald-900/60 border border-emerald-700 px-3 py-1 text-xs text-emerald-300">
          複勝エッジ: {seg.edge_bins_fukusho}件 / {seg.total_bins}件中
        </span>
        <span className="rounded-full bg-gray-800 border border-gray-700 px-3 py-1 text-xs text-gray-400">
          信頼度0.25以上: {aboveThr}件
        </span>
        <button
          onClick={() => downloadCsv(data, `${seg.segment_name}.csv`)}
          className="ml-auto flex items-center gap-1.5 rounded-md border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-300 hover:border-gray-500 hover:text-white transition-colors"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          CSV
        </button>
      </div>

      {/* テーブル */}
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-800 text-gray-300 text-xs uppercase tracking-wider">
              {["ビン", "単勝件数", "単勝的中", "単勝的中率%", "単勝回収率%",
                "複勝件数", "複勝的中", "複勝的中率%", "複勝回収率%",
                "単勝補正%", "複勝補正%", "信頼度"].map((h) => (
                <th key={h} className="whitespace-nowrap px-3 py-2 text-right first:text-left">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => {
              const tEdge = row.tansho_corrected_roi >= 80 && row.confidence >= 0.25;
              const fEdge = row.fukusho_corrected_roi >= 80 && row.confidence >= 0.25;
              const lowConf = row.confidence < 0.25;
              const base = i % 2 === 0 ? "bg-gray-950" : "bg-gray-900";
              return (
                <tr
                  key={i}
                  className={`${base} ${lowConf ? "opacity-50" : ""} border-l-2 border-r-2 ${
                    tEdge ? "border-l-green-500" : "border-l-transparent"
                  } ${fEdge ? "border-r-emerald-500" : "border-r-transparent"}`}
                >
                  <td className="whitespace-nowrap px-3 py-1.5 text-gray-200 font-mono text-xs">
                    {row.bin_label}
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{row.tansho_count}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{row.tansho_hit}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{fmtPct(row.tansho_hit_rate)}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{fmtPct(row.tansho_roi)}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{row.fukusho_count}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{row.fukusho_hit}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{fmtPct(row.fukusho_hit_rate)}</td>
                  <td className="px-3 py-1.5 text-right text-gray-300">{fmtPct(row.fukusho_roi)}</td>
                  <td className={`px-3 py-1.5 text-right font-semibold ${tEdge ? "text-green-400" : "text-gray-300"}`}>
                    {fmtPct(row.tansho_corrected_roi)}
                  </td>
                  <td className={`px-3 py-1.5 text-right font-semibold ${fEdge ? "text-emerald-400" : "text-gray-300"}`}>
                    {fmtPct(row.fukusho_corrected_roi)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-400 font-mono text-xs">
                    {fmtConf(row.confidence)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// メインページ
// ─────────────────────────────────────────────
export default function AnalysisPage() {
  const [factors, setFactors] = useState<Factor[]>([]);
  const [factorsLoading, setFactorsLoading] = useState(true);

  // 条件
  const [segment, setSegment] = useState("GLOBAL");
  const [key1, setKey1] = useState("");
  const [key2, setKey2] = useState("");
  const [key3, setKey3] = useState("");
  const [tanshoMin, setTanshoMin] = useState("1.0");
  const [tanshoMax, setTanshoMax] = useState("100.0");
  const [fukushoMin, setFukushoMin] = useState("1.0");
  const [fukushoMax, setFukushoMax] = useState("17.0");
  const [prevRaceType, setPrevRaceType] = useState("none");
  const [yearFrom, setYearFrom] = useState(2016);
  const [yearTo, setYearTo] = useState(2025);

  // 結果
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(0);

  // ファクター取得
  useEffect(() => {
    fetchFactors()
      .then((d) => setFactors(d.factors))
      .catch(() => setFactors([]))
      .finally(() => setFactorsLoading(false));
  }, []);

  // 分析実行
  const handleAnalyze = useCallback(async () => {
    if (!key1) { setError("集計キー1を選択してください"); return; }
    setLoading(true);
    setError(null);
    setResult(null);
    setActiveTab(0);

    const request: AnalysisRequest = {
      name: [key1, key2, key3].filter(Boolean).join(" × ") || "分析",
      segment,
      key1,
      key2: key2 || undefined,
      key3: key3 || undefined,
      conditions: {},
      odds_filter: {
        tansho: [parseFloat(tanshoMin) || 1.0, parseFloat(tanshoMax) || 100.0],
        fukusho: [parseFloat(fukushoMin) || 1.0, parseFloat(fukushoMax) || 17.0],
      },
      prev_race_type: prevRaceType,
      data_period: [`${yearFrom}-01-01`, `${yearTo}-12-31`],
      year_weights: DEFAULT_YEAR_WEIGHTS,
      min_samples: 30,
      bin_config: {},
    };

    try {
      const res = await runAnalysis(request);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "エラーが発生しました");
    } finally {
      setLoading(false);
    }
  }, [segment, key1, key2, key3, tanshoMin, tanshoMax, fukushoMin, fukushoMax, prevRaceType, yearFrom, yearTo]);

  return (
    <div className="flex h-screen flex-col bg-gray-950 text-white overflow-hidden">
      {/* ヘッダー */}
      <header className="flex items-center gap-4 border-b border-gray-800 px-6 py-3 flex-shrink-0">
        <Link href="/" className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          戻る
        </Link>
        <h1 className="text-base font-semibold text-white">データ分析</h1>
      </header>

      {/* メインコンテンツ */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左パネル（条件設定） */}
        <aside className="w-72 flex-shrink-0 border-r border-gray-800 flex flex-col overflow-y-auto">
          <div className="flex-1 p-4 space-y-5">

            {/* セグメント */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">セグメント</label>
              <select
                value={segment}
                onChange={(e) => setSegment(e.target.value)}
                className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
              >
                {SEGMENTS.map((s) => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </select>
            </div>

            {/* 集計キー */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                集計キー1 <span className="text-blue-400">*</span>
              </label>
              {factorsLoading ? (
                <div className="text-xs text-gray-500">読み込み中...</div>
              ) : (
                <FactorSelect value={key1} onChange={setKey1} factors={factors} />
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">集計キー2</label>
              {factorsLoading ? (
                <div className="text-xs text-gray-500">読み込み中...</div>
              ) : (
                <FactorSelect value={key2} onChange={setKey2} factors={factors} nullable placeholder="─ なし ─" />
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">集計キー3</label>
              {factorsLoading ? (
                <div className="text-xs text-gray-500">読み込み中...</div>
              ) : (
                <FactorSelect value={key3} onChange={setKey3} factors={factors} nullable placeholder="─ なし ─" />
              )}
            </div>

            {/* オッズ条件 */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">オッズ条件</label>
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-400 w-10">単勝</span>
                  <input
                    type="number" step="0.1" min="1" value={tanshoMin}
                    onChange={(e) => setTanshoMin(e.target.value)}
                    className="w-16 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-center text-gray-200 focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-gray-500">〜</span>
                  <input
                    type="number" step="0.1" min="1" value={tanshoMax}
                    onChange={(e) => setTanshoMax(e.target.value)}
                    className="w-16 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-center text-gray-200 focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-gray-500">倍</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-400 w-10">複勝</span>
                  <input
                    type="number" step="0.1" min="1" value={fukushoMin}
                    onChange={(e) => setFukushoMin(e.target.value)}
                    className="w-16 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-center text-gray-200 focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-gray-500">〜</span>
                  <input
                    type="number" step="0.1" min="1" value={fukushoMax}
                    onChange={(e) => setFukushoMax(e.target.value)}
                    className="w-16 rounded border border-gray-700 bg-gray-900 px-2 py-1 text-center text-gray-200 focus:outline-none focus:border-blue-500"
                  />
                  <span className="text-gray-500">倍</span>
                </div>
              </div>
            </div>

            {/* 前走タイプ */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">前走タイプ</label>
              <div className="space-y-1.5">
                {PREV_RACE_TYPES.map((t) => (
                  <label key={t.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio" name="prevRaceType" value={t.value}
                      checked={prevRaceType === t.value}
                      onChange={(e) => setPrevRaceType(e.target.value)}
                      className="accent-blue-500"
                    />
                    <span className="text-sm text-gray-300">{t.label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* 分析期間 */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">分析期間</label>
              <div className="flex items-center gap-2">
                <select
                  value={yearFrom}
                  onChange={(e) => setYearFrom(Number(e.target.value))}
                  className="flex-1 rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                >
                  {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
                <span className="text-gray-500 text-sm">〜</span>
                <select
                  value={yearTo}
                  onChange={(e) => setYearTo(Number(e.target.value))}
                  className="flex-1 rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                >
                  {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
            </div>
          </div>

          {/* 実行ボタン（固定フッター） */}
          <div className="p-4 border-t border-gray-800">
            <button
              onClick={handleAnalyze}
              disabled={loading || !key1}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2.5 text-sm font-semibold text-white transition-colors"
            >
              {loading ? (
                <>
                  <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  分析中...
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                  分析実行
                </>
              )}
            </button>
            {!key1 && (
              <p className="mt-1.5 text-center text-xs text-gray-600">集計キー1を選択してください</p>
            )}
          </div>
        </aside>

        {/* 右エリア（結果表示） */}
        <main className="flex-1 overflow-y-auto">
          {/* エラー */}
          {error && (
            <div className="m-4 rounded-lg border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
              <span className="font-semibold">エラー: </span>{error}
            </div>
          )}

          {/* 実行前 */}
          {!loading && !result && !error && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="mb-4 text-gray-700">
                  <svg className="mx-auto h-16 w-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <p className="text-gray-500">条件を設定して分析を実行してください</p>
                <p className="mt-1 text-xs text-gray-700">数十秒かかる場合があります</p>
              </div>
            </div>
          )}

          {/* ローディング */}
          {loading && (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <svg className="mx-auto h-12 w-12 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <p className="mt-4 text-gray-400">分析中...</p>
                <p className="mt-1 text-xs text-gray-600">数十秒かかる場合があります</p>
              </div>
            </div>
          )}

          {/* 結果 */}
          {result && !loading && (
            <div className="p-5">
              {/* 全体サマリー */}
              <div className="mb-5 flex flex-wrap gap-3 items-center">
                <h2 className="text-sm font-semibold text-gray-300">{result.query_name}</h2>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
                    総行数: {result.total_rows.toLocaleString()}
                  </span>
                  <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
                    単勝有効: {result.valid_tansho_rows.toLocaleString()}
                  </span>
                  <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-400">
                    複勝有効: {result.valid_fukusho_rows.toLocaleString()}
                  </span>
                </div>
              </div>

              {/* セグメントタブ */}
              {result.segments.length > 1 && (
                <div className="mb-4 flex gap-1 border-b border-gray-800">
                  {result.segments.map((seg, i) => (
                    <button
                      key={seg.segment_name}
                      onClick={() => setActiveTab(i)}
                      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                        activeTab === i
                          ? "border-blue-500 text-blue-400"
                          : "border-transparent text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {seg.segment_name}
                      <span className="ml-1.5 rounded-full bg-gray-800 px-1.5 py-0.5 text-xs text-gray-500">
                        {seg.total_bins}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* アクティブセグメントの結果 */}
              {result.segments[activeTab] && (
                <ResultTable seg={result.segments[activeTab]} />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
