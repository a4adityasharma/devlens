import React from "react";
import { Link } from "react-router-dom";
import { Layers, Network, BookOpen, ExternalLink, Cpu, ChevronRight } from "lucide-react";

interface NavbarProps {
  repoName?: string;
  repoOwner?: string;
}

export const Navbar: React.FC<NavbarProps> = ({ repoName, repoOwner }) => {
  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-slate-950/80 border-b border-slate-800/80 transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand & Breadcrumb */}
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:shadow-indigo-500/40 transition-all duration-300">
              <Cpu className="w-5 h-5 text-white" />
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-300 bg-clip-text text-transparent">
                  DevLens
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 font-semibold border border-indigo-500/20">
                  AI
                </span>
              </div>
            </div>
          </Link>

          {repoOwner && repoName && (
            <div className="flex items-center gap-2 text-sm ml-2 pl-3 border-l border-slate-800">
              <ChevronRight className="w-4 h-4 text-slate-600" />
              <Link to="/" className="text-slate-400 hover:text-slate-200 transition-colors">
                Repositories
              </Link>
              <ChevronRight className="w-4 h-4 text-slate-600" />
              <span className="font-medium text-slate-200">
                {repoOwner}/{repoName}
              </span>
            </div>
          )}
        </div>

        {/* External Tool Shortcuts & Status */}
        <div className="flex items-center gap-3">
          <a
            href="http://localhost:7474"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 transition-all duration-200 group shadow-sm"
            title="Open Neo4j Visual Graph Browser (neo4j / devlenspass)"
          >
            <Network className="w-3.5 h-3.5 text-emerald-400 group-hover:scale-110 transition-transform" />
            <span>Neo4j Browser</span>
            <ExternalLink className="w-3 h-3 text-slate-500 group-hover:text-slate-300" />
          </a>

          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 transition-all duration-200 group shadow-sm"
            title="Open Interactive FastAPI Swagger Documentation"
          >
            <BookOpen className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
            <span>API Docs</span>
            <ExternalLink className="w-3 h-3 text-slate-500 group-hover:text-slate-300" />
          </a>

          <div className="flex items-center gap-2 pl-2 border-l border-slate-800 text-xs text-emerald-400 font-medium hidden sm:flex">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-slate-400">Stack Active</span>
          </div>
        </div>
      </div>
    </header>
  );
};
export default Navbar;
