import React, { useEffect, useRef, useState, useMemo } from "react";
import type { Repository, AnalysisOut } from "../../types/repository";
import {
  Network,
  ExternalLink,
  Copy,
  Check,
  Search,
  Filter,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Compass,
  FileCode2,
  Code2,
  Boxes,
  Layers,
} from "lucide-react";

interface KnowledgeGraphTabProps {
  repository: Repository;
  analysis: AnalysisOut | null;
}

interface Node {
  id: string;
  name: string;
  type: "Repository" | "File" | "Function" | "Class" | "Module";
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  details?: Record<string, any>;
}

interface Edge {
  source: string;
  target: string;
  type: "CONTAINS" | "DEFINES" | "IMPORTS" | "CALLS";
}

const TYPE_COLORS: Record<string, string> = {
  Repository: "#6366f1", // indigo
  File: "#0ea5e9", // sky
  Function: "#10b981", // emerald
  Class: "#a855f7", // purple
  Module: "#f59e0b", // amber
};

export const KnowledgeGraphTab: React.FC<KnowledgeGraphTabProps> = ({ repository, analysis }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState<Record<string, boolean>>({
    Repository: true,
    File: true,
    Function: true,
    Class: true,
    Module: true,
  });
  const [copiedQuery, setCopiedQuery] = useState<string | null>(null);

  // Zoom and pan state
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const isDraggingCanvas = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const draggedNode = useRef<Node | null>(null);

  // Mutable nodes reference for silky 60fps simulation
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);

  // Build initial graph layout from AST symbols
  useEffect(() => {
    const nodesMap = new Map<string, Node>();
    const edgesList: Edge[] = [];

    // Root repository node
    const repoNode: Node = {
      id: "repo",
      name: repository.name,
      type: "Repository",
      x: 450,
      y: 300,
      vx: 0,
      vy: 0,
      radius: 22,
      color: TYPE_COLORS.Repository,
      details: { url: repository.url, owner: repository.owner },
    };
    nodesMap.set(repoNode.id, repoNode);

    const symbols = analysis?.symbols || [];
    const filesSet = new Set<string>();

    symbols.forEach((s) => {
      if (s.file) filesSet.add(s.file);
    });

    // Select files
    const fileList = Array.from(filesSet).slice(0, 24);
    fileList.forEach((file, idx) => {
      const fileId = `file-${file}`;
      const angle = (idx / Math.max(fileList.length, 1)) * 2 * Math.PI;
      const dist = 140 + (idx % 3) * 35;
      nodesMap.set(fileId, {
        id: fileId,
        name: file.split("/").pop() || file,
        type: "File",
        x: 450 + Math.cos(angle) * dist,
        y: 300 + Math.sin(angle) * dist,
        vx: 0,
        vy: 0,
        radius: 13,
        color: TYPE_COLORS.File,
        details: { path: file },
      });
      edgesList.push({ source: "repo", target: fileId, type: "CONTAINS" });
    });

    // Select key functions and classes
    const keySymbols = symbols
      .filter((s) => s.type === "function" || s.type === "class")
      .slice(0, 45);

    keySymbols.forEach((s, idx) => {
      const fileId = `file-${s.file}`;
      const symId = `sym-${s.name}-${idx}`;
      const fileNode = nodesMap.get(fileId);

      const angle = (idx / Math.max(keySymbols.length, 1)) * 2 * Math.PI;
      const dist = 55 + (idx % 4) * 15;
      const baseX = fileNode ? fileNode.x : 450;
      const baseY = fileNode ? fileNode.y : 300;

      const isClass = s.type === "class";
      nodesMap.set(symId, {
        id: symId,
        name: s.name,
        type: isClass ? "Class" : "Function",
        x: baseX + Math.cos(angle) * dist,
        y: baseY + Math.sin(angle) * dist,
        vx: 0,
        vy: 0,
        radius: isClass ? 10 : 8,
        color: isClass ? TYPE_COLORS.Class : TYPE_COLORS.Function,
        details: s,
      });

      if (fileNode) {
        edgesList.push({ source: fileId, target: symId, type: "DEFINES" });
      }
    });

    // Add function call edges
    const calls = symbols.filter((s) => s.type === "call").slice(0, 20);
    calls.forEach((c) => {
      const targetFn = keySymbols.find((s) => s.name === c.name);
      if (targetFn && c.parent) {
        const sourceSym = keySymbols.find((s) => s.name === c.parent);
        if (sourceSym) {
          edgesList.push({
            source: `sym-${sourceSym.name}-0`,
            target: `sym-${targetFn.name}-0`,
            type: "CALLS",
          });
        }
      }
    });

    // Run 120 iterations of spring relaxation to stabilize layout
    const allNodes = Array.from(nodesMap.values());
    for (let step = 0; step < 120; step++) {
      // Spring forces along edges
      edgesList.forEach((edge) => {
        const s = nodesMap.get(edge.source);
        const t = nodesMap.get(edge.target);
        if (!s || !t) return;

        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const desiredDist = edge.type === "CONTAINS" ? 130 : 60;
        const force = (dist - desiredDist) * 0.008;

        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (s.id !== "repo") {
          s.x += fx;
          s.y += fy;
        }
        t.x -= fx;
        t.y -= fy;
      });

      // Repulsion between nodes
      for (let i = 0; i < allNodes.length; i++) {
        for (let j = i + 1; j < allNodes.length; j++) {
          const a = allNodes[i];
          const b = allNodes[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const distSq = dx * dx + dy * dy;
          if (distSq < 16000) {
            const dist = Math.max(Math.sqrt(distSq), 0.5);
            const force = 90 / (distSq + 20);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            if (a.id !== "repo") {
              a.x -= fx;
              a.y -= fy;
            }
            if (b.id !== "repo") {
              b.x += fx;
              b.y += fy;
            }
          }
        }
      }
    }

    nodesRef.current = allNodes;
    edgesRef.current = edgesList;
  }, [repository, analysis]);

  // Canvas drawing loop
  useEffect(() => {
    let animId: number;

    function renderCanvas() {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const currentNodes = nodesRef.current;
      const currentEdges = edgesRef.current;
      const nodeMap = new Map(currentNodes.map((n) => [n.id, n]));

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();

      // Pan & zoom transform
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);

      // Draw Edges
      currentEdges.forEach((edge) => {
        const s = nodeMap.get(edge.source);
        const t = nodeMap.get(edge.target);
        if (!s || !t) return;
        if (!activeFilters[s.type] || !activeFilters[t.type]) return;

        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);

        if (edge.type === "CALLS") {
          ctx.strokeStyle = "rgba(168, 85, 247, 0.6)"; // Purple
          ctx.setLineDash([4, 4]);
          ctx.lineWidth = 1.5;
        } else if (edge.type === "DEFINES") {
          ctx.strokeStyle = "rgba(16, 185, 129, 0.4)"; // Emerald
          ctx.setLineDash([]);
          ctx.lineWidth = 1;
        } else {
          ctx.strokeStyle = "rgba(99, 102, 241, 0.3)"; // Indigo
          ctx.setLineDash([]);
          ctx.lineWidth = 1.2;
        }
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Draw Nodes
      currentNodes.forEach((node) => {
        if (!activeFilters[node.type]) return;
        const isSelected = selectedNode?.id === node.id;
        const isMatch =
          searchQuery && node.name.toLowerCase().includes(searchQuery.toLowerCase());

        // Halo / Glow
        if (isSelected || isMatch) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.radius + 6, 0, 2 * Math.PI);
          ctx.strokeStyle = isMatch ? "#f59e0b" : "#ffffff";
          ctx.lineWidth = 2.5;
          ctx.stroke();
        }

        // Main Node Circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);
        ctx.fillStyle = node.color;
        ctx.fill();

        // Label
        ctx.fillStyle = isSelected ? "#ffffff" : isMatch ? "#fbbf24" : "#cbd5e1";
        ctx.font = `${node.type === "Repository" ? "bold 13px" : "11px"} Inter, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(node.name, node.x, node.y + node.radius + 14);
      });

      ctx.restore();
      animId = requestAnimationFrame(renderCanvas);
    }

    animId = requestAnimationFrame(renderCanvas);
    return () => cancelAnimationFrame(animId);
  }, [transform, activeFilters, selectedNode, searchQuery]);

  // Mouse drag / pan handlers
  function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left - transform.x) / transform.k;
    const mouseY = (e.clientY - rect.top - transform.y) / transform.k;

    // Check if clicked on a node
    const clicked = nodesRef.current.find((node) => {
      if (!activeFilters[node.type]) return false;
      const dx = node.x - mouseX;
      const dy = node.y - mouseY;
      return dx * dx + dy * dy <= (node.radius + 4) * (node.radius + 4);
    });

    if (clicked) {
      draggedNode.current = clicked;
      setSelectedNode(clicked);
    } else {
      isDraggingCanvas.current = true;
      dragStart.current = { x: e.clientX - transform.x, y: e.clientY - transform.y };
    }
  }

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (draggedNode.current) {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      draggedNode.current.x = (e.clientX - rect.left - transform.x) / transform.k;
      draggedNode.current.y = (e.clientY - rect.top - transform.y) / transform.k;
    } else if (isDraggingCanvas.current) {
      setTransform((prev) => ({
        ...prev,
        x: e.clientX - dragStart.current.x,
        y: e.clientY - dragStart.current.y,
      }));
    }
  }

  function handleMouseUp() {
    draggedNode.current = null;
    isDraggingCanvas.current = false;
  }

  function handleWheel(e: React.WheelEvent<HTMLCanvasElement>) {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    setTransform((prev) => ({
      ...prev,
      k: Math.max(0.4, Math.min(2.5, prev.k * zoomFactor)),
    }));
  }

  function copyCypher(query: string, label: string) {
    navigator.clipboard.writeText(query);
    setCopiedQuery(label);
    setTimeout(() => setCopiedQuery(null), 2000);
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Controls & Live Neo4j link */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Network className="w-5 h-5 text-emerald-400" /> Neo4j Code Knowledge Graph
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Real graph relationships (`DEFINES`, `CONTAINS`, `CALLS`) mapped from AST database
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Live Neo4j browser button */}
          <a
            href="http://localhost:7474"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 transition shadow-sm"
          >
            <Compass className="w-3.5 h-3.5" /> Open Live Neo4j Browser
            <ExternalLink className="w-3 h-3" />
          </a>

          {/* Quick Cypher Copy Buttons */}
          <button
            onClick={() =>
              copyCypher(
                "MATCH (f:File)-[r:DEFINES]->(fn:Function) RETURN f, r, fn LIMIT 30",
                "files-functions"
              )
            }
            className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1 transition"
            title="Copy Cypher query for files and functions"
          >
            {copiedQuery === "files-functions" ? (
              <Check className="w-3 h-3 text-emerald-400" />
            ) : (
              <Copy className="w-3 h-3" />
            )}
            Cypher: Files $\to$ Functions
          </button>

          <button
            onClick={() =>
              copyCypher(
                "MATCH (a:Function)-[r:CALLS]->(b:Function) RETURN a, r, b",
                "calls"
              )
            }
            className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1 transition"
            title="Copy Cypher query for function calls"
          >
            {copiedQuery === "calls" ? (
              <Check className="w-3 h-3 text-emerald-400" />
            ) : (
              <Copy className="w-3 h-3" />
            )}
            Cypher: Calls
          </button>
        </div>
      </div>

      {/* Graph Area & Inspector Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
        {/* Main Canvas with overlay filters */}
        <div className="lg:col-span-3 rounded-2xl border border-slate-800 bg-slate-950 p-2 relative min-h-[540px] flex flex-col shadow-inner">
          {/* Top Canvas Bar: Search & Node Legend / Filter */}
          <div className="absolute top-4 left-4 right-4 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
            {/* Search Input */}
            <div className="relative pointer-events-auto">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Find node by name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 text-xs bg-slate-900/90 backdrop-blur border border-slate-700 rounded-lg text-slate-200 outline-none focus:border-indigo-500 w-48 shadow-lg"
              />
            </div>

            {/* Type Filter Pills */}
            <div className="flex flex-wrap items-center gap-1.5 pointer-events-auto bg-slate-900/90 backdrop-blur border border-slate-800 p-1 rounded-xl shadow-lg">
              {Object.entries(TYPE_COLORS).map(([type, color]) => (
                <button
                  key={type}
                  onClick={() =>
                    setActiveFilters((prev) => ({ ...prev, [type]: !prev[type] }))
                  }
                  className={`px-2 py-1 rounded-md text-[11px] font-medium flex items-center gap-1 transition ${
                    activeFilters[type]
                      ? "bg-slate-800 text-slate-200 border border-slate-700"
                      : "text-slate-500 opacity-50 hover:opacity-100"
                  }`}
                >
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Canvas */}
          <canvas
            ref={canvasRef}
            width={900}
            height={540}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onWheel={handleWheel}
            className="w-full h-[540px] rounded-xl cursor-grab active:cursor-grabbing bg-slate-950/90"
          />

          {/* Bottom zoom buttons */}
          <div className="absolute bottom-4 right-4 z-10 flex items-center bg-slate-900/90 backdrop-blur border border-slate-800 rounded-lg p-1 shadow-lg">
            <button
              onClick={() => setTransform((prev) => ({ ...prev, k: Math.max(0.4, prev.k - 0.2) }))}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="px-2 text-xs font-mono text-slate-300">{Math.round(transform.k * 100)}%</span>
            <button
              onClick={() => setTransform((prev) => ({ ...prev, k: Math.min(2.5, prev.k + 0.2) }))}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setTransform({ x: 0, y: 0, k: 1 })}
              className="p-1.5 text-slate-400 hover:text-white rounded hover:bg-slate-800 transition ml-1 border-l border-slate-800"
              title="Reset view"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Node Detail Inspector Sidebar */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5 flex flex-col justify-between shadow-xl">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Node Inspector
              </span>
              {selectedNode && (
                <span
                  className="text-[10px] font-bold px-2 py-0.5 rounded uppercase"
                  style={{
                    backgroundColor: `${selectedNode.color}20`,
                    color: selectedNode.color,
                    border: `1px solid ${selectedNode.color}40`,
                  }}
                >
                  {selectedNode.type}
                </span>
              )}
            </div>

            {selectedNode ? (
              <div className="space-y-4 mt-4">
                <div>
                  <h3 className="text-sm font-bold text-white break-words">{selectedNode.name}</h3>
                  <p className="text-xs text-slate-400 font-mono mt-0.5">{selectedNode.id}</p>
                </div>

                {selectedNode.details && (
                  <div className="space-y-2 text-xs">
                    {selectedNode.details.file && (
                      <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/80">
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">File</span>
                        <span className="text-slate-200 font-mono break-all">{selectedNode.details.file}</span>
                      </div>
                    )}
                    {selectedNode.details.line_start !== undefined && (
                      <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/80">
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">Location</span>
                        <span className="text-slate-200 font-mono">
                          Lines {selectedNode.details.line_start} - {selectedNode.details.line_end}
                        </span>
                      </div>
                    )}
                    {selectedNode.details.parameters && selectedNode.details.parameters.length > 0 && (
                      <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/80">
                        <span className="text-slate-400 block text-[10px] uppercase font-semibold">Parameters</span>
                        <span className="text-slate-200 font-mono">
                          ({selectedNode.details.parameters.join(", ")})
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="py-16 text-center text-slate-400">
                <Compass className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                <p className="text-xs">Click any node on the graph canvas to inspect its AST metadata and relations.</p>
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-slate-800/80 text-[11px] text-slate-400">
            Tip: Drag nodes to rearrange. Scroll mouse wheel to zoom in/out.
          </div>
        </div>
      </div>
    </div>
  );
};
export default KnowledgeGraphTab;
