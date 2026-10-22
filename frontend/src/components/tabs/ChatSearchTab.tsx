import React, { useState, useRef, useEffect } from "react";
import type { ChatResponse, ChatSourceOut, SearchResultOut } from "../../types/repository";
import { sendChatMessage, searchRepository } from "../../services/api";
import {
  MessageSquare,
  Search,
  Send,
  FileCode,
  Bot,
  User,
  Sparkles,
  Network,
  AlertCircle,
  Loader2,
  Code2,
  ArrowRight,
} from "lucide-react";

interface ChatSearchTabProps {
  repositoryId: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: ChatSourceOut[];
  graphAvailable?: boolean;
  hitCount?: number;
}

export const ChatSearchTab: React.FC<ChatSearchTabProps> = ({ repositoryId }) => {
  // Chat state
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResultOut[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Active tab
  const [mode, setMode] = useState<"chat" | "search">("chat");

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMsg = chatInput.trim();
    setChatInput("");
    setChatError(null);
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setChatLoading(true);

    try {
      const res = await sendChatMessage(repositoryId, userMsg, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          graphAvailable: res.graph_available,
          hitCount: res.hit_count,
        },
      ]);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || "Chat request failed";
      if (err?.response?.status === 503) {
        setChatError(
          "LLM is not configured. Add ANTHROPIC_API_KEY or OPENAI_API_KEY to .env to enable RAG Chat."
        );
      } else {
        setChatError(detail);
      }
    } finally {
      setChatLoading(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim() || searchLoading) return;

    setSearchLoading(true);
    setSearchError(null);
    setSearchResults([]);

    try {
      const results = await searchRepository(repositoryId, searchQuery.trim(), 15);
      setSearchResults(results);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || "Search failed";
      setSearchError(detail);
    } finally {
      setSearchLoading(false);
    }
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Mode Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-xl border border-slate-800">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            {mode === "chat" ? (
              <MessageSquare className="w-5 h-5 text-purple-400" />
            ) : (
              <Search className="w-5 h-5 text-indigo-400" />
            )}
            {mode === "chat" ? "RAG AI Codebase Chat" : "Semantic Vector Code Search"}
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {mode === "chat"
              ? "Ask questions about the codebase grounded by Neo4j graph context and Qdrant vector retrieval."
              : "Natural-language query matched against embedded code chunks in Qdrant."}
          </p>
        </div>

        <div className="flex bg-slate-950 border border-slate-800 rounded-xl p-1">
          <button
            onClick={() => setMode("chat")}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition ${
              mode === "chat"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" /> AI Chat
          </button>
          <button
            onClick={() => setMode("search")}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition ${
              mode === "search"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            <Search className="w-3.5 h-3.5" /> Code Search
          </button>
        </div>
      </div>

      {/* ===================== CHAT MODE ===================== */}
      {mode === "chat" && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950 flex flex-col h-[580px] shadow-xl overflow-hidden">
          {/* Message Thread */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {messages.length === 0 && !chatError && (
              <div className="flex flex-col items-center justify-center h-full text-center py-16">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-600/20 to-indigo-600/20 border border-purple-500/30 flex items-center justify-center mb-4">
                  <Bot className="w-8 h-8 text-purple-400" />
                </div>
                <h3 className="text-base font-semibold text-white">Ask anything about this codebase</h3>
                <p className="text-xs text-slate-400 mt-1.5 max-w-md">
                  I answer questions using evidence retrieved from the Neo4j knowledge graph and
                  Qdrant vector embeddings. Every source citation is validated against the AST.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-6 max-w-lg">
                  {[
                    "What is the main entry point of this project?",
                    "How does authentication work in this codebase?",
                    "What functions handle API routing?",
                    "Explain the database models and their relationships",
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => {
                        setChatInput(suggestion);
                      }}
                      className="text-left px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 hover:border-purple-500/40 hover:text-white transition"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div key={idx} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-lg bg-purple-600/20 border border-purple-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Bot className="w-4 h-4 text-purple-400" />
                  </div>
                )}

                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-indigo-600 text-white rounded-br-md"
                      : "bg-slate-900 text-slate-200 border border-slate-800 rounded-bl-md"
                  }`}
                >
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Source Citations */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-1.5">
                      <div className="text-[11px] font-semibold text-purple-300 flex items-center gap-1">
                        <Sparkles className="w-3 h-3" /> Grounded Sources ({msg.sources.length})
                      </div>
                      {msg.sources.map((src, si) => (
                        <div
                          key={si}
                          className="flex items-center gap-2 px-2 py-1 bg-slate-950/60 rounded-lg text-[11px] font-mono text-slate-400"
                        >
                          <FileCode className="w-3 h-3 text-indigo-400 flex-shrink-0" />
                          <span className="text-slate-300 truncate">{src.file}</span>
                          <span className="text-indigo-400">:L{src.line_start}-{src.line_end}</span>
                          <span className="text-emerald-400">{src.symbol}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Graph Context Indicator */}
                  {msg.role === "assistant" && msg.graphAvailable !== undefined && (
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
                      <Network className="w-3 h-3" />
                      <span>
                        Graph: {msg.graphAvailable ? "✓ Used" : "✗ Unavailable"} •{" "}
                        {msg.hitCount ?? 0} retrieval hits
                      </span>
                    </div>
                  )}
                </div>

                {msg.role === "user" && (
                  <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-indigo-400" />
                  </div>
                )}
              </div>
            ))}

            {chatLoading && (
              <div className="flex gap-3 justify-start">
                <div className="w-7 h-7 rounded-lg bg-purple-600/20 border border-purple-500/30 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-purple-400" />
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                  Reasoning over graph + vector context...
                </div>
              </div>
            )}

            {chatError && (
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <span>{chatError}</span>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Input Bar */}
          <form
            onSubmit={handleSendMessage}
            className="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center gap-3"
          >
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask about the codebase..."
              className="flex-1 px-4 py-2.5 bg-slate-950 border border-slate-700 rounded-xl text-sm text-slate-200 outline-none focus:border-purple-500 placeholder:text-slate-500"
              disabled={chatLoading}
            />
            <button
              type="submit"
              disabled={chatLoading || !chatInput.trim()}
              className="p-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white transition shadow-sm flex items-center justify-center"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}

      {/* ===================== SEARCH MODE ===================== */}
      {mode === "search" && (
        <div className="space-y-5">
          {/* Search Form */}
          <form
            onSubmit={handleSearch}
            className="flex items-center gap-3 bg-slate-950 p-4 rounded-2xl border border-slate-800 shadow-xl"
          >
            <Search className="w-5 h-5 text-slate-500 flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Describe what you're looking for in natural language..."
              className="flex-1 bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
              disabled={searchLoading}
            />
            <button
              type="submit"
              disabled={searchLoading || !searchQuery.trim()}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs font-semibold flex items-center gap-2 transition"
            >
              {searchLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Search className="w-3.5 h-3.5" />
              )}
              Search
            </button>
          </form>

          {searchError && (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <span>{searchError}</span>
            </div>
          )}

          {/* Results */}
          {searchResults.length > 0 && (
            <div className="space-y-3">
              <div className="text-xs text-slate-400 font-medium">
                {searchResults.length} matching code segments (ranked by semantic similarity)
              </div>

              {searchResults.map((result, idx) => (
                <div
                  key={result.id || idx}
                  className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 hover:border-slate-700 transition space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 uppercase">
                        {result.type}
                      </span>
                      <span className="text-sm font-bold text-white font-mono">{result.symbol}</span>
                      <span className="text-xs text-slate-400">in {result.language}</span>
                    </div>
                    <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-md border border-emerald-500/20">
                      Score: {result.score.toFixed(3)}
                    </span>
                  </div>

                  <div className="text-xs font-mono text-slate-400 flex items-center gap-2">
                    <FileCode className="w-3 h-3 text-indigo-400" />
                    <span>{result.file}</span>
                    <span className="text-indigo-400">
                      :L{result.start_line}-{result.end_line}
                    </span>
                  </div>

                  <pre className="text-xs font-mono text-slate-300 bg-slate-950 p-3 rounded-lg overflow-x-auto max-h-28 leading-relaxed border border-slate-800/80">
                    {result.text}
                  </pre>
                </div>
              ))}
            </div>
          )}

          {searchResults.length === 0 && !searchLoading && !searchError && searchQuery && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center">
              <Search className="w-10 h-10 text-slate-500 mx-auto mb-3" />
              <h3 className="text-sm font-semibold text-white">No results found</h3>
              <p className="text-xs text-slate-400 mt-1">
                Try rephrasing your query or ensure embeddings were generated during analysis.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
export default ChatSearchTab;
