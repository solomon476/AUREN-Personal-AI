web: cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}
worker: cd backend && python -m app.services.memory.runner
