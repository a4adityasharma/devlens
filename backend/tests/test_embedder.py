import math

from app.embeddings.embedder import HashingEmbedder, get_embedder


def test_hashing_embedder_is_deterministic():
    embedder = HashingEmbedder(dimension=64)
    v1 = embedder.embed_batch(["def authenticate(user):"])
    v2 = embedder.embed_batch(["def authenticate(user):"])
    assert v1 == v2


def test_hashing_embedder_produces_correct_dimension():
    embedder = HashingEmbedder(dimension=128)
    [vector] = embedder.embed_batch(["hello world"])
    assert len(vector) == 128
    assert embedder.dimension == 128


def test_hashing_embedder_vectors_are_l2_normalized():
    embedder = HashingEmbedder(dimension=64)
    [vector] = embedder.embed_batch(["some function with several distinct tokens here"])
    norm = math.sqrt(sum(v * v for v in vector))
    assert abs(norm - 1.0) < 1e-9


def test_hashing_embedder_empty_text_returns_zero_vector():
    embedder = HashingEmbedder(dimension=32)
    [vector] = embedder.embed_batch([""])
    assert vector == [0.0] * 32


def test_hashing_embedder_batch_preserves_order_and_count():
    embedder = HashingEmbedder(dimension=32)
    texts = ["alpha", "beta function", "gamma delta epsilon"]
    vectors = embedder.embed_batch(texts)
    assert len(vectors) == 3
    # different texts should (almost certainly) produce different vectors
    assert vectors[0] != vectors[1] != vectors[2]


def test_hashing_embedder_similar_text_scores_higher_than_dissimilar():
    """Not a claim of semantic quality (see embedder.py's module docstring
    — this is a bag-of-words hash, not a real model) — just confirms the
    vectors behave sanely enough for the pipeline to be meaningfully
    testable: literally shared tokens should push cosine similarity up."""
    embedder = HashingEmbedder(dimension=256)
    base = "def authenticate_user(username, password): validate credentials"
    similar = "def authenticate_admin(username, password): validate credentials"
    different = "def render_chart(data, axis): plot the histogram"

    v_base, v_similar, v_different = embedder.embed_batch([base, similar, different])

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))  # already L2-normalized

    assert cosine(v_base, v_similar) > cosine(v_base, v_different)


def test_get_embedder_falls_back_to_hashing_without_api_key(monkeypatch):
    monkeypatch.setattr("app.embeddings.embedder.settings.OPENAI_API_KEY", "")
    embedder = get_embedder()
    assert isinstance(embedder, HashingEmbedder)
