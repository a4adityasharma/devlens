import React, { useState, useMemo } from "react";
import type { AnalysisOut, SymbolItem } from "../../types/repository";
import {
  Code2,
  Boxes,
  FileCode,
  Search,
  Filter,
  Copy,
  Check,
  ChevronDown,
  Terminal,
  ArrowUpRight,
  Brackets,
} from "lucide-react";

interface CodeIntelligenceTabProps {
  analysis: AnalysisOut | null;
  loading: boolean;
}

export const CodeIntelligenceTab: React.FC<CodeIntelligenceTabProps> = ({ analysis, loading }) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [copiedSymbol, setCopiedSymbol] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const symbols = useMemo(() => analysis?.symbols || [], [analysis]);

  // Unique types and file counts
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = { all: symbols.length };
    symbols.forEach((s) => {
      counts[s.type] = (counts[s.type] || 0) + 1;
    });
    return counts;
  }, [symbols]);

  // Filtered symbols
  const filteredSymbols = useMemo(() => {
    return symbols.filter((s) => {
      const matchesType = typeFilter === "all" || s.type === typeFilter;
      const matchesSearch =
        !searchTerm ||
        s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.file.toLowerCase().includes(searchTerm.toLowerCase());
      return matchesType && matchesSearch;
    });
  }, [symbols, typeFilter, searchTerm]);

  // Paginated symbols
  const paginatedSymbols = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredSymbols.slice(start, start + pageSize);
  }, [filteredSymbols, page]);

  const totalPages = Math.ceil(filteredSymbols.length / pageSize) || 1;

  function handleCopy(text: string, id: string) {
    navigator.clipboard.writeText(text);
    setCopiedSymbol(id);
    setTimeout(() => setCopiedSymbol(null), 2000);
  }

  const badgeStyles: Record<string, string> = {
    function: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    method: "bg-teal-500/10 text-teal-400 border-teal-500/20",
    class: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    import: "bg-sky-500/10 text-sky-400 border-sky-500/20",
    call: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-16 text-slate-400">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3" />
        <p className="text-sm">Reading Tree-sitter AST symbol table...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header controls & stats */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Brackets className="w-5 h-5 text-indigo-400" /> Tree-sitter AST Code Intelligence
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Deterministic AST parser extracted {symbols.length} code symbols across all parsed source files.
          </p>
        </div>

        {/* Search Bar */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search functions, classes, files..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-950 border border-slate-700 rounded-lg text-slate-200 outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Type Filter Tabs */}
      <div className="flex flex-wrap gap-2">
        {["all", "function", "method", "class", "import", "call"].map((type) => {
          const count = typeCounts[type] || 0;
          const isActive = typeFilter === type;
          return (
            <button
              key={type}
              onClick={() => {
                setTypeFilter(type);
                setPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border flex items-center gap-1.5 transition capitalize ${
                isActive
                  ? "bg-indigo-600 text-white border-indigo-500 shadow-sm"
                  : "bg-slate-900/80 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <span>{type}</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                  isActive ? "bg-indigo-500 text-white" : "bg-slate-800 text-slate-400"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Symbol Table */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950 overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left text-slate-300">
            <thead className="bg-slate-900/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Symbol Name</th>
                <th className="px-4 py-3">Parent / Class</th>
                <th className="px-4 py-3">Parameters / Signature</th>
                <th className="px-4 py-3">File Location</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {paginatedSymbols.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-500">
                    No symbols match the current search & filters.
                  </td>
                </tr>
              ) : (
                paginatedSymbols.map((sym, idx) => {
                  const symId = `${sym.file}-${sym.name}-${idx}`;
                  return (
                    <tr key={symId} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-4 py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded-md border text-[11px] font-semibold uppercase ${
                            badgeStyles[sym.type] || "bg-slate-800 text-slate-300 border-slate-700"
                          }`}
                        >
                          {sym.type}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-bold text-white max-w-xs truncate" title={sym.name}>
                        {sym.name}
                      </td>
                      <td className="px-4 py-2.5 text-purple-300">{sym.parent || "—"}</td>
                      <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate" title={sym.parameters?.join(", ")}>
                        {sym.parameters && sym.parameters.length > 0 ? `(${sym.parameters.join(", ")})` : "()"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 max-w-sm truncate" title={`${sym.file}:${sym.line_start}`}>
                        <span className="text-slate-300">{sym.file}</span>
                        <span className="text-indigo-400 ml-1.5">
                          :L{sym.line_start}
                          {sym.line_end && sym.line_end !== sym.line_start ? `-${sym.line_end}` : ""}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          onClick={() => handleCopy(`${sym.file}:${sym.line_start} - ${sym.name}`, symId)}
                          className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition"
                          title="Copy file & symbol reference"
                        >
                          {copiedSymbol === symId ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination controls */}
        <div className="flex items-center justify-between px-4 py-3 bg-slate-900/60 border-t border-slate-800 text-xs text-slate-400">
          <div>
            Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, filteredSymbols.length)} of{" "}
            {filteredSymbols.length} symbols
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 transition"
            >
              Previous
            </button>
            <span className="font-mono text-slate-300">
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 transition"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
export default CodeIntelligenceTab;
