"""Single boundary between PA and the Nexus memory substrate (Postgres/pgvector)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_NEXUS_ENV = Path(__file__).resolve().parents[2] / "Nexus" / ".env"
load_dotenv(_NEXUS_ENV)

from app.api.routes_ingestion import (  # noqa: E402
    _get_or_create_manual_source,
    _persist_document,
)
from app.config import settings  # noqa: E402
from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.intelligence.embedder import Embedder  # noqa: E402
from app.intelligence.sentence_window import (  # noqa: E402
    ingest_sentence_spans,
    retrieve_windows,
)

_engine: AsyncEngine | None = None
_sf: async_sessionmaker[AsyncSession] | None = None
_emb: Embedder | None = None
_source_id: uuid.UUID | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_engine(str(settings.database_url))
    return _engine


def _session_factory() -> async_sessionmaker[AsyncSession]:
    global _sf
    if _sf is None:
        _sf = make_session_factory(_get_engine())
    return _sf


def _embedder() -> Embedder:
    global _emb
    if _emb is None:
        _emb = Embedder(
            settings.t1_model,
            truncate_dim=settings.t1_truncate_dim or None,
        )
    return _emb


async def _get_source_id() -> uuid.UUID:
    global _source_id
    if _source_id is None:
        factory = _session_factory()
        async with factory() as session:
            source = await _get_or_create_manual_source(
                session,
                name="perpetual-analyst",
                domain_pack=settings.default_pack_id,
            )
            await session.commit()
            _source_id = source.id
    return _source_id


async def ingest(
    scope: str,
    *,
    title: str,
    url: str,
    text: str,
    published_at: datetime | None = None,
) -> uuid.UUID | None:
    source_id = await _get_source_id()
    factory = _session_factory()
    embedder = _embedder()

    async with factory() as session:
        persisted = await _persist_document(
            session,
            source_id=source_id,
            title=title,
            url=url,
            raw_text=text,
            clean_text=text,
            published_at=published_at,
        )
        if persisted is None:
            return None

        persisted.scope = scope
        await session.commit()
        await session.refresh(persisted)
        document_id = persisted.id

    await ingest_sentence_spans(factory, embedder, document_id, text)
    return document_id


async def retrieve(
    scope: str,
    query: str,
    k: int | None = None,
) -> list[dict[str, Any]]:
    factory = _session_factory()
    embedder = _embedder()

    async with factory() as session:
        return await retrieve_windows(
            session,
            embedder,
            query,
            fetch_k=settings.sentence_window_fetch_k,
            window=settings.sentence_window_size,
            k=k or settings.sentence_window_top_k,
            as_of=None,
            hybrid=settings.sentence_window_hybrid,
            scope=scope,
        )
