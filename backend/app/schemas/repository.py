from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RepositoryCreate(BaseModel):
    url: str = Field(..., description="GitHub repository URL")


class RepositoryOut(BaseModel):
    id: str
    name: str
    url: str
    owner: Optional[str] = None
    default_branch: Optional[str] = None
    primary_language: Optional[str] = None
    languages: dict = {}
    file_count: int = 0
    size_bytes: int = 0
    frameworks: list = []
    package_managers: list = []
    entry_points: list = []
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RepositoryCreateResponse(BaseModel):
    repository_id: str
    status: str


class AnalysisOut(BaseModel):
    id: str
    repository_id: str
    commit_hash: Optional[str] = None
    status: str
    stage: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    stats: dict = {}
    symbols: list = []
    created_at: datetime

    class Config:
        from_attributes = True


class SearchQuery(BaseModel):
    query: str = Field(..., description="Natural-language or keyword search query")
    limit: int = Field(default=10, ge=1, le=50)


class SearchResultOut(BaseModel):
    id: str
    score: float
    repository_id: str
    file: str
    symbol: str
    type: str
    language: str
    start_line: int
    end_line: int
    parent: Optional[str] = None
    parameters: list = []
    text: str


class FindingOut(BaseModel):
    id: str
    analysis_id: str
    agent: str
    category: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[float] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    title: str
    description: Optional[str] = None
    recommendation: Optional[str] = None
    validated: str
    created_at: datetime

    class Config:
        from_attributes = True


class SecurityScanResponse(BaseModel):
    findings_created: int
    findings_rejected: int
    total_raw: int
    findings: list[FindingOut] = []


class ArtifactOut(BaseModel):
    id: str
    analysis_id: str
    agent: str
    artifact_type: str
    content: str
    extra: dict = {}
    created_at: datetime

    class Config:
        from_attributes = True


class UntestedSymbolOut(BaseModel):
    file: str
    name: str
    type: str
    parent: Optional[str] = None
    line_start: int
    line_end: int
    parameters: list = []


class GenerateTestRequest(BaseModel):
    file: str = Field(..., description="File path (relative to repo root) containing the target symbol")
    symbol_name: str = Field(..., description="Name of the function/method to generate a test for")


class GenerateTestResponse(BaseModel):
    file: str
    symbol: str
    generated_code: str
    validation: dict
    persisted: bool
    artifact_id: Optional[str] = None


class GenerateDocRequest(BaseModel):
    doc_type: str = Field(..., description="One of: readme, architecture_overview, setup_guide, api_reference")


class GenerateDocResponse(BaseModel):
    doc_type: str
    content: str
    grounding: dict
    artifact_id: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's question about the repository")
    session_id: Optional[str] = Field(
        default=None, description="Continue an existing chat session, or start a new one if omitted"
    )


class ChatSourceOut(BaseModel):
    file: str
    line_start: int
    line_end: int
    symbol: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[ChatSourceOut] = []
    graph_available: bool
    hit_count: int
