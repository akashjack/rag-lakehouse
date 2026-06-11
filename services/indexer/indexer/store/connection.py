"""Oracle connection pool using python-oracledb thin mode.

Thin mode requires no Oracle client install — pure Python over the
Oracle Net protocol. Good enough for our throughput (≤ a few hundred
upserts/sec).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import oracledb
import structlog

from indexer.config import IndexerSettings

if TYPE_CHECKING:
    from collections.abc import Iterator


log = structlog.get_logger(__name__)


def build_pool(settings: IndexerSettings) -> oracledb.ConnectionPool:
    """Construct a connection pool. Thin mode (no client install needed)."""
    pool = oracledb.create_pool(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
        min=settings.oracle_pool_min,
        max=settings.oracle_pool_max,
        increment=1,
        getmode=oracledb.POOL_GETMODE_WAIT,
    )
    log.info(
        "oracle.pool.created",
        dsn=settings.oracle_dsn,
        user=settings.oracle_user,
        min=settings.oracle_pool_min,
        max=settings.oracle_pool_max,
    )
    return pool


@contextmanager
def acquire(pool: oracledb.ConnectionPool) -> Iterator[oracledb.Connection]:
    """Context manager that acquires a connection and returns it to the pool."""
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)
