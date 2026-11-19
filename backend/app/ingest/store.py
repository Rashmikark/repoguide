import psycopg

from backend.app.ingest.chunker import Chunk
from backend.app.ingest.embedder import chunk_embedding_text, embed_texts
from backend.app.ingest.repo_loader import LoadedRepo, SourceFile
from backend.app.ingest.search_text import build_search_text

EMBED_PAGE = 200   # chunks read from the DB and committed per round


def to_pgvector(v: list[float]) -> str:
    return "[" + ",".join(map(str, v)) + "]"


def save_repo(conn: psycopg.Connection, repo: LoadedRepo,
              file_chunks: list[tuple[SourceFile, list[Chunk]]]) -> int:
    url = f"https://github.com/{repo.owner}/{repo.name}"
    repo_id = conn.execute(
        """
        INSERT INTO repos (url, owner, name, commit_sha, status, heartbeat_at)
        VALUES (%s, %s, %s, %s, 'indexing', now())
        ON CONFLICT (url) DO UPDATE
            SET commit_sha = EXCLUDED.commit_sha, status = 'indexing',
                error = NULL, heartbeat_at = now()
        RETURNING id
        """,
        (url, repo.owner, repo.name, repo.commit_sha),
    ).fetchone()[0]

    # Re-index = start clean. Chunks are removed by ON DELETE CASCADE.
    conn.execute("DELETE FROM files WHERE repo_id = %s", (repo_id,))

    for f, chunks in file_chunks:
        file_id = conn.execute(
            "INSERT INTO files (repo_id, path, language, size_bytes) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (repo_id, f.path, f.language, f.size_bytes),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (repo_id, file_id, path, start_line, end_line, "
                "kind, symbol, content, search_text) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(repo_id, file_id, c.path, c.start_line, c.end_line, c.kind, c.symbol,
                  c.content.replace("\x00", ""),
                  build_search_text(c.path, c.symbol, c.content.replace("\x00", "")))
                 for c in chunks],
            )
    conn.commit()
    return repo_id


def embed_missing(conn: psycopg.Connection, repo_id: int) -> int:
    done = 0
    while True:
        rows = conn.execute(
            "SELECT id, path, kind, symbol, content FROM chunks "
            "WHERE repo_id = %s AND embedding IS NULL ORDER BY id LIMIT %s",
            (repo_id, EMBED_PAGE),
        ).fetchall()
        if not rows:
            return done
        texts = [chunk_embedding_text(p, k, s, c) for _, p, k, s, c in rows]
        vectors = embed_texts(texts, "RETRIEVAL_DOCUMENT")
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE chunks SET embedding = %s::vector WHERE id = %s",
                [(to_pgvector(v), row[0]) for v, row in zip(vectors, rows)],
            )
        conn.commit()          # each page is saved, so a crash loses nothing
        conn.execute("UPDATE repos SET heartbeat_at = now() WHERE id = %s", (repo_id,))
        conn.commit()          # heartbeat: "this job is still alive"
        done += len(rows)
        print(f"  embedded {done} chunks")


def mark_ready(conn: psycopg.Connection, repo_id: int) -> None:
    conn.execute(
        """
        UPDATE repos SET status = 'ready', indexed_at = now(), heartbeat_at = now(),
            file_count  = (SELECT count(*) FROM files  WHERE repo_id = %s),
            chunk_count = (SELECT count(*) FROM chunks WHERE repo_id = %s)
        WHERE id = %s
        """,
        (repo_id, repo_id, repo_id),
    )
    conn.commit()


def mark_failed(conn: psycopg.Connection, repo_id: int, error: str) -> None:
    conn.rollback()   # clear the failed transaction before writing
    conn.execute(
        "UPDATE repos SET status = 'failed', error = %s WHERE id = %s",
        (error[:1000], repo_id),
    )
    conn.commit()