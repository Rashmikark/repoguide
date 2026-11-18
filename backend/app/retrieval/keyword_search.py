import psycopg

from backend.app.ingest.search_text import expand_identifiers
from backend.app.retrieval.vector_search import Hit


def keyword_terms(question: str) -> str:
    return expand_identifiers(question)


def keyword_search(conn: psycopg.Connection, repo_id: int, question: str, k: int = 5) -> list[Hit]:
    terms = keyword_terms(question)
    if not terms.strip():
        return []
    rows = conn.execute(
        """
        WITH q AS (
            -- stem + drop stopwords with 'english', then turn AND into OR.
            -- 'simple' re-parses the already-stemmed words without changing them.
            SELECT to_tsquery('simple',
                   replace(plainto_tsquery('english', %s)::text, ' & ', ' | ')) AS query
        )
        SELECT c.id, c.path, c.start_line, c.end_line, c.kind, c.symbol, c.content,
               ts_rank_cd(c.search_tsv, q.query, 1) AS score
        FROM chunks c, q
        WHERE c.repo_id = %s AND c.search_tsv @@ q.query
        ORDER BY score DESC, c.id
        LIMIT %s
        """,
        (terms, repo_id, k),
    ).fetchall()
    return [Hit(*row) for row in rows]