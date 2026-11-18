from dataclasses import dataclass

import psycopg

from backend.app.ingest.embedder import embed_texts
from backend.app.ingest.store import to_pgvector


@dataclass
class Hit:
    chunk_id: int
    path: str
    start_line: int
    end_line: int
    kind: str
    symbol: str | None
    content: str
    score: float          # cosine similarity: higher = closer; only for ranking


def embed_query(question: str) -> str:
    return to_pgvector(embed_texts([question], "RETRIEVAL_QUERY")[0])


def vector_search(conn: psycopg.Connection, repo_id: int, query_vec: str, k: int = 5) -> list[Hit]:
    # Keep scanning the HNSW index until k rows survive the repo filter.
    conn.execute("SET hnsw.iterative_scan = strict_order")
    rows = conn.execute(
        """
        SELECT id, path, start_line, end_line, kind, symbol, content,
               1 - (embedding <=> %s::vector) AS score
        FROM chunks
        WHERE repo_id = %s AND embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vec, repo_id, query_vec, k),
    ).fetchall()
    return [Hit(*row) for row in rows]