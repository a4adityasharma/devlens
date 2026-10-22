import axios from "axios";
import type {
  Repository,
  AnalysisOut,
  ArtifactOut,
  FindingOut,
  UntestedSymbolOut,
  ChatResponse,
  SearchResultOut,
  GenerateTestResponse,
} from "../types/repository";

const api = axios.create({ baseURL: "/api" });

// ── Repositories ──────────────────────────────────────────────────────────────

export async function createRepository(url: string) {
  const { data } = await api.post<{ repository_id: string; status: string }>(
    "/repositories",
    { url }
  );
  return data;
}

export async function listRepositories() {
  const { data } = await api.get<Repository[]>("/repositories");
  return data;
}

export async function getRepository(id: string) {
  const { data } = await api.get<Repository>(`/repositories/${id}`);
  return data;
}

export async function deleteRepository(id: string) {
  await api.delete(`/repositories/${id}`);
}

// ── Analysis ──────────────────────────────────────────────────────────────────

export async function getLatestAnalysis(id: string) {
  const { data } = await api.get<AnalysisOut>(
    `/repositories/${id}/analyses/latest`
  );
  return data;
}

// ── Architecture diagram ───────────────────────────────────────────────────────

export async function getArchitecture(id: string) {
  const { data } = await api.get<ArtifactOut>(
    `/repositories/${id}/architecture`
  );
  return data;
}

// ── Security ───────────────────────────────────────────────────────────────────

export async function runSecurityScan(id: string) {
  const { data } = await api.post(`/repositories/${id}/analyze/security`);
  return data;
}

export async function getFindings(id: string) {
  const { data } = await api.get<FindingOut[]>(`/repositories/${id}/findings`);
  return data;
}

// ── Testing ───────────────────────────────────────────────────────────────────

export async function getUntestedSymbols(id: string) {
  const { data } = await api.get<UntestedSymbolOut[]>(
    `/repositories/${id}/untested`
  );
  return data;
}

export async function generateTest(
  id: string,
  file_path: string,
  symbol_name: string
) {
  const { data } = await api.post<GenerateTestResponse>(
    `/repositories/${id}/generate-test`,
    { file_path, symbol_name }
  );
  return data;
}

// ── Chat & Search ─────────────────────────────────────────────────────────────

export async function sendChatMessage(
  id: string,
  question: string,
  session_id?: string
) {
  const { data } = await api.post<ChatResponse>(`/repositories/${id}/chat`, {
    question,
    session_id,
  });
  return data;
}

export async function searchRepository(
  id: string,
  query: string,
  top_k = 10
) {
  const { data } = await api.post<SearchResultOut[]>(
    `/repositories/${id}/search`,
    { query, top_k }
  );
  return data;
}
