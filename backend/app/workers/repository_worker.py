"""
Celery task wrapping the same ingestion pipeline used by the inline
BackgroundTasks path in app/api/routes/repositories.py.

Switch the API route to call `run_ingestion_task.delay(repository_id)`
instead of the inline `_run_ingestion` once you want ingestion to run
on the `worker` container instead of inside the API process (recommended
for anything beyond small demo repos).
"""
from app.core.database import SessionLocal
from app.models.models import Repository
from app.services.repository_service import ingest_repository
from app.workers.celery_app import celery_app


@celery_app.task(name="repository.ingest")
def run_ingestion_task(repository_id: str):
    db = SessionLocal()
    try:
        repo = db.query(Repository).filter(Repository.id == repository_id).first()
        if repo:
            ingest_repository(db, repo)
    finally:
        db.close()
