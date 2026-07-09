# Backend

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

## Notes

- Set `DB_ENGINE=django.db.backends.postgresql` for PostgreSQL.
- Set `CELERY_BROKER_URL` to Redis for async indexing.
- The document retrieval layer is intentionally small and easy to swap for pgvector/Chroma.
- Set `AI_PROVIDER`, `LLM_PROVIDER`, and `EMBEDDING_PROVIDER` to `openai`, `gemini`, `ollama`, or `local`.
