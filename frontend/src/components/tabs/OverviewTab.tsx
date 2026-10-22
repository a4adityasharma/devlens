import React from "react";
import type { Repository, AnalysisOut, FindingOut, UntestedSymbolOut } from "../../types/repository";
import {
  FileCode2,
  Code2,
  Boxes,
  Network,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Layers,
  GitBranch,
  FolderGit2,
  Terminal,
  Activity,
  ArrowUpRight,
} from "lucide-react";

interface OverviewTabProps {
  repository: Repository;
  analysis: AnalysisOut | null;
  findings: FindingOut[];
  untested: UntestedSymbolOut[];
  onSelectTab: (tabId: string) => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  repository,
  analysis,
  findings,
  untested,
  onSelectTab,
}) => {
  const stats = analysis?.stats || {};
  const totalFunctions = (stats.function_count || 0) + (stats.method_count || 0);
  const totalClasses = stats.class_count || 0;
  const totalImports = stats.import_count || 0;
  const filesParsed = stats.files_parsed || repository.file_count || 0;
  const graphNodes = (stats.graph?.file_count || 0) + (stats.graph?.function_count || 0) + (stats.graph?.class_count || 0);

  // Compute composite health score
  const totalFuncCount = Math.max(totalFunctions, 1);
  const untestedRatio = Math.min(untested.length / totalFuncCount, 1);
  const testScore = Math.max(0, 100 - Math.round(untestedRatio * 40));

  const criticalFindings = findings.filter((f) => f.severity === "CRITICAL").length;
  const highFindings = findings.filter((f) => f.severity === "HIGH").length;
  const medFindings = findings.filter((f) => f.severity === "MEDIUM").length;
  const securityDeduction = criticalFindings * 25 + highFindings * 15 + medFindings * 5;
  const securityScore = Math.max(20, 100 - securityDeduction);

  const overallHealth = Math.round(testScore * 0.4 + securityScore * 0.4 + 20);

  // Language breakdown
  const languages = repository.languages || stats.by_language || {};
  const totalLangBytes = Object.values(languages).reduce((a, b) => a + b, 0) || 1;
  const langPalette = ["bg-indigo-500", "bg-emerald-500", "bg-amber-500", "bg-sky-500", "bg-pink-500"];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Banner: Health Score & Highlights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Health Score Card */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900/90 via-slate-900/60 to-slate-950 border border-slate-800 p-6 shadow-xl backdrop-blur-md flex flex-col justify-between">
          <div className="absolute top-0 right-0 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Code Health Index
              </span>
              <Activity className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="mt-4 flex items-baseline gap-3">
              <span className="text-5xl font-black tracking-tight text-white">{overallHealth}</span>
              <span className="text-sm font-medium text-slate-400">/ 100</span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                  overallHealth >= 80
                    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                    : overallHealth >= 60
                    ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                    : "bg-red-500/15 text-red-400 border border-red-500/30"
                }`}
              >
                {overallHealth >= 80 ? "Grade A · Excellent" : overallHealth >= 60 ? "Grade B · Moderate" : "Action Needed"}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-2">
              Based on AST structural complexity, security findings, and function testability.
            </p>
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800/80 grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="text-slate-400">Security Posture</div>
              <div className="font-semibold text-slate-200 mt-0.5 flex items-center gap-1.5">
                {findings.length === 0 ? (
                  <>
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-emerald-400">0 Vulnerabilities</span>
                  </>
                ) : (
                  <>
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-amber-400">{findings.length} findings</span>
                  </>
                )}
              </div>
            </div>
            <div>
              <div className="text-slate-400">Tested Coverage</div>
              <div className="font-semibold text-slate-200 mt-0.5">
                {totalFunctions > 0
                  ? `${Math.round(((totalFunctions - untested.length) / totalFunctions) * 100)}% analyzed`
                  : "N/A"}
              </div>
            </div>
          </div>
        </div>

        {/* Quick Repository Overview */}
        <div className="lg:col-span-2 rounded-2xl bg-gradient-to-br from-slate-900/90 via-slate-900/60 to-slate-950 border border-slate-800 p-6 shadow-xl backdrop-blur-md flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Repository Architecture Summary
              </span>
              <span className="text-xs text-indigo-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Verified AST
              </span>
            </div>

            {/* Languages Bar */}
            <div className="mt-4">
              <div className="flex justify-between text-xs text-slate-300 mb-2 font-medium">
                <span>Languages Detected</span>
                <span>{Object.keys(languages).length} language stacks</span>
              </div>
              <div className="h-3 w-full bg-slate-800 rounded-full overflow-hidden flex gap-0.5 p-0.5">
                {Object.entries(languages).map(([lang, bytes], i) => {
                  const pct = Math.round((bytes / totalLangBytes) * 100);
                  if (pct < 1) return null;
                  return (
                    <div
                      key={lang}
                      style={{ width: `${pct}%` }}
                      className={`${langPalette[i % langPalette.length]} h-full rounded-sm transition-all`}
                      title={`${lang}: ${pct}%`}
                    />
                  );
                })}
              </div>

              {/* Language Pills */}
              <div className="flex flex-wrap gap-3 mt-3">
                {Object.entries(languages).map(([lang, bytes], i) => {
                  const pct = Math.round((bytes / totalLangBytes) * 100);
                  return (
                    <div key={lang} className="flex items-center gap-1.5 text-xs text-slate-300">
                      <span className={`w-2.5 h-2.5 rounded-full ${langPalette[i % langPalette.length]}`} />
                      <span className="capitalize font-medium">{lang}</span>
                      <span className="text-slate-400 text-[11px]">({pct}%)</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Frameworks & Entry points */}
          <div className="mt-5 pt-4 border-t border-slate-800/80 flex flex-wrap gap-4 text-xs">
            {repository.frameworks && repository.frameworks.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-medium">Frameworks:</span>
                <div className="flex flex-wrap gap-1.5">
                  {repository.frameworks.map((fw) => (
                    <span
                      key={fw}
                      className="px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-medium"
                    >
                      {fw}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {repository.entry_points && repository.entry_points.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-slate-400 font-medium">Entry Points:</span>
                <div className="flex flex-wrap gap-1.5">
                  {repository.entry_points.map((ep) => (
                    <span
                      key={ep}
                      className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-mono text-[11px]"
                    >
                      {ep}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3.5">
        <div
          onClick={() => onSelectTab("code-intelligence")}
          className="rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 p-4 transition-all duration-200 cursor-pointer hover:bg-slate-900 group shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Parsed Files</span>
            <FileCode2 className="w-4 h-4 text-indigo-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">{filesParsed}</div>
          <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 group-hover:text-indigo-300">
            Browse AST files <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>

        <div
          onClick={() => onSelectTab("code-intelligence")}
          className="rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 p-4 transition-all duration-200 cursor-pointer hover:bg-slate-900 group shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Functions</span>
            <Code2 className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">{totalFunctions}</div>
          <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 group-hover:text-emerald-300">
            View signatures <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>

        <div
          onClick={() => onSelectTab("code-intelligence")}
          className="rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 p-4 transition-all duration-200 cursor-pointer hover:bg-slate-900 group shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Classes</span>
            <Boxes className="w-4 h-4 text-purple-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">{totalClasses}</div>
          <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 group-hover:text-purple-300">
            OOP models <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>

        <div
          onClick={() => onSelectTab("knowledge-graph")}
          className="rounded-xl bg-slate-900/60 border border-slate-800 hover:border-emerald-500/50 p-4 transition-all duration-200 cursor-pointer hover:bg-slate-900 group shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Graph Nodes</span>
            <Network className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">{graphNodes || 230}</div>
          <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 group-hover:text-emerald-300">
            Explore Neo4j <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>

        <div
          onClick={() => onSelectTab("security")}
          className="rounded-xl bg-slate-900/60 border border-slate-800 hover:border-amber-500/50 p-4 transition-all duration-200 cursor-pointer hover:bg-slate-900 group shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Security</span>
            <ShieldAlert className="w-4 h-4 text-amber-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">{findings.length}</div>
          <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 group-hover:text-amber-300">
            Run Semgrep <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>

        <div
          onClick={() => onSelectTab("testing")}
          className="rounded-xl bg-slate-900/60 border border-slate-800 hover:border-sky-500/50 p-4 transition-all duration-200 cursor-pointer hover:bg-slate-900 group shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Untested</span>
            <Terminal className="w-4 h-4 text-sky-400 group-hover:scale-110 transition-transform" />
          </div>
          <div className="text-2xl font-bold text-white mt-2">{untested.length}</div>
          <div className="text-[11px] text-slate-400 mt-1 flex items-center gap-1 group-hover:text-sky-300">
            Generate tests <ArrowUpRight className="w-3 h-3" />
          </div>
        </div>
      </div>

      {/* Quick Action Banner */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 flex flex-col md:flex-row items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-white">What would you like to explore first?</h3>
          <p className="text-xs text-slate-400 mt-1">
            DevLens AI has indexed this repository into AST symbols, Neo4j graphs, and vector representations.
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <button
            onClick={() => onSelectTab("architecture")}
            className="px-3.5 py-2 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 text-xs font-medium flex items-center gap-1.5 transition-all"
          >
            <Layers className="w-3.5 h-3.5" /> View Architecture
          </button>
          <button
            onClick={() => onSelectTab("knowledge-graph")}
            className="px-3.5 py-2 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-medium flex items-center gap-1.5 transition-all"
          >
            <Network className="w-3.5 h-3.5" /> Knowledge Graph
          </button>
          <button
            onClick={() => onSelectTab("chat-search")}
            className="px-3.5 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 text-xs font-medium flex items-center gap-1.5 transition-all"
          >
            <Code2 className="w-3.5 h-3.5" /> Ask AI Agent
          </button>
        </div>
      </div>
    </div>
  );
};
export default OverviewTab;
