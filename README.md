# DevLens AI

Repository-aware code intelligence platform. Converts source code into structured
knowledge (AST + graph + vectors), then lets specialised AI agents reason over it
with evidence-backed answers.

## Status: Milestone 1 + Module 1 (Repository Manager) — working

See `docs/PROGRESS.md` for the full build log, what's implemented, what's next,
and prompts to continue this project with other AI tools.

## Quick start (local, no Docker)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="sqlite:///./dev.db"
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, paste a public GitHub URL (e.g.
`https://github.com/octocat/Hello-World`), and watch the repository move through
`queued → cloning → scanning → ready`.

## Quick start (Docker, full stack incl. Neo4j/Qdrant/Redis)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Neo4j browser: http://localhost:7474 (neo4j / devlenspass)
- Qdrant: http://localhost:6333/dashboard

## API

```
POST /api/repositories        { "url": "https://github.com/owner/repo" }  -> 202
GET  /api/repositories                                                   -> list
GET  /api/repositories/{id}                                              -> detail
DELETE /api/repositories/{id}
```

## Project layout

```
devlens-ai/
├── backend/     FastAPI app, SQLAlchemy models, Celery worker
├── frontend/    React + TS + Tailwind
├── docker-compose.yml   postgres, redis, neo4j, qdrant, backend, worker, frontend
└── docs/PROGRESS.md     build log + roadmap + AI-tool handoff prompts
```
