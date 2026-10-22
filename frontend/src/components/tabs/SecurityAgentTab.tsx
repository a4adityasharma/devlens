import React, { useState } from "react";
import type { FindingOut } from "../../types/repository";
import {
  ShieldAlert,
  ShieldCheck,
  Play,
  CheckCircle2,
  AlertTriangle,
  Info,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  FileCode2,
  Sparkles,
} from "lucide-react";

interface SecurityAgentTabProps {
  repositoryId: string;
  findings: FindingOut[];
  onTriggerScan: () => Promise<void>;
  scanning: boolean;
}

export const SecurityAgentTab: React.FC<SecurityAgentTabProps> = ({
  repositoryId,
  findings,
  onTriggerScan,
  scanning,
}) => {
  const [selectedSeverity, setSelectedSeverity] = useState<string>("all");
  const [expandedFinding, setExpandedFinding] = useState<string | null>(null);

  const criticalCount = findings.filter((f) => f.severity === "CRITICAL").length;
  const highCount = findings.filter((f) => f.severity === "HIGH").length;
  const medCount = findings.filter((f) => f.severity === "MEDIUM").length;
  const lowCount = findings.filter((f) => f.severity === "LOW").length;

  const filteredFindings = findings.filter((f) => {
    if (selectedSeverity === "all") return true;
    return f.severity === selectedSeverity;
  });

  const severityBadgeColors: Record<string, string> = {
    CRITICAL: "bg-red-500/15 text-red-400 border-red-500/30",
    HIGH: "bg-orange-500/15 text-orange-400 border-orange-500/30",
    MEDIUM: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    LOW: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header controls & trigger */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-xl border border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-400" /> Semgrep Security Audit Agent
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Static analysis ruleset checking for SQL injection, command execution, hardcoded keys, and tainted inputs.
          </p>
        </div>

        <button
          onClick={onTriggerScan}
          disabled={scanning}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white flex items-center gap-2 transition disabled:opacity-50 shadow-lg shadow-amber-500/20"
        >
          {scanning ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>Auditing codebase...</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Run On-Demand Audit</span>
            </>
          )}
        </button>
      </div>

      {/* Severity Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <div
          onClick={() => setSelectedSeverity("all")}
          className={`rounded-xl border p-4 cursor-pointer transition ${
            selectedSeverity === "all"
              ? "bg-slate-900 border-indigo-500/50 shadow-sm"
              : "bg-slate-900/40 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="text-xs text-slate-400 font-medium">Total Findings</div>
          <div className="text-2xl font-bold text-white mt-1">{findings.length}</div>
        </div>

        <div
          onClick={() => setSelectedSeverity("HIGH")}
          className={`rounded-xl border p-4 cursor-pointer transition ${
            selectedSeverity === "HIGH"
              ? "bg-slate-900 border-orange-500/50 shadow-sm"
              : "bg-slate-900/40 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="text-xs text-orange-400 font-medium flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> High Severity
          </div>
          <div className="text-2xl font-bold text-orange-400 mt-1">{highCount}</div>
        </div>

        <div
          onClick={() => setSelectedSeverity("MEDIUM")}
          className={`rounded-xl border p-4 cursor-pointer transition ${
            selectedSeverity === "MEDIUM"
              ? "bg-slate-900 border-amber-500/50 shadow-sm"
              : "bg-slate-900/40 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="text-xs text-amber-400 font-medium flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Medium
          </div>
          <div className="text-2xl font-bold text-amber-400 mt-1">{medCount}</div>
        </div>

        <div
          onClick={() => setSelectedSeverity("LOW")}
          className={`rounded-xl border p-4 cursor-pointer transition ${
            selectedSeverity === "LOW"
              ? "bg-slate-900 border-blue-500/50 shadow-sm"
              : "bg-slate-900/40 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="text-xs text-blue-400 font-medium flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5" /> Low / Advisory
          </div>
          <div className="text-2xl font-bold text-blue-400 mt-1">{lowCount}</div>
        </div>
      </div>

      {/* Findings List */}
      <div className="space-y-3">
        {filteredFindings.length === 0 ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
            <ShieldCheck className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-white">No Vulnerabilities Detected</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
              The Semgrep ruleset scanned the codebase and found zero matching patterns for SQL injection, command
              execution, or exposed credentials.
            </p>
          </div>
        ) : (
          filteredFindings.map((finding) => {
            const isExpanded = expandedFinding === finding.id;
            return (
              <div
                key={finding.id}
                className="rounded-xl border border-slate-800 bg-slate-900/70 hover:border-slate-700 overflow-hidden transition"
              >
                <div
                  onClick={() => setExpandedFinding(isExpanded ? null : finding.id)}
                  className="p-4 flex items-center justify-between cursor-pointer select-none"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-md border mt-0.5 uppercase ${
                        severityBadgeColors[finding.severity || "LOW"]
                      }`}
                    >
                      {finding.severity || "LOW"}
                    </span>
                    <div>
                      <div className="font-semibold text-sm text-white">{finding.title}</div>
                      <div className="text-xs font-mono text-slate-400 mt-0.5 flex items-center gap-2">
                        <span>{finding.file_path}</span>
                        {finding.line_start && (
                          <span className="text-amber-400">
                            :L{finding.line_start}
                            {finding.line_end ? `-${finding.line_end}` : ""}
                          </span>
                        )}
                        {finding.category && (
                          <span className="text-slate-500 font-sans">• {finding.category}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500 hidden sm:inline">
                      {isExpanded ? "Collapse" : "Details"}
                    </span>
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div className="px-4 pb-4 pt-2 border-t border-slate-800/80 bg-slate-950/60 text-xs space-y-3">
                    {finding.description && (
                      <div>
                        <div className="font-semibold text-slate-300 mb-1">Vulnerability Description:</div>
                        <p className="text-slate-400 leading-relaxed">{finding.description}</p>
                      </div>
                    )}

                    {finding.recommendation && (
                      <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                        <div className="font-semibold text-emerald-300 flex items-center gap-1.5 mb-1">
                          <Sparkles className="w-3.5 h-3.5" /> Remediation Guidance:
                        </div>
                        <p className="text-emerald-200/90 leading-relaxed font-mono text-[11px]">
                          {finding.recommendation}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
export default SecurityAgentTab;
