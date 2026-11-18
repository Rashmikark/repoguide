import psycopg

from backend.app.config import settings

with psycopg.connect(settings.database_url) as conn:
    version = conn.execute("SELECT version()").fetchone()[0]
    print("Connected:", version[:40])

    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    ext = conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()[0]
    print("pgvector version:", ext)