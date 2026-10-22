"""
Thin wrapper around the official `neo4j` driver (architecture doc §9-10).

Kept deliberately small: one driver instance per process, a context-managed
session helper, and a `run_query` convenience method. Higher-level graph
logic (what nodes/relationships to write) lives in graph_builder.py, not
here — this module knows nothing about repositories/symbols.
"""
from contextlib import contextmanager

from neo4j import GraphDatabase

from app.core.config import get_settings

settings = get_settings()


class Neo4jClient:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self._uri = uri or settings.NEO4J_URI
        self._user = user or settings.NEO4J_USER
        self._password = password or settings.NEO4J_PASSWORD
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
        return self._driver

    @contextmanager
    def session(self):
        driver = self._get_driver()
        session = driver.session()
        try:
            yield session
        finally:
            session.close()

    def run_query(self, cypher: str, **params) -> list[dict]:
        with self.session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    def run_write(self, cypher: str, **params) -> None:
        """For statements where we don't need the result (bulk writes)."""
        with self.session() as session:
            session.run(cypher, **params)

    def verify_connectivity(self) -> bool:
        try:
            self._get_driver().verify_connectivity()
            return True
        except Exception:  # noqa: BLE001
            return False

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None


_client: Neo4jClient | None = None


def get_neo4j_client() -> Neo4jClient:
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client
