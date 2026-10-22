import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createRepository, listRepositories } from "../services/api";
import type { Repository } from "../types/repository";
import {
  Cpu,
  GitBranch,
  Globe,
  ArrowRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
  FileCode2,
  Sparkles,
  Network,
  Shield,
  TestTube2,
  MessageSquare,
  Layers,
  RefreshCw,
  Plus,
  ChevronRight,
  Code2,
  Zap,
} from "lucide-react";

const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; dot: string; pulse: boolean }
> = {
  queued: {
    label: "Queued",
    color: "text-slate-400",
    dot: "bg-slate-500",
    pulse: false,
  },
  cloning: {
    label: "Cloning...",
    color: "text-amber-400",
    dot: "bg-amber-400",
    pulse: true,
  },
  scanning: {
    label: "Scanning...",
    color: "text-indigo-400",
    dot: "bg-indigo-400",
    pulse: true,
  },
  ready: {
    label: "Ready",
    color: "text-emerald-400",
    dot: "bg-emerald-400",
    pulse: false,
  },
  failed: {
    label: "Failed",
    color: "text-red-400",
    dot: "bg-red-500",
    pulse: false,
  },
};

const LANG_COLORS: Record<string, string> = {
  Python: "bg-sky-500",
  TypeScript: "bg-blue-500",
  JavaScript: "bg-yellow-400",
  Go: "bg-cyan-400",
  Rust: "bg-orange-500",
  Java: "bg-red-500",
  Ruby: "bg-pink-500",
  "C++": "bg-violet-500",
  C: "bg-slate-400",
  PHP: "bg-purple-400",
};

const FEATURE_CARDS = [
  {
    icon: <Layers className="w-5 h-5" />,
    color: "text-indigo-400",
    bg: "bg-indigo-500/10 border-indigo-500/20",
    title: "Architecture Analysis",
    desc: "Auto-inferred layer diagrams from AST call topology",
  },
  {
    icon: <Network className="w-5 h-5" />,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/20",
    title: "Knowledge Graph",
    desc: "Neo4j DEFINES/CALLS/CONTAINS relationships, live canvas viz",
  },
  {
    icon: <Shield className="w-5 h-5" />,
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
    title: "Security Agent",
    desc: "Semgrep + Bandit static analysis, OWASP-aligned findings",
  },
  {
    icon: <TestTube2 className="w-5 h-5" />,
    color: "text-sky-400",
    bg: "bg-sky-500/10 border-sky-500/20",
    title: "Testing Agent",
    desc: "Coverage gap detection + Stage A validated test generation",
  },
  {
    icon: <MessageSquare className="w-5 h-5" />,
    color: "text-purple-400",
    bg: "bg-purple-500/10 border-purple-500/20",
    title: "RAG AI Chat",
    desc: "Evidence-grounded Q&A via Neo4j graph + Qdrant vector retrieval",
  },
  {
    icon: <Code2 className="w-5 h-5" />,
    color: "text-rose-400",
    bg: "bg-rose-500/10 border-rose-500/20",
    title: "Code Intelligence",
    desc: "Tree-sitter AST symbol table: functions, classes, imports",
  },
];

function RepoCard({ repo }: { repo: Repository }) {
  const cfg = STATUS_CONFIG[repo.status] ?? STATUS_CONFIG.queued;
  const langColor = LANG_COLORS[repo.primary_language ?? ""] ?? "bg-slate-500";
  const isReady = repo.status === "ready";
  const isProcessing = repo.status === "cloning" || repo.status === "scanning";

  const card = (
    <div
      className={`group relative rounded-2xl border bg-slate-900/60 backdrop-blur-sm p-5 transition-all duration-200 overflow-hidden
        ${isReady ? "border-slate-700/80 hover:border-indigo-500/50 hover:bg-slate-900/80 hover:shadow-lg hover:shadow-indigo-500/5 cursor-pointer" : "border-slate-800"}
      `}
    >
      {/* Subtle top gradient for ready repos */}
      {isReady && (
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-500/40 to-transparent" />
      )}

      <div className="flex items-start justify-between gap-4">
        {/* Left: icon + name */}
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-10 h-10 rounded-xl flex-shrink-0 flex items-center justify-center border
            ${isReady ? "bg-gradient-to-br from-indigo-600/20 to-violet-600/20 border-indigo-500/30 group-hover:border-indigo-400/40 transition-colors" : "bg-slate-800/60 border-slate-700/50"}`}
          >
            <GitBranch
              className={`w-5 h-5 ${isReady ? "text-indigo-400" : "text-slate-500"}`}
            />
          </div>

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-slate-500 truncate">
                {repo.owner}
              </span>
              <span className="text-slate-700">/</span>
              <span className="font-bold text-sm text-white tracking-wide truncate">
                {repo.name}
              </span>
            </div>

            <div className="flex items-center gap-3 mt-1 text-xs text-slate-400 flex-wrap">
              {repo.primary_language && (
                <span className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${langColor}`} />
                  {repo.primary_language}
                </span>
              )}
              <span className="flex items-center gap-1">
                <FileCode2 className="w-3 h-3 text-slate-500" />
                {repo.file_count.toLocaleString()} files
              </span>
              {repo.frameworks?.length > 0 && (
                <span className="text-slate-500 truncate">
                  {repo.frameworks.slice(0, 2).join(", ")}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Right: status + arrow */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              {cfg.pulse && (
                <span
                  className={`animate-ping absolute inline-flex h-full w-full rounded-full ${cfg.dot} opacity-75`}
                />
              )}
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${cfg.dot}`}
              />
            </span>
            <span className={`text-xs font-semibold ${cfg.color}`}>
              {isProcessing && (
                <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
              )}
              {cfg.label}
            </span>
          </div>

          {isReady && (
            <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all" />
          )}
        </div>
      </div>

      {/* Error message */}
      {repo.error_message && (
        <div className="mt-3 flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span className="truncate">{repo.error_message}</span>
        </div>
      )}

      {/* Ready badge row */}
      {isReady && (
        <div className="mt-3 pt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
          <span className="flex items-center gap-1.5 text-emerald-400">
            <CheckCircle2 className="w-3 h-3" />
            Analysis complete — open dashboard
          </span>
          <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-indigo-400 transition-colors" />
        </div>
      )}
    </div>
  );

  return isReady ? (
    <Link to={`/repositories/${repo.id}`}>{card}</Link>
  ) : (
    card
  );
}

export default function RepositoriesPage() {
  const [url, setUrl] = useState("");
  const [repos, setRepos] = useState<Repository[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  async function refresh(showIndicator = false) {
    if (showIndicator) setRefreshing(true);
    try {
      const data = await listRepositories();
      setRepos(data);
    } finally {
      if (showIndicator) setRefreshing(false);
    }
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(() => refresh(), 3500);
    return () => clearInterval(interval);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setError(null);
    setSuccess(false);
    setSubmitting(true);
    try {
      await createRepository(url.trim());
      setUrl("");
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
      await refresh();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to submit repository");
    } finally {
      setSubmitting(false);
    }
  }

  const readyRepos = repos.filter((r) => r.status === "ready");
  const processingRepos = repos.filter(
    (r) => r.status === "cloning" || r.status === "scanning" || r.status === "queued"
  );
  const failedRepos = repos.filter((r) => r.status === "failed");

  return (
    <div className="min-h-[calc(100vh-64px)]">
      {/* ── Hero Section ─────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden">
        {/* Background glows */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-20 right-0 w-[400px] h-[300px] bg-violet-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-12">
          {/* Tag line */}
          <div className="flex justify-center mb-6">
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-xs font-semibold text-indigo-300">
              <Zap className="w-3.5 h-3.5 text-indigo-400" />
              Code Intelligence Platform · 10 AI Agents
            </span>
          </div>

          {/* Title */}
          <h1 className="text-center text-4xl sm:text-5xl font-black tracking-tight leading-tight">
            <span className="gradient-text">DevLens AI</span>
          </h1>
          <p className="text-center text-slate-400 mt-4 text-base max-w-2xl mx-auto leading-relaxed">
            Paste any public GitHub repository URL. DevLens will clone, parse,
            and index it using Tree-sitter AST, Neo4j graph, and Qdrant vector
            embeddings — then surface agent-powered insights.
          </p>

          {/* Submit Form */}
          <div className="mt-10 max-w-2xl mx-auto">
            <form onSubmit={handleSubmit}>
              <div
                className={`flex items-center gap-2 p-2 rounded-2xl border bg-slate-900/80 backdrop-blur-sm shadow-2xl transition-all duration-200
                ${error ? "border-red-500/40" : success ? "border-emerald-500/40" : "border-slate-700/80 focus-within:border-indigo-500/60"}`}
              >
                <div className="flex items-center gap-2 pl-2 flex-1 min-w-0">
                  <Globe className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  <input
                    id="repo-url-input"
                    type="url"
                    value={url}
                    onChange={(e) => {
                      setUrl(e.target.value);
                      if (error) setError(null);
                    }}
                    placeholder="https://github.com/owner/repository"
                    className="flex-1 bg-transparent text-sm text-slate-200 placeholder:text-slate-500 outline-none min-w-0 py-2"
                    disabled={submitting}
                    required
                  />
                </div>
                <button
                  id="analyze-btn"
                  type="submit"
                  disabled={submitting || !url.trim()}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-all duration-200 shadow-lg shadow-indigo-500/25 flex-shrink-0"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Cloning...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Analyze</span>
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Feedback messages */}
            {error && (
              <div className="mt-3 flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5 animate-in">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                {error}
              </div>
            )}
            {success && (
              <div className="mt-3 flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-4 py-2.5 animate-in">
                <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                Repository queued for analysis — scanning will begin shortly
              </div>
            )}

            <p className="text-center text-xs text-slate-600 mt-3">
              Works with any public GitHub repository · Max ~10,000 files
            </p>
          </div>
        </div>
      </div>

      {/* ── Feature cards ────────────────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pb-12">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {FEATURE_CARDS.map((f) => (
            <div
              key={f.title}
              className={`rounded-xl border p-3.5 ${f.bg} transition-all hover:scale-[1.02] duration-200`}
            >
              <div className={`${f.color} mb-2`}>{f.icon}</div>
              <div className="text-xs font-semibold text-white leading-tight">
                {f.title}
              </div>
              <div className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                {f.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Repository List ───────────────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        {repos.length > 0 ? (
          <div className="space-y-6">
            {/* Header row */}
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">
                  Repositories
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  {readyRepos.length} ready · {processingRepos.length} processing
                  {failedRepos.length > 0 && ` · ${failedRepos.length} failed`}
                </p>
              </div>
              <button
                id="refresh-btn"
                onClick={() => refresh(true)}
                disabled={refreshing}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-400 hover:text-white hover:border-slate-700 transition"
                title="Refresh repository list"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-indigo-400" : ""}`}
                />
                Refresh
              </button>
            </div>

            {/* Processing repos */}
            {processingRepos.length > 0 && (
              <div className="space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                  Processing
                </div>
                <div className="space-y-2">
                  {processingRepos.map((r) => (
                    <RepoCard key={r.id} repo={r} />
                  ))}
                </div>
              </div>
            )}

            {/* Ready repos */}
            {readyRepos.length > 0 && (
              <div className="space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  Ready to Explore
                </div>
                <div className="space-y-2">
                  {readyRepos.map((r) => (
                    <RepoCard key={r.id} repo={r} />
                  ))}
                </div>
              </div>
            )}

            {/* Failed repos */}
            {failedRepos.length > 0 && (
              <div className="space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  <AlertCircle className="w-3.5 h-3.5 text-red-400" />
                  Failed
                </div>
                <div className="space-y-2">
                  {failedRepos.map((r) => (
                    <RepoCard key={r.id} repo={r} />
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Empty state */
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-600/20 to-violet-600/20 border border-indigo-500/20 flex items-center justify-center mb-6 shadow-xl shadow-indigo-500/10">
              <Cpu className="w-10 h-10 text-indigo-400" />
            </div>
            <h3 className="text-xl font-bold text-white">No repositories yet</h3>
            <p className="text-sm text-slate-400 mt-2 max-w-sm">
              Paste a GitHub URL above to start your first repository
              analysis. DevLens will index it in seconds.
            </p>
            <div className="mt-6 flex items-center gap-2 text-xs text-slate-500">
              <span>Try</span>
              <button
                onClick={() =>
                  setUrl("https://github.com/pallets/flask")
                }
                className="text-indigo-400 hover:text-indigo-300 font-mono underline underline-offset-2 transition"
              >
                github.com/pallets/flask
              </button>
              <span>or</span>
              <button
                onClick={() =>
                  setUrl("https://github.com/octocat/Hello-World")
                }
                className="text-indigo-400 hover:text-indigo-300 font-mono underline underline-offset-2 transition"
              >
                github.com/octocat/Hello-World
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
