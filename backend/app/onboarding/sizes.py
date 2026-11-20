"""Line count per file = largest end_line among its chunks (the chunker misses 0 lines).
LEFT JOIN so a file with no chunks (e.g. an empty __init__.py) is kept with 0 lines."""

SIZES_SQL = """
SELECT f.path, COALESCE(MAX(c.end_line), 0)
FROM files f
LEFT JOIN chunks c ON c.file_id = f.id
WHERE f.repo_id = %s
GROUP BY f.path
"""


def load_sizes(conn, repo_id: int) -> dict[str, int]:
    rows = conn.execute(SIZES_SQL, (repo_id,)).fetchall()
    return {path: int(n) for path, n in rows}