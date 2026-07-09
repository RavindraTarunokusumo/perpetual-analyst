from __future__ import annotations

import ipaddress
import socket
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

from perpetual_analyst.store.models import SourceCandidate

ALLOWED_SOURCE_TYPES = {"rss", "web"}
MAX_REDIRECTS = 3


class CandidateApprovalError(ValueError):
    pass


@dataclass
class FetchValidationResult:
    url: str
    status_code: int


def _is_blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise CandidateApprovalError(f"Invalid resolved IP address: {value}") from exc
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_host(hostname: str, resolver=socket.getaddrinfo) -> None:
    lowered = hostname.lower().rstrip(".")
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".localhost"):
        raise CandidateApprovalError("URL host is not allowed")

    try:
        ipaddress.ip_address(lowered)
    except ValueError:
        try:
            infos = resolver(lowered, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise CandidateApprovalError("URL host did not resolve") from exc
        resolved = {info[4][0] for info in infos}
        if not resolved:
            raise CandidateApprovalError("URL host did not resolve")
        blocked = [addr for addr in resolved if _is_blocked_ip(addr)]
        if blocked:
            raise CandidateApprovalError("URL resolves to a private or reserved address")
    else:
        if _is_blocked_ip(lowered):
            raise CandidateApprovalError("URL host is a private or reserved address")


def validate_public_source_url(url: str | None, resolver=socket.getaddrinfo) -> str:
    if not url:
        raise CandidateApprovalError("URL is required")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise CandidateApprovalError("URL must use http or https")
    if not parsed.hostname:
        raise CandidateApprovalError("URL host is required")
    if parsed.username or parsed.password:
        raise CandidateApprovalError("URL credentials are not allowed")

    _validate_host(parsed.hostname, resolver=resolver)
    return url


def fetch_public_source_url(
    url: str,
    *,
    resolver=socket.getaddrinfo,
    http_get=None,
    timeout: float = 10.0,
    max_redirects: int = MAX_REDIRECTS,
) -> FetchValidationResult:
    current_url = validate_public_source_url(url, resolver=resolver)

    client = None
    if http_get is None:
        import httpx

        client = httpx.Client(follow_redirects=False, timeout=timeout, trust_env=False)

        def http_get(target: str):
            return client.get(target)

    try:
        for _ in range(max_redirects + 1):
            response = http_get(current_url)
            status = int(response.status_code)
            if 300 <= status < 400:
                location = response.headers.get("location")
                if not location:
                    raise CandidateApprovalError("Redirect response missing Location header")
                current_url = validate_public_source_url(
                    urljoin(current_url, location),
                    resolver=resolver,
                )
                continue
            if status >= 400:
                raise CandidateApprovalError(f"URL fetch failed with HTTP {status}")
            return FetchValidationResult(url=current_url, status_code=status)

        raise CandidateApprovalError("Too many redirects")
    finally:
        if client is not None:
            client.close()


def _candidate_from_db(conn: sqlite3.Connection, candidate_id: int) -> SourceCandidate:
    row = conn.execute("SELECT * FROM source_candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        raise CandidateApprovalError(f"Source candidate {candidate_id} not found")
    return SourceCandidate.from_row(row)


def _existing_topic_source(
    conn: sqlite3.Connection, topic_id: int | None, url: str | None
) -> int | None:
    row = conn.execute(
        """SELECT s.id
           FROM sources s
           JOIN topic_sources ts ON ts.source_id = s.id
           WHERE ts.topic_id = ? AND s.url = ?
           ORDER BY s.id
           LIMIT 1""",
        (topic_id, url),
    ).fetchone()
    return int(row["id"]) if row else None


def approve_source_candidate(
    conn: sqlite3.Connection,
    candidate_id: int,
    *,
    source_type: str = "rss",
    note: str | None = None,
    fetcher=fetch_public_source_url,
    resolver=socket.getaddrinfo,
) -> int:
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise CandidateApprovalError(f"Unsupported source type: {source_type}")

    candidate = _candidate_from_db(conn, candidate_id)
    if candidate.status == "rejected":
        raise CandidateApprovalError("Rejected candidates cannot be approved")
    if not candidate.topic_id:
        raise CandidateApprovalError("Candidate has no topic")
    if not candidate.url:
        raise CandidateApprovalError("Candidate has no URL")

    existing_source_id = _existing_topic_source(conn, candidate.topic_id, candidate.url)
    if candidate.status == "approved" and existing_source_id is not None:
        return existing_source_id

    fetcher(candidate.url, resolver=resolver)
    reviewed_at = datetime.now(UTC).isoformat()

    with conn:
        source_id = _existing_topic_source(conn, candidate.topic_id, candidate.url)
        if source_id is None:
            cur = conn.execute(
                """INSERT INTO sources
                       (type, url, name, active, status, probation_until)
                   VALUES (?, ?, ?, 1, 'probation', datetime('now', '+21 days'))""",
                (source_type, candidate.url, candidate.domain or candidate.url),
            )
            source_id = int(cur.lastrowid)

        conn.execute(
            "INSERT OR IGNORE INTO topic_sources (topic_id, source_id) VALUES (?, ?)",
            (candidate.topic_id, source_id),
        )
        conn.execute(
            """UPDATE source_candidates
               SET status = 'approved', reviewed_at = ?, review_note = ?
               WHERE id = ?""",
            (reviewed_at, note, candidate_id),
        )

    return source_id


def dismiss_source_candidate(
    conn: sqlite3.Connection,
    candidate_id: int,
    *,
    note: str | None = None,
) -> None:
    candidate = _candidate_from_db(conn, candidate_id)
    if candidate.status == "approved":
        raise CandidateApprovalError("Approved candidates cannot be dismissed")

    reviewed_at = datetime.now(UTC).isoformat()
    with conn:
        conn.execute(
            """UPDATE source_candidates
               SET status = 'rejected', reviewed_at = ?, review_note = ?
               WHERE id = ?""",
            (reviewed_at, note, candidate_id),
        )
