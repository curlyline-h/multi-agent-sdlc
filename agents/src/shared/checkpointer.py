import sqlite3
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

_configured_paths: set[str] = set()


def configure_sqlite_pragmas(db_path: str = "checkpoints.sqlite") -> None:
    """
    Configures SQLite WAL mode and busy_timeout once per database path
    to prevent 'database is locked' errors under concurrent async access.
    """
    if db_path in _configured_paths:
        return
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.commit()
    finally:
        conn.close()
    _configured_paths.add(db_path)


@asynccontextmanager
async def get_async_checkpointer(db_path: str = "checkpoints.sqlite"):
    """
    Yields a properly configured AsyncSqliteSaver with WAL mode and busy_timeout.
    """
    configure_sqlite_pragmas(db_path)
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        if hasattr(checkpointer, "conn") and checkpointer.conn is not None:
            try:
                await checkpointer.conn.execute("PRAGMA busy_timeout=10000;")
            except Exception:
                pass
        await checkpointer.setup()
        yield checkpointer
