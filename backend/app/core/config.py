from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me"

    DATABASE_URL: str = "postgresql+psycopg2://devlens:devlens@localhost:5432/devlens"
    REDIS_URL: str = "redis://localhost:6379/0"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "devlenspass"

    QDRANT_URL: str = "http://localhost:6333"

    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    REPO_STORAGE_PATH: str = "./storage/repos"
    MAX_REPO_FILES: int = 10000

    IGNORED_DIRS: set[str] = {
        ".git", "node_modules", "venv", ".venv", "dist", "build",
        "coverage", "__pycache__", "target", ".next", ".idea", ".vscode",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
