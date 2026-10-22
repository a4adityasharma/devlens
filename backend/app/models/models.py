import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, JSON, Text, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    owner = Column(String, nullable=True)
    default_branch = Column(String, default="main")
    local_path = Column(String, nullable=True)

    primary_language = Column(String, nullable=True)
    languages = Column(JSON, default=dict)  # {"python": 120, "typescript": 40}
    file_count = Column(Integer, default=0)
    size_bytes = Column(Integer, default=0)
    frameworks = Column(JSON, default=list)
    package_managers = Column(JSON, default=list)
    entry_points = Column(JSON, default=list)

    status = Column(String, default="queued")  # queued|cloning|scanning|ready|failed
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    analyses = relationship("RepositoryAnalysis", back_populates="repository", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="repository", cascade="all, delete-orphan")


class RepositoryAnalysis(Base):
    __tablename__ = "repository_analyses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    repository_id = Column(UUID(as_uuid=False), ForeignKey("repositories.id"), nullable=False)
    commit_hash = Column(String, nullable=True)

    status = Column(String, default="pending")  # pending|running|completed|failed
    stage = Column(String, nullable=True)  # cloning|parsing|graph|embedding|agents|done

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    stats = Column(JSON, default=dict)  # file_count, function_count, class_count, etc.
    symbols = Column(JSON, default=list)  # [{type,name,file,line_start,line_end,...}, ...]

    created_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="analyses")
    findings = relationship("Finding", back_populates="analysis", cascade="all, delete-orphan")
    artifacts = relationship("GeneratedArtifact", back_populates="analysis", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    analysis_id = Column(UUID(as_uuid=False), ForeignKey("repository_analyses.id"), nullable=False)

    agent = Column(String, nullable=False)  # security|architecture|testing|performance|review|docs
    category = Column(String, nullable=True)
    severity = Column(String, nullable=True)  # LOW|MEDIUM|HIGH|CRITICAL
    confidence = Column(Float, nullable=True)

    file_path = Column(String, nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)

    validated = Column(String, default="pending")  # pending|valid|rejected

    created_at = Column(DateTime, default=datetime.utcnow)

    analysis = relationship("RepositoryAnalysis", back_populates="findings")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    repository_id = Column(UUID(as_uuid=False), ForeignKey("repositories.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # user|assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, default=list)  # [{"file":..,"line":..}]
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class GeneratedArtifact(Base):
    """Non-finding agent output — diagrams, generated docs, etc. (architecture
    doc §24/§32 mentions a `generated_artifacts` table; the Finding table is
    shaped for security-style findings and shouldn't be overloaded for
    fundamentally different content like a Mermaid diagram)."""
    __tablename__ = "generated_artifacts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    analysis_id = Column(UUID(as_uuid=False), ForeignKey("repository_analyses.id"), nullable=False)
    agent = Column(String, nullable=False)  # e.g. "architecture"
    artifact_type = Column(String, nullable=False)  # e.g. "mermaid_diagram"
    content = Column(Text, nullable=False)  # the artifact itself (e.g. Mermaid source)
    extra = Column(JSON, default=dict)  # structured data alongside content, e.g. layer stats
    created_at = Column(DateTime, default=datetime.utcnow)

    analysis = relationship("RepositoryAnalysis", back_populates="artifacts")
