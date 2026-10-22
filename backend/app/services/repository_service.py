"""
Repository Manager (Module 1)

Responsible for:
  1. Validating a GitHub URL
  2. Cloning the repository to local disk
  3. Discovering files (skipping ignored directories)
  4. Detecting languages / frameworks / package managers / entry points
  5. Persisting metadata to Postgres
"""
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import git
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import Repository

settings = get_settings()

GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(\.git)?/?$"
)

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
}

FRAMEWORK_MARKERS = {
    "package.json": None,          # inspected further for react/vue/express etc.
    "requirements.txt": "python-pip",
    "pyproject.toml": "python-poetry",
    "manage.py": "django",
    "next.config.js": "nextjs",
    "next.config.ts": "nextjs",
    "angular.json": "angular",
    "pom.xml": "maven",
    "build.gradle": "gradle",
}

ENTRY_POINT_CANDIDATES = [
    "main.py", "app.py", "manage.py", "index.js", "index.ts",
    "server.js", "server.ts", "src/main.tsx", "src/index.tsx",
]


class InvalidRepositoryURLError(Exception):
    pass


def validate_github_url(url: str) -> dict:
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise InvalidRepositoryURLError(f"'{url}' is not a valid GitHub repository URL")
    return match.groupdict()


def _iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in settings.IGNORED_DIRS]
        for fname in filenames:
            yield Path(dirpath) / fname


def clone_repository(url: str, repo_id: str) -> Path:
    dest = Path(settings.REPO_STORAGE_PATH) / repo_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    git.Repo.clone_from(url, dest, depth=1)
    return dest


def scan_repository(local_path: Path) -> dict:
    """Walk the repo, skip ignored dirs, detect languages/frameworks/entry points."""
    language_counts: dict[str, int] = {}
    file_count = 0
    size_bytes = 0
    frameworks: set[str] = set()
    package_managers: set[str] = set()
    entry_points: list[str] = []

    for path in _iter_source_files(local_path):
        try:
            size_bytes += path.stat().st_size
        except OSError:
            continue
        file_count += 1

        ext = path.suffix.lower()
        if ext in LANGUAGE_EXTENSIONS:
            lang = LANGUAGE_EXTENSIONS[ext]
            language_counts[lang] = language_counts.get(lang, 0) + 1

        if path.name in FRAMEWORK_MARKERS:
            marker = FRAMEWORK_MARKERS[path.name]
            if marker:
                frameworks.add(marker)
            if path.name in ("requirements.txt", "pyproject.toml"):
                package_managers.add("pip/poetry")
            if path.name in ("pom.xml",):
                package_managers.add("maven")
            if path.name in ("build.gradle",):
                package_managers.add("gradle")

        rel = str(path.relative_to(local_path))
        if rel in ENTRY_POINT_CANDIDATES or path.name in ENTRY_POINT_CANDIDATES:
            entry_points.append(rel)

        if path.name == "package.json":
            package_managers.add("npm/yarn")
            try:
                content = path.read_text(errors="ignore")
                if '"react"' in content:
                    frameworks.add("react")
                if '"vue"' in content:
                    frameworks.add("vue")
                if '"express"' in content:
                    frameworks.add("express")
                if '"next"' in content:
                    frameworks.add("nextjs")
            except OSError:
                pass

    primary_language = max(language_counts, key=language_counts.get) if language_counts else None

    return {
        "languages": language_counts,
        "primary_language": primary_language,
        "file_count": file_count,
        "size_bytes": size_bytes,
        "frameworks": sorted(frameworks),
        "package_managers": sorted(package_managers),
        "entry_points": entry_points[:10],
    }


def ingest_repository(db: Session, repository: Repository) -> Repository:
    """Full synchronous ingestion pipeline: clone -> scan -> persist.

    In production this body is what the Celery task (app/workers/repository_worker.py)
    calls, so the same logic runs whether triggered inline (small repos / demo)
    or asynchronously via the queue.
    """
    try:
        repository.status = "cloning"
        db.commit()

        local_path = clone_repository(repository.url, repository.id)
        repository.local_path = str(local_path)

        repository.status = "scanning"
        db.commit()

        metadata = scan_repository(local_path)

        if metadata["file_count"] > settings.MAX_REPO_FILES:
            repository.status = "failed"
            repository.error_message = (
                f"Repository has {metadata['file_count']} files, "
                f"exceeding MVP limit of {settings.MAX_REPO_FILES}"
            )
            db.commit()
            return repository

        repository.languages = metadata["languages"]
        repository.primary_language = metadata["primary_language"]
        repository.file_count = metadata["file_count"]
        repository.size_bytes = metadata["size_bytes"]
        repository.frameworks = metadata["frameworks"]
        repository.package_managers = metadata["package_managers"]
        repository.entry_points = metadata["entry_points"]
        repository.status = "ready"
        db.commit()
        db.refresh(repository)
        return repository

    except Exception as exc:  # noqa: BLE001
        repository.status = "failed"
        repository.error_message = str(exc)
        db.commit()
        raise
