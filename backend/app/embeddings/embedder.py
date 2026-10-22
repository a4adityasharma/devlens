"""
Embedding (Phase 5 / architecture doc §12).

Two implementations behind one `Embedder` interface:

- `OpenAIEmbedder` — the real, production path. Calls OpenAI's embeddings
  API using `OPENAI_API_KEY`/`EMBEDDING_MODEL` from app/core/config.py.
  **This class has NOT been exercised against a live API in any session so
  far** — api.openai.com is outside this sandbox's allowed network domains
  (only api.anthropic.com is reachable, and Anthropic doesn't expose an
  embeddings endpoint). Whoever next has real API access should verify
  this class before trusting it; the batching/retry logic is written
  carefully but unverified end-to-end.

- `HashingEmbedder` — a deterministic, dependency-free, offline fallback
  using the classic "hashing trick" (token -> bucket via hash, bag-of-words
  counts, L2-normalized). It is NOT semantically meaningful the way a real
  embedding model is — "authentication" and "login" will not land near
  each other the way they would with a real model — so it must not be
  mistaken for good search quality. Its purpose is narrower: it lets the
  full chunk -> embed -> store -> query pipeline be built and verified
  end-to-end in environments with no embedding API access (like this one),
  and it's a reasonable zero-config fallback for local dev. Swap in
  `OpenAIEmbedder` (or another real provider) before relying on search
  quality for anything user-facing / for Phase 6 RAG.
"""
import hashlib
import re
from abc import ABC, abstractmethod

from app.core.config import get_settings

settings = get_settings()

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_SPLIT_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _tokenize(text: str) -> list[str]:
    """Splits on non-identifier chars, then further splits identifiers on
    snake_case/camelCase boundaries — `authenticate_user` and
    `authenticateUser` both become ["authenticate", "user"]. Without this,
    a query for "authenticate" shares zero tokens with a chunk containing
    only the identifier `authenticate_user` (discovered by testing against
    real Qdrant search results — see test_embedding_service.py, the
    original single-token version ranked an unrelated chunk first because
    neither chunk's compound identifiers matched the query at all).

    Case-sensitive camelCase detection has to happen BEFORE lowercasing —
    lowercasing first destroys the exact signal (`authenticateUser` ->
    `authenticateuser`) camelCase splitting depends on.
    """
    tokens = []
    for word in _IDENTIFIER_RE.findall(text):  # NOT text.lower() — see docstring
        for part in word.split("_"):
            if not part:
                continue
            sub = _CAMEL_SPLIT_RE.findall(part)
            tokens.extend((s.lower() for s in sub) if sub else [part.lower()])
    return tokens

# Known output dimensions for OpenAI's current embedding models, so callers
# can size a Qdrant collection before the first real API call.
_OPENAI_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class Embedder(ABC):
    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Returns one vector per input text, same order, same length."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...


class OpenAIEmbedder(Embedder):
    """Production path — see module docstring for verification status."""

    def __init__(self, api_key: str | None = None, model: str | None = None, batch_size: int = 100):
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._model = model or settings.EMBEDDING_MODEL
        self._batch_size = batch_size
        if not self._api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set — OpenAIEmbedder cannot be used. "
                "Either set it in .env, or use get_embedder() which falls "
                "back to HashingEmbedder automatically when no key is present."
            )
        # Imported lazily so the `openai` package is only required when this
        # class is actually instantiated, not for the whole app to import.
        from openai import OpenAI
        self._client = OpenAI(api_key=self._api_key)

    @property
    def dimension(self) -> int:
        return _OPENAI_MODEL_DIMS.get(self._model, 1536)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            response = self._client.embeddings.create(model=self._model, input=batch)
            # OpenAI guarantees response.data is in the same order as input.
            vectors.extend(item.embedding for item in response.data)
        return vectors


class HashingEmbedder(Embedder):
    """Deterministic offline fallback — see module docstring."""

    def __init__(self, dimension: int = 256):
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        tokens = _tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self._dimension
            vector[bucket] += 1.0
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


def get_embedder() -> Embedder:
    """Factory: real embeddings if an API key is configured, otherwise the
    offline fallback. Every caller should go through this rather than
    instantiating a specific Embedder directly, so swapping providers is a
    config change, not a code change."""
    if settings.OPENAI_API_KEY:
        return OpenAIEmbedder()
    return HashingEmbedder()
