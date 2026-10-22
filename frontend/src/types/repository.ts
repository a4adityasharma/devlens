export interface Repository {
  id: string;
  name: string;
  url: string;
  owner?: string;
  default_branch?: string;
  primary_language?: string;
  languages: Record<string, number>;
  file_count: number;
  size_bytes: number;
  frameworks: string[];
  package_managers: string[];
  entry_points: string[];
  status: "queued" | "cloning" | "scanning" | "ready" | "failed";
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface SymbolItem {
  type: string; // "function" | "class" | "method" | "import" | "call"
  name: string;
  file: string;
  line_start: number;
  line_end?: number;
  parent?: string;
  parameters?: string[];
}

export interface AnalysisOut {
  id: string;
  repository_id: string;
  commit_hash?: string;
  status: string;
  symbols: SymbolItem[];
  stats?: Record<string, any>;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface FindingOut {
  id: string;
  analysis_id: string;
  title: string;
  description?: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  category?: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  rule_id?: string;
  recommendation?: string;
}

export interface ArtifactOut {
  id: string;
  repository_id: string;
  artifact_type: string;
  content: string;
  extra?: Record<string, any>;
  created_at: string;
}

export interface UntestedSymbolOut {
  name: string;
  type: string;
  file: string;
  line_start: number;
  line_end?: number;
}

export interface ChatSourceOut {
  file: string;
  line_start: number;
  line_end: number;
  symbol: string;
}

export interface ChatResponse {
  answer: string;
  session_id: string;
  sources: ChatSourceOut[];
  graph_available: boolean;
  hit_count: number;
}

export interface SearchResultOut {
  id: string;
  score: number;
  file: string;
  symbol: string;
  type: string;
  language: string;
  start_line: number;
  end_line: number;
  text: string;
}

export interface GenerateTestResponse {
  symbol: string;
  file: string;
  framework: string;
  generated_code: string;
  validation: {
    valid?: boolean;
    syntax_valid?: boolean;
    references_symbol?: boolean;
    has_assertions?: boolean;
    passes?: boolean;
    reasons?: string[];
  };
}
