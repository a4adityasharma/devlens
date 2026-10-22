from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.api.routes import repositories


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP: create tables directly. Replace with Alembic migrations
    # (backend/alembic/) once the schema stabilizes.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="DevLens AI API",
    version="0.1.0",
    description="Repository-aware code intelligence platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repositories.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
