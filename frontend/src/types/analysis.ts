export interface AnalysisRequest {
  name: string;
  segment: string;
  key1: string;
  key2?: string;
  key3?: string;
  conditions: Record<string, unknown>;
  odds_filter: { tansho: number[]; fukusho: number[] };
  prev_race_type: string;
  data_period: string[];
  year_weights: Record<string, number>;
  min_samples: number;
  bin_config: Record<string, unknown>;
}

export interface BinRow {
  bin_label: string;
  tansho_count: number;
  tansho_hit: number;
  tansho_hit_rate: number;
  tansho_roi: number;
  fukusho_count: number;
  fukusho_hit: number;
  fukusho_hit_rate: number;
  fukusho_roi: number;
  tansho_corrected_roi: number;
  fukusho_corrected_roi: number;
  confidence: number;
}

export interface SegmentResult {
  segment_name: string;
  data: BinRow[];
  edge_bins_tansho: number;
  edge_bins_fukusho: number;
  total_bins: number;
}

export interface AnalysisResponse {
  query_name: string;
  total_rows: number;
  valid_tansho_rows: number;
  valid_fukusho_rows: number;
  segments: SegmentResult[];
}

export interface Factor {
  table_name: string;
  column_name: string;
  data_type: string;
  comment: string;
}

export interface FactorItem {
  key: string;
  label: string;
  desc: string;
}

export interface FactorCategory {
  icon: string;
  factors: FactorItem[];
}

export interface FactorsResponse {
  categories: Record<string, FactorCategory>;
  factors: Factor[];
  total: number;
}
