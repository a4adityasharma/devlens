import React, { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  getRepository,
  getLatestAnalysis,
  getArchitecture,
  getFindings,
  getUntestedSymbols,
  runSecurityScan,
} from "../services/api";
import type {
  Repository,
  AnalysisOut,
  ArtifactOut,
  FindingOut,
  UntestedSymbolOut,
} from "../types/repository";
import {
  LayoutDashboard,
  FolderTree,
  Network,
  Code2,
  Shield,
  TestTube2,
  MessageSquare,
  Loader2,
  AlertCircle,
  ArrowLeft,
  ExternalLink,
  GitBranch,
  FileCode2,
  Clock,
  RefreshCw,
} from "lucide-react";

import { OverviewTab } from "../components/tabs/OverviewTab";
import { ArchitectureTab } from "../components/tabs/ArchitectureTab";
import { KnowledgeGraphTab } from "../components/tabs/KnowledgeGraphTab";
import { CodeIntelligenceTab } from "../components/tabs/CodeIntelligenceTab";
import { SecurityAgentTab } from "../components/tabs/SecurityAgentTab";
import { TestingAgentTab } from "../components/tabs/TestingAgentTab";
import { ChatSearchTab } from "../components/tabs/ChatSearchTab";

type TabKey =
  | "overview"
  | "architecture"
  | "graph"
  | "code"
  | "security"
  | "testing"
  | "chat";

interface TabMeta {
  key: TabKey;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

export default function RepositoryDetailPage() {
  const { id } = useParams<{ id: string }>();

  // Data states
  const [repo, setRepo] = useState<Repository | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisOut | null>(null);
  const [architecture, setArchitecture] = useState<ArtifactOut | null>(null);
  const [findings, setFindings] = useState<FindingOut[]>([]);
  const [untested, setUntested] = useState<UntestedSymbolOut[]>([]);

  // Loading states
  const [loading, setLoading] = useState(true);
  const [archLoading, setArchLoading] = useState(false);
  const [untestedLoading, setUntestedLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Active navigation tab
  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  // Load all repository data
  const loadRepoData = useCallback(async () => {
    if (!id) return;
    try {
      setError(null);
      const [repoData, analysisData] = await Promise.all([
        getRepository(id).catch(() => null),
        getLatestAnalysis(id).catch(() => null),
      ]);

      if (!repoData) {
        setError("Repository not found or failed to load.");
        setLoading(false);
        return;
      }

      setRepo(repoData);
      setAnalysis(analysisData);
      setLoading(false);

      // Async fetch secondary artifacts
      setArchLoading(true);
      getArchitecture(id)
        .then((arch) => setArchitecture(arch))
        .catch(() => setArchitecture(null))
        .finally(() => setArchLoading(false));

      getFindings(id)
        .then((f) => setFindings(f))
        .catch(() => setFindings([]));

      setUntestedLoading(true);
      getUntestedSymbols(id)
        .then((u) => setUntested(u))
        .catch(() => setUntested([]))
        .finally(() => setUntestedLoading(false));
    } catch (err: any) {
      setError(err?.message || "Failed to load repository details");
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadRepoData();
  }, [loadRepoData]);

  // Security scan trigger
  const handleTriggerSecurityScan = async () => {
    if (!id || scanning) return;
    setScanning(true);
    try {
      await runSecurityScan(id);
      const refreshedFindings = await getFindings(id);
      setFindings(refreshedFindings);
    } catch {
      /* handle or alert */
    } finally {
      setScanning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <Loader2 className="w-9 h-9 text-indigo-400 animate-spin" />
        <p className="text-sm text-slate-400">Loading codebase intelligence...</p>
      </div>
    );
  }

  if (error || !repo) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-4">
        <AlertCircle className="w-10 h-10 text-red-400" />
        <p className="text-sm text-red-400">{error || "Repository not found"}</p>
        <Link
          to="/"
          className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Repositories
        </Link>
      </div>
    );
  }

  const langColors: Record<string, string> = {
    Python: "bg-sky-500",
    TypeScript: "bg-blue-500",
    JavaScript: "bg-yellow-500",
    Go: "bg-cyan-500",
    Rust: "bg-orange-500",
    Java: "bg-red-500",
  };
  const langDot = langColors[repo.primary_language ?? ""] ?? "bg-slate-500";

  const tabs: TabMeta[] = [
    { key: "overview", label: "Overview", icon: <LayoutDashboard className="w-4 h-4" /> },
    { key: "architecture", label: "Architecture", icon: <FolderTree className="w-4 h-4" /> },
    { key: "graph", label: "Knowledge Graph", icon: <Network className="w-4 h-4" /> },
    { key: "code", label: "Code Intel", icon: <Code2 className="w-4 h-4" /> },
    {
      key: "security",
      label: "Security",
      icon: <Shield className="w-4 h-4" />,
      badge: findings.length > 0 ? findings.length : undefined,
    },
    {
      key: "testing",
      label: "Testing",
      icon: <TestTube2 className="w-4 h-4" />,
      badge: untested.length > 0 ? untested.length : undefined,
    },
    { key: "chat", label: "AI Chat & Search", icon: <MessageSquare className="w-4 h-4" /> },
  ];

  function renderTab() {
    if (!id || !repo) return null;
    switch (activeTab) {
      case "overview":
        return (
          <OverviewTab
            repository={repo}
            analysis={analysis}
            findings={findings}
            untested={untested}
            onSelectTab={(tabKey) => {
              if (tabKey === "code-intelligence" || tabKey === "code") setActiveTab("code");
              else if (tabKey === "knowledge-graph" || tabKey === "graph") setActiveTab("graph");
              else if (tabKey === "chat-search" || tabKey === "chat") setActiveTab("chat");
              else if (tabKey === "architecture") setActiveTab("architecture");
              else if (tabKey === "security") setActiveTab("security");
              else if (tabKey === "testing") setActiveTab("testing");
              else setActiveTab("overview");
            }}
          />
        );
      case "architecture":
        return <ArchitectureTab architecture={architecture} loading={archLoading} />;
      case "graph":
        return <KnowledgeGraphTab repository={repo} analysis={analysis} />;
      case "code":
        return <CodeIntelligenceTab analysis={analysis} loading={loading} />;
      case "security":
        return (
          <SecurityAgentTab
            repositoryId={id}
            findings={findings}
            onTriggerScan={handleTriggerSecurityScan}
            scanning={scanning}
          />
        );
      case "testing":
        return (
          <TestingAgentTab
            repositoryId={id}
            untested={untested}
            loading={untestedLoading}
          />
        );
      case "chat":
        return <ChatSearchTab repositoryId={id} />;
      default:
        return null;
    }
  }

  const analysisDate =
    analysis?.completed_at || analysis?.started_at || analysis?.created_at;

  return (
    <div className="min-h-screen pb-16">
      {/* Repository Header */}
      <div className="border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600/20 to-violet-600/20 border border-indigo-500/30 flex items-center justify-center shadow-lg shadow-indigo-500/10">
                <GitBranch className="w-6 h-6 text-indigo-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <Link
                    to="/"
                    className="text-xs text-slate-500 hover:text-slate-300 transition"
                  >
                    Repositories
                  </Link>
                  <span className="text-slate-700">/</span>
                  <span className="text-xs text-slate-400">{repo.owner}</span>
                  <span className="text-slate-700">/</span>
                  <span className="text-sm font-bold text-white tracking-wide">
                    {repo.name}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400">
                  {repo.primary_language && (
                    <span className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${langDot}`} />
                      {repo.primary_language}
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <FileCode2 className="w-3 h-3 text-slate-500" />
                    {repo.file_count.toLocaleString()} files
                  </span>
                  {repo.default_branch && (
                    <span className="flex items-center gap-1">
                      <GitBranch className="w-3 h-3 text-slate-500" />
                      {repo.default_branch}
                    </span>
                  )}
                  {analysisDate && (
                    <span className="flex items-center gap-1 text-emerald-400">
                      <Clock className="w-3 h-3" />
                      Analyzed {new Date(analysisDate).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <a
                href={repo.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 transition shadow-sm"
              >
                <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                <span>GitHub</span>
              </a>
              <button
                onClick={loadRepoData}
                className="p-2 rounded-lg bg-slate-900/80 border border-slate-700/80 text-slate-400 hover:text-white hover:border-slate-600 transition shadow-sm"
                title="Refresh codebase data"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-slate-800 bg-slate-900/40 backdrop-blur-sm sticky top-16 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex gap-1 overflow-x-auto py-2.5 scrollbar-none -mb-px">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all duration-200 ${
                    isActive
                      ? "bg-slate-800/90 text-white shadow-sm border border-slate-700/60"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                  }`}
                >
                  {tab.icon}
                  <span>{tab.label}</span>
                  {tab.badge !== undefined && tab.badge > 0 && (
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                        tab.key === "security"
                          ? "bg-red-500/20 text-red-400 border border-red-500/30"
                          : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                      }`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>

      {/* Tab Body */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        {renderTab()}
      </main>
    </div>
  );
}
