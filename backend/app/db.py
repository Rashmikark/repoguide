from typing import Callable, TypeVar

import psycopg
from psycopg_pool import ConnectionPool

from backend.app.config import settings

T = TypeVar("T")

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=5,
    check=ConnectionPool.check_connection,   # test each connection before lending it
    max_idle=300,                            # drop connections idle > 5 min
    open=False,                              # opened at app startup, not at import
)


def with_conn(fn: Callable[[psycopg.Connection], T], retries: int = 1) -> T:
    """Run fn with a pooled connection; retry once if the connection dropped.
    Only for reads and idempotent writes - a retried write could run twice."""
    for attempt in range(retries + 1):
        try:
            with pool.connection() as conn:
                return fn(conn)
        except psycopg.OperationalError:
            if attempt == retries:
                raise
    raise RuntimeError("unreachable")