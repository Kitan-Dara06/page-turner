web: PYTHONPATH=backend uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
worker: PYTHONPATH=backend celery -A backend.app.workers.celery_app worker -B --loglevel=info --concurrency=4 --max-memory-per-child=120000
