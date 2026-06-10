from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class User:
    id: int
    telegram_chat_id: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> User:
        return cls(**dict(row))


@dataclass
class Topic:
    id: int
    user_id: int | None
    slug: str
    name: str
    brief: str | None
    active: int
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Topic:
        return cls(**dict(row))


@dataclass
class Source:
    id: int
    type: str
    url: str | None
    name: str | None
    active: int
    last_fetched_at: str | None
    fetch_error_count: int
    quality_score: float | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Source:
        return cls(**dict(row))


@dataclass
class Item:
    id: int
    source_id: int | None
    url: str | None
    content_hash: str
    title: str | None
    author: str | None
    published_at: str | None
    fetched_at: str
    raw_text: str | None
    triage_summary: str | None
    triage_score: float | None
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Item:
        return cls(**dict(row))


@dataclass
class Dossier:
    topic_id: int
    content: str
    updated_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Dossier:
        return cls(**dict(row))


@dataclass
class Thesis:
    id: int
    topic_id: int
    statement: str
    rationale: str | None
    confidence: float | None
    status: str
    created_at: str
    updated_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Thesis:
        return cls(**dict(row))


@dataclass
class ThesisUpdate:
    id: int
    thesis_id: int
    change: str
    confidence_before: float | None
    confidence_after: float | None
    triggered_by_item_id: int | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ThesisUpdate:
        return cls(**dict(row))


@dataclass
class Observation:
    id: int
    topic_id: int
    kind: str
    content: str
    importance: int
    source_item_ids: str | None  # JSON array string
    status: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Observation:
        return cls(**dict(row))


@dataclass
class Report:
    id: int
    user_id: int | None
    report_date: str
    digest_text: str | None
    full_markdown: str | None
    delivered_at: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Report:
        return cls(**dict(row))
