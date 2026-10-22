import React, { useState } from "react";
import type { UntestedSymbolOut, GenerateTestResponse } from "../../types/repository";
import { generateTest } from "../../services/api";
import {
  Terminal,
  CheckCircle2,
  XCircle,
  Play,
  Copy,
  Check,
  AlertCircle,
  FileCode,
  ShieldCheck,
  Sparkles,
  ArrowRight,
  Code2,
} from "lucide-react";

interface TestingAgentTabProps {
  repositoryId: string;
  untested: UntestedSymbolOut[];
  loading: boolean;
}

export const TestingAgentTab: React.FC<TestingAgentTabProps> = ({ repositoryId, untested, loading }) => {
  const [selectedSymbol, setSelectedSymbol] = useState<UntestedSymbolOut | null>(null);
  const [generating, setGenerating] = useState(false);
  const [testResult, setTestResult] = useState<GenerateTestResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState(false);

  async function handleGenerate(sym: UntestedSymbolOut) {
    setSelectedSymbol(sym);
    setGenerating(true);
    setErrorMessage(null);
    setTestResult(null);

    try {
      const res = await generateTest(repositoryId, sym.file, sym.name);
      setTestResult(res);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || "Failed to generate test";
      if (err?.response?.status === 503) {
        setErrorMessage(
          "LLM is not configured (ANTHROPIC_API_KEY unset). Add your key to .env to enable live unit test synthesis with Claude."
        );
      } else {
        setErrorMessage(detail);
      }
    } finally {
      setGenerating(false);
    }
  }

  function handleCopy() {
    if (!testResult?.generated_code) return;
    navigator.clipboard.writeText(testResult.generated_code);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-slate-400">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3" />
        <p className="text-sm">Analyzing test coverage gap...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-xl border border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Terminal className="w-5 h-5 text-sky-400" /> Testing Agent & Coverage Gap Analyzer
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Identifies functions without direct test calls and synthesizes Stage A validated test suites.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs px-2.5 py-1 rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20 font-semibold">
            {untested.length} Untested Candidates
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Untested Functions List */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-800 bg-slate-950 p-4 flex flex-col h-[560px]">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs font-semibold text-slate-300">
            <span>Untested Functions / Methods</span>
            <span className="text-slate-500 font-mono text-[11px]">{untested.length} items</span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 py-2 pr-1">
            {untested.length === 0 ? (
              <div className="text-center py-16 text-slate-500 text-xs">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
                All identified functions have direct test coverage!
              </div>
            ) : (
              untested.map((sym, idx) => {
                const isSelected = selectedSymbol?.name === sym.name && selectedSymbol?.file === sym.file;
                return (
                  <div
                    key={`${sym.file}-${sym.name}-${idx}`}
                    onClick={() => handleGenerate(sym)}
                    className={`p-3 rounded-xl border text-xs cursor-pointer transition ${
                      isSelected
                        ? "bg-sky-950/40 border-sky-500/50 shadow-sm"
                        : "bg-slate-900/40 border-slate-800 hover:border-slate-700 hover:bg-slate-900"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-white truncate max-w-[200px]" title={sym.name}>
                        {sym.name}()
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 uppercase">
                        {sym.type}
                      </span>
                    </div>

                    <div className="text-[11px] font-mono text-slate-500 truncate mt-1">
                      {sym.file}:L{sym.line_start}
                    </div>

                    <div className="mt-2 flex items-center justify-end text-[11px] text-sky-400 font-medium gap-1">
                      <span>Generate Test</span>
                      <ArrowRight className="w-3 h-3" />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Generator Output & Validation Panel */}
        <div className="lg:col-span-3 rounded-2xl border border-slate-800 bg-slate-950 p-5 flex flex-col justify-between min-h-[560px]">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Code2 className="w-4 h-4 text-indigo-400" />
                <span className="text-sm font-semibold text-white">
                  {selectedSymbol ? `Generated Test for ${selectedSymbol.name}()` : "Select a function to generate test"}
                </span>
              </div>

              {testResult && (
                <button
                  onClick={handleCopy}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1 transition"
                >
                  {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedCode ? "Copied" : "Copy Code"}
                </button>
              )}
            </div>

            {generating ? (
              <div className="flex flex-col items-center justify-center py-24 text-slate-400">
                <div className="w-8 h-8 border-2 border-sky-500 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-sm font-medium text-slate-200">Synthesizing Unit Test with LLM...</p>
                <p className="text-xs text-slate-500 mt-1">
                  Target: {selectedSymbol?.name} ({selectedSymbol?.file})
                </p>
              </div>
            ) : errorMessage ? (
              <div className="my-6 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 space-y-2">
                <div className="flex items-center gap-2 font-semibold text-amber-200">
                  <AlertCircle className="w-4 h-4 text-amber-400" /> Generation Notice
                </div>
                <p className="leading-relaxed">{errorMessage}</p>
              </div>
            ) : testResult ? (
              <div className="mt-4 space-y-4">
                {/* Stage A Validation Badges */}
                <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 space-y-2">
                  <div className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" /> Stage A Static Safety Verification:
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-[11px]">
                    <div className="flex items-center gap-1.5 text-slate-300">
                      {testResult.validation?.valid ?? testResult.validation?.syntax_valid ?? testResult.validation?.passes ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                      )}
                      <span>AST Syntax Valid</span>
                    </div>

                    <div className="flex items-center gap-1.5 text-slate-300">
                      {testResult.validation?.valid ?? testResult.validation?.references_symbol ?? testResult.validation?.passes ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                      )}
                      <span>Targets {testResult.symbol}()</span>
                    </div>

                    <div className="flex items-center gap-1.5 text-slate-300">
                      {testResult.validation?.valid ?? testResult.validation?.has_assertions ?? testResult.validation?.passes ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                      )}
                      <span>Static Verified</span>
                    </div>
                  </div>

                  {testResult.validation?.reasons && testResult.validation.reasons.length > 0 && (
                    <div className="text-[11px] text-red-400 mt-1">
                      Issues: {testResult.validation.reasons.join(", ")}
                    </div>
                  )}
                </div>

                {/* Code Viewer */}
                <div className="rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
                  <div className="px-3 py-1.5 bg-slate-900/60 border-b border-slate-800 text-[11px] font-mono text-slate-400 flex justify-between">
                    <span>Generated Test File</span>
                    <span className="text-indigo-400">Not Executed (Static Validated)</span>
                  </div>
                  <pre className="p-4 text-xs font-mono text-emerald-300 max-h-72 overflow-y-auto overflow-x-auto leading-relaxed">
                    {testResult.generated_code}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="text-center py-28 text-slate-500 text-xs">
                <FileCode className="w-10 h-10 mx-auto mb-3 text-slate-600" />
                Select any untested function on the left to synthesize a test suite.
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-slate-800 text-[11px] text-slate-500">
            <span className="font-semibold text-slate-400">Security Boundary: </span>
            Generated tests are never executed on the host container. Stage A verification guarantees syntactic validity
            without arbitrary code execution risks.
          </div>
        </div>
      </div>
    </div>
  );
};
export default TestingAgentTab;
