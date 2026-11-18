import psycopg

from backend.app.config import settings
from backend.app.ingest.search_text import build_search_text

with psycopg.connect(settings.database_url) as conn:
    rows = conn.execute(
        "SELECT id, path, symbol, content FROM chunks WHERE search_text IS NULL"
    ).fetchall()
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE chunks SET search_text = %s WHERE id = %s",
            [(build_search_text(p, s, c), i) for i, p, s, c in rows],
        )
    print(f"backfilled {len(rows)} chunks")