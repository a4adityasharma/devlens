import React, { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import type { ArtifactOut } from "../../types/repository";
import {
  Layers,
  Copy,
  Check,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Box,
  ArrowRight,
  Code,
  Network,
  CheckCircle2,
  FileCode2,
} from "lucide-react";

interface ArchitectureTabProps {
  architecture: ArtifactOut | null;
  loading: boolean;
}

export const ArchitectureTab: React.FC<ArchitectureTabProps> = ({ architecture, loading }) => {
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [showRaw, setShowRaw] = useState(false);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      themeVariables: {
        darkMode: true,
        background: "#020617",
        primaryColor: "#4f46e5",
        primaryTextColor: "#f8fafc",
        primaryBorderColor: "#6366f1",
        lineColor: "#94a3b8",
        secondaryColor: "#059669",
        tertiaryColor: "#0f172a",
      },
      flowchart: {
        curve: "basis",
        htmlLabels: true,
      },
    });
  }, []);

  useEffect(() => {
    if (!architecture?.content) return;

    const uniqueId = `mermaid_diag_${Math.floor(Math.random() * 1000000)}`;
    setRenderError(null);

    // Clean any trailing or leading invalid syntax
    const cleanContent = architecture.content.trim();

    mermaid
      .render(uniqueId, cleanContent)
      .then(({ svg }) => {
        setSvgContent(svg);
      })
      .catch((err) => {
        console.warn("Mermaid rendering warning:", err);
        setRenderError("Visual diagram rendered using structural architecture cards below.");
      });
  }, [architecture?.content]);

  function handleCopy() {
    if (!architecture?.content) return;
    navigator.clipboard.writeText(architecture.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-slate-400">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3" />
        <p className="text-sm">Inferring architectural layers & call dependencies...</p>
      </div>
    );
  }

  if (!architecture) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center text-slate-400">
        <Layers className="w-10 h-10 mx-auto mb-3 text-slate-500" />
        <h3 className="text-base font-semibold text-white">No Architecture Diagram Available</h3>
        <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
          The Architecture Agent generates layer diagrams automatically when a repository finishes analysis.
        </p>
      </div>
    );
  }

  const layers: Record<string, any> = architecture.extra?.layers || {};
  const edges: any[] = architecture.extra?.edges || [];
  const layerKeys = Object.keys(layers);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" /> Layer Hierarchy & Call Topology
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Auto-inferred from Tree-sitter AST calls & directory structure ({layerKeys.length} layers,{" "}
            {edges.length} cross-layer calls)
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Zoom controls */}
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-1">
            <button
              onClick={() => setZoom((z) => Math.max(0.6, z - 0.15))}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="px-2 text-xs font-mono text-slate-300">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom((z) => Math.min(2, z + 0.15))}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setZoom(1)}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition ml-1 border-l border-slate-800"
              title="Reset zoom"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={() => setShowRaw(!showRaw)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition ${
              showRaw
                ? "bg-indigo-600 text-white border-indigo-500"
                : "bg-slate-900 text-slate-300 border-slate-700 hover:bg-slate-800"
            }`}
          >
            <Code className="w-3.5 h-3.5" /> {showRaw ? "Visual Diagram" : "Mermaid Code"}
          </button>

          <button
            onClick={handleCopy}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700 flex items-center gap-1.5 transition"
            title="Copy Mermaid Markdown"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? "Copied" : "Copy Code"}
          </button>
        </div>
      </div>

      {/* Main Diagram Canvas */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950 p-6 min-h-[380px] flex items-center justify-center overflow-auto shadow-inner relative">
        {showRaw ? (
          <pre className="text-xs font-mono text-indigo-300 p-4 bg-slate-900/90 rounded-xl border border-slate-800 w-full overflow-x-auto">
            {architecture.content}
          </pre>
        ) : svgContent ? (
          <div
            ref={containerRef}
            style={{ transform: `scale(${zoom})`, transformOrigin: "center center" }}
            className="transition-transform duration-150 max-w-full flex items-center justify-center [&>svg]:max-w-full [&>svg]:h-auto"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        ) : (
          <div className="flex flex-col items-center gap-3 text-sm text-slate-400 p-8 text-center">
            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p>Rendering architectural diagram...</p>
            {renderError && <p className="text-xs text-amber-400">{renderError}</p>}
          </div>
        )}
      </div>

      {/* Interactive Layer Cards Breakdown */}
      {layerKeys.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Box className="w-4 h-4 text-indigo-400" /> Architectural Layers ({layerKeys.length})
            </h3>
            <span className="text-xs text-slate-400">Classified from directory hierarchy</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3.5">
            {Object.entries(layers).map(([layerName, layerInfo]: [string, any], idx) => {
              const fileCount =
                typeof layerInfo === "number"
                  ? layerInfo
                  : typeof layerInfo === "object" && layerInfo?.file_count !== undefined
                  ? layerInfo.file_count
                  : Array.isArray(layerInfo)
                  ? layerInfo.length
                  : 1;

              const layerColors = [
                "border-indigo-500/30 bg-indigo-500/5",
                "border-violet-500/30 bg-violet-500/5",
                "border-sky-500/30 bg-sky-500/5",
                "border-emerald-500/30 bg-emerald-500/5",
                "border-amber-500/30 bg-amber-500/5",
                "border-pink-500/30 bg-pink-500/5",
              ];
              const colorClass = layerColors[idx % layerColors.length];

              return (
                <div
                  key={layerName}
                  className={`rounded-xl border p-4 transition-all duration-200 hover:scale-[1.01] ${colorClass}`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-indigo-400" />
                      <span className="font-bold text-sm text-white tracking-wide">{layerName}</span>
                    </div>
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-900 border border-slate-700 text-slate-300 font-mono">
                      {fileCount} {fileCount === 1 ? "file" : "files"}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Layer node index: L{idx} in Mermaid graph
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Cross-Layer Dependencies Table */}
      {edges.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Network className="w-4 h-4 text-emerald-400" /> Cross-Layer Call Relationships
            </h3>
            <span className="text-xs text-slate-400">{edges.length} cross-layer call paths</span>
          </div>

          <div className="overflow-x-auto max-h-64">
            <table className="w-full text-xs text-left text-slate-300">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0">
                <tr>
                  <th className="px-3 py-2">Caller Layer</th>
                  <th className="px-3 py-2">Direction</th>
                  <th className="px-3 py-2">Callee Layer</th>
                  <th className="px-3 py-2">Call Frequency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {edges.map((edge: any, idx: number) => {
                  const from = edge.from || edge.from_layer || "Source";
                  const to = edge.to || edge.to_layer || "Target";
                  const count = edge.count || 1;
                  return (
                    <tr key={idx} className="hover:bg-slate-800/40 transition">
                      <td className="px-3 py-2.5 font-semibold text-indigo-300">{from}</td>
                      <td className="px-3 py-2.5 text-slate-500">
                        <span className="inline-flex items-center gap-1 text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-[10px]">
                          calls <ArrowRight className="w-3 h-3 text-indigo-400" />
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-semibold text-emerald-300">{to}</td>
                      <td className="px-3 py-2.5 font-mono text-purple-300">
                        <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                          {count} {count === 1 ? "call" : "calls"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
export default ArchitectureTab;
