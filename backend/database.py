import os
import socket
import sqlite3
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

_ROOT = Path(__file__).resolve().parents[1]

def _resolve_database_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/agenticdb"
    )
    if "postgresql" in url:
        try:
            with socket.create_connection(("127.0.0.1", 5432), timeout=0.5) as s:
                s.settimeout(0.5)
                # Send Postgres SSLRequest packet; real Postgres replies b'S' or b'N', dead Docker proxy returns b'' (EOF)
                s.sendall(b"\x00\x00\x00\x08\x04\xd2\x16/")
                resp = s.recv(1)
                if resp in (b"S", b"N"):
                    return url
                raise ConnectionError("Port 5432 closed with EOF (Docker proxy without running container)")
        except Exception:
            fallback_path = _ROOT / "agenticdb_local.sqlite"
            print(f"[DB] Port 5432 unreachable (Docker stopped); falling back to {fallback_path.name}")
            return f"sqlite+aiosqlite:///{fallback_path}"
    return url

# Database connection URL targeting PostgreSQL AgenticDB (or automatic SQLite fallback)
DATABASE_URL = _resolve_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    """Dependency for obtaining async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
