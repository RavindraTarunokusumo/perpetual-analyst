"""Single boundary between PA and the Nexus memory substrate (Postgres/pgvector)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from perpetual_analyst.analyst.schemas import NarrativeUpdate

_NEXUS_ENV = Path(__file__).resolve().parents[2] / "Nexus" / ".env"
load_dotenv(_NEXUS_ENV)

from app.api.routes_ingestion import (  # noqa: E402
    _get_or_create_manual_source,
    _persist_document,
)
from app.config import settings  # noqa: E402
from app.db.models import Claim, Hypothesis, NarrativeState, Prediction, WatchTopic  # noqa: E402
from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.intelligence.embedder import Embedder  # noqa: E402
from app.intelligence.llm_client import LLMClient, LLMSchemaError  # noqa: E402
from app.intelligence.sentence_window import (  # noqa: E402
    ingest_sentence_spans,
    retrieve_windows,
)

_engine: AsyncEngine | None = None
_sf: async_sessionmaker[AsyncSession] | None = None
_loop_id: int | None = None
_emb: Embedder | None = None
_source_id: uuid.UUID | None = None

# ruff: noqa: E501
_SYNTHESIS_SYSTEM = (
    "You are a perpetual analyst maintaining an evolving, source-grounded understanding of ONE topic "
    "across daily sessions. You are given your current narrative (prior belief), the active claims, "
    "competing hypotheses, open predictions, and newly retrieved source passages. Produce a "
    "NarrativeUpdate: (1) extract source-backed CLAIMS and time-stamped EVENTS from the passages, each "
    "with confidence and source_authority (assign LOW source_authority to self-interested/vendor/promotional "
    "sources); (2) list indices of prior claims that new evidence SUPERSEDES or CONTRADICTS; (3) write a NEW "
    "narrative_summary and a change_summary stating what changed versus the prior narrative and WHY, citing "
    "the claims/sources; (4) update competing HYPOTHESES (supporting/contradicting claim sets + confidence; "
    "keep at most 7 active; retire per invalidation_criteria); (5) emit or adjust scored PREDICTIONS. Keep "
    "CLAIMS (source-backed) separate from INTERPRETATION (narrative/hypotheses). Never fabricate. If today's "
    "passages do not materially change the understanding, set nothing_significant=true and leave "
    "briefing_markdown empty. Otherwise write briefing_markdown as the user-facing daily briefing."
)

_SCHEMA_RETRY_SUFFIX = "\n\nReturn ONLY valid JSON matching the schema."


def _session_factory() -> async_sessionmaker[AsyncSession]:
    # asyncpg engines are bound to the event loop they were created on. daily_run
    # calls asyncio.run() once per topic (a fresh loop each time), so cache the
    # engine per running loop and rebuild when the loop changes.
    global _engine, _sf, _loop_id
    loop_id = id(asyncio.get_running_loop())
    if _sf is None or _loop_id != loop_id:
        _engine = make_engine(str(settings.database_url))
        _sf = make_session_factory(_engine)
        _loop_id = loop_id
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


async def get_or_create_watch_topic(
    slug: str,
    name: str,
    *,
    description: str | None = None,
    domain: str | None = None,
) -> uuid.UUID:
    # ponytail: no concurrency guard; retry on unique-violation only if PA runs topics concurrently
    factory = _session_factory()
    async with factory() as session:
        existing = await session.scalar(select(WatchTopic).where(WatchTopic.slug == slug))
        if existing is not None:
            return existing.id

        topic = WatchTopic(slug=slug, name=name, description=description, domain=domain)
        session.add(topic)
        await session.commit()
        await session.refresh(topic)
        return topic.id


def _format_date(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.date().isoformat()


def _build_synthesis_user_prompt(
    narrative: NarrativeState | None,
    claims: list[Claim],
    hypotheses: list[Hypothesis],
    predictions: list[Prediction],
    windows: list[dict[str, Any]],
) -> str:
    sections: list[str] = []

    if narrative is not None:
        sections.append(f"CURRENT NARRATIVE\n{narrative.summary}")
    else:
        sections.append("CURRENT NARRATIVE\n(none yet)")

    if claims:
        claim_lines = [f"[{i}] {c.claim_text} (conf={c.confidence})" for i, c in enumerate(claims)]
        sections.append("ACTIVE CLAIMS\n" + "\n".join(claim_lines))
    else:
        sections.append("ACTIVE CLAIMS\n(none)")

    if hypotheses:
        hyp_lines = [
            f"- {h.statement} (conf={h.confidence}, status={h.status})" for h in hypotheses
        ]
        sections.append("ACTIVE HYPOTHESES\n" + "\n".join(hyp_lines))
    else:
        sections.append("ACTIVE HYPOTHESES\n(none)")

    if predictions:
        pred_lines = [
            f"- {p.statement} (prob={p.probability}, horizon={p.horizon_days}d)"
            for p in predictions
        ]
        sections.append("OPEN PREDICTIONS\n" + "\n".join(pred_lines))
    else:
        sections.append("OPEN PREDICTIONS\n(none)")

    if windows:
        passage_lines: list[str] = []
        for i, w in enumerate(windows):
            date_str = _format_date(w.get("published_at"))
            header = f"--- Passage {i + 1}"
            if date_str:
                header += f" ({date_str})"
            header += " ---"
            text = w.get("text", "")
            passage_lines.append(f"{header}\n{text}")
        sections.append("NEW SOURCE PASSAGES\n" + "\n\n".join(passage_lines))
    else:
        sections.append("NEW SOURCE PASSAGES\n(none retrieved)")

    schema = json.dumps(NarrativeUpdate.model_json_schema(), separators=(",", ":"))
    preamble = f"Produce a valid JSON NarrativeUpdate matching this schema:\n{schema}"
    return preamble + "\n\n" + "\n\n".join(sections)


async def synthesize(
    topic_id: uuid.UUID,
    scope: str,
    focus: str,
    k: int | None = None,
) -> tuple[NarrativeUpdate, int]:
    windows = await retrieve(scope, focus, k)

    factory = _session_factory()
    async with factory() as session:
        narrative = await session.scalar(
            select(NarrativeState)
            .where(NarrativeState.topic_id == topic_id)
            .order_by(desc(NarrativeState.version))
            .limit(1)
        )
        claims = list(
            (
                await session.scalars(
                    select(Claim)
                    .where(Claim.topic_id == topic_id, Claim.status == "active")
                    .order_by(desc(Claim.created_at))
                    .limit(50)
                )
            ).all()
        )
        hypotheses = list(
            (
                await session.scalars(
                    select(Hypothesis)
                    .where(Hypothesis.topic_id == topic_id, Hypothesis.status == "active")
                    .order_by(desc(Hypothesis.created_at))
                    .limit(50)
                )
            ).all()
        )
        predictions = list(
            (
                await session.scalars(
                    select(Prediction)
                    .where(Prediction.topic_id == topic_id, Prediction.status == "open")
                    .order_by(desc(Prediction.created_at))
                    .limit(50)
                )
            ).all()
        )

    user = _build_synthesis_user_prompt(narrative, claims, hypotheses, predictions, windows)
    client = LLMClient(settings.llm_api_key, _session_factory(), base_url=settings.llm_base_url)

    try:
        result, tokens = await client.complete_json(
            model=settings.t3_model,
            system=_SYNTHESIS_SYSTEM,
            user=user,
            response_model=NarrativeUpdate,
            run_type="narrative_update",
            max_tokens=4000,
        )
    except LLMSchemaError:
        result, tokens = await client.complete_json(
            model=settings.t3_model,
            system=_SYNTHESIS_SYSTEM + _SCHEMA_RETRY_SUFFIX,
            user=user,
            response_model=NarrativeUpdate,
            run_type="narrative_update",
            max_tokens=4000,
        )

    return result, tokens
