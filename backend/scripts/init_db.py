from pathlib import Path

import psycopg

from backend.app.config import settings

schema = Path("backend/db/schema.sql").read_text(encoding="utf-8")

with psycopg.connect(settings.database_url) as conn:
    conn.execute(schema)
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' ORDER BY table_name"
    ).fetchall()
    print("Tables:", [r[0] for r in rows])