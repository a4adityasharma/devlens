import os

# Ensure tests never require a running Postgres instance — default to a
# local SQLite file unless the environment already specifies DATABASE_URL
# (e.g. CI running against real Postgres).
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
