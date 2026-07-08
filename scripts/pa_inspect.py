#!/usr/bin/env python3
"""Hands-on inspection harness for the PA analyst memory loop.

Paste (or URL-fetch) an article you know, run the synthesis, and read the
claims / hypotheses / predictions / narrative it produces so you can judge
accuracy yourself. Talks to the Nexus substrate directly (Postgres), keyed by a
topic slug — no SQLite topic/inbox setup needed.

Run it through ./try.sh (which loads Nexus/.env + venv), e.g.:

    ./try.sh run  --topic demo --url https://example.com/article
    ./try.sh run  --topic demo --file article.txt
    ./try.sh run  --topic demo            # then paste text, end with Ctrl-D
    ./try.sh show --topic demo
    ./try.sh ask  --topic demo "What is the biggest risk?"
    ./try.sh reset --topic demo           # wipe this topic's corpus + analysis
"""

from __future__ import annotations

import argparse
import asyncio
import sys

BAR = "─" * 72


def _read_text(args) -> tuple[str, str, str]:
    """Return (title, url, text) from --url / --file / stdin."""
    if args.url:
        import trafilatura

        downloaded = trafilatura.fetch_url(args.url)
        text = trafilatura.extract(downloaded) if downloaded else None
        if not text:
            sys.exit(f"Could not extract article text from {args.url}")
        return (args.title or args.url, args.url, text)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            return (args.title or args.file, args.url or "", fh.read())
    print("Paste the article text, then press Ctrl-D:\n", file=sys.stderr)
    text = sys.stdin.read()
    if not text.strip():
        sys.exit("No text provided.")
    return (args.title or "pasted-article", args.url or "", text)


def _fmt_claim(i: int, c) -> str:
    ents = ", ".join(getattr(c, "entities", []) or [])
    return (
        f"  [{i}] {c.claim_text}\n"
        f"      confidence={c.confidence:.2f}  source_authority={c.source_authority:.2f}"
        + (f"  entities: {ents}" if ents else "")
    )


def _print_bundle(bundle, tokens: int, result: dict) -> None:
    print(f"\n{BAR}\nSYNTHESIS RESULT  (tokens={tokens})\n{BAR}")
    if bundle.nothing_significant:
        print("nothing_significant = True — nothing worth reporting.")
        return

    print("\n■ NARRATIVE")
    print("  " + bundle.narrative_summary.replace("\n", "\n  "))
    if bundle.change_summary:
        print("\n■ WHAT CHANGED")
        print("  " + bundle.change_summary.replace("\n", "\n  "))

    print(f"\n■ CLAIMS ({len(bundle.claims)})")
    for i, c in enumerate(bundle.claims):
        print(_fmt_claim(i, c))
    if bundle.superseded_claim_ids:
        print(f"  superseded prior claims [P#]: {bundle.superseded_claim_ids}")

    print(f"\n■ HYPOTHESES ({len(bundle.hypotheses)})")
    for h in bundle.hypotheses:
        print(f"  • {h.statement}  (conf={h.confidence:.2f})")
        if h.supporting_claim_ids:
            print(f"      supported by claims {h.supporting_claim_ids}")
        if h.contradicting_claim_ids:
            print(f"      contradicted by claims {h.contradicting_claim_ids}")
        print(f"      invalidated if: {h.invalidation_criteria}")

    print(f"\n■ PREDICTIONS ({len(bundle.predictions)})")
    for p in bundle.predictions:
        print(
            f"  • {p.statement}\n"
            f"      prob={p.probability:.2f}  horizon={p.horizon_days}d  "
            f"resolve: {p.resolution_criteria}"
        )

    print(f"\n■ EVENTS ({len(bundle.events)})")
    for e in bundle.events:
        print(f"  • {e.event_time}: {e.description}")

    print(f"\n■ PERSISTED: {result}")
    if bundle.briefing_markdown:
        print(f"\n{BAR}\nBRIEFING (as delivered)\n{BAR}\n{bundle.briefing_markdown}")


async def _cmd_run(args) -> None:
    from perpetual_analyst import substrate
    from perpetual_analyst.analyst.synthesis import build_focus

    title, url, text = _read_text(args)
    tid = await substrate.get_or_create_watch_topic(args.topic, args.name, description=args.brief)
    print(f"Ingesting '{title}' into topic '{args.topic}' ...", file=sys.stderr)
    doc_id = await substrate.ingest(args.topic, title=title, url=url, text=text, published_at=None)
    msg = f"  ingested doc_id={doc_id}" if doc_id else "  (duplicate — already in corpus)"
    print(msg, file=sys.stderr)

    print("Running synthesis (qwen3.7-max) ...", file=sys.stderr)
    focus = build_focus(args.brief, [title])
    bundle, tokens, ctx = await substrate.synthesize(tid, args.topic, focus, args.k)
    result = await substrate.persist_bundle(tid, bundle, ctx)
    _print_bundle(bundle, tokens, result)


async def _cmd_show(args) -> None:
    from app.db.models import Claim, Hypothesis, NarrativeState, Prediction, WatchTopic
    from sqlalchemy import select

    from perpetual_analyst import substrate

    factory = substrate._session_factory()
    async with factory() as s:
        tid = await s.scalar(select(WatchTopic.id).where(WatchTopic.slug == args.topic))
        if tid is None:
            sys.exit(f"No topic '{args.topic}' — run `run` first.")
        nar = await s.scalar(
            select(NarrativeState)
            .where(NarrativeState.topic_id == tid)
            .order_by(NarrativeState.version.desc())
            .limit(1)
        )
        claims = (
            await s.scalars(
                select(Claim).where(Claim.topic_id == tid, Claim.status == "active")
            )
        ).all()
        hyps = (
            await s.scalars(
                select(Hypothesis).where(Hypothesis.topic_id == tid, Hypothesis.status == "active")
            )
        ).all()
        preds = (
            await s.scalars(
                select(Prediction).where(Prediction.topic_id == tid, Prediction.status == "open")
            )
        ).all()

    print(f"{BAR}\nTOPIC '{args.topic}' — current memory\n{BAR}")
    print(f"\n■ NARRATIVE (v{nar.version if nar else '-'})")
    print("  " + (nar.summary.replace("\n", "\n  ") if nar else "(none)"))
    print(f"\n■ ACTIVE CLAIMS ({len(claims)})")
    for c in claims:
        print(f"  • {c.claim_text}  (conf={c.confidence})")
    print(f"\n■ ACTIVE HYPOTHESES ({len(hyps)})")
    for h in hyps:
        print(f"  • {h.statement}  (conf={h.confidence})")
    print(f"\n■ OPEN PREDICTIONS ({len(preds)})")
    for p in preds:
        print(f"  • {p.statement}  (prob={p.probability})")


async def _cmd_ask(args) -> None:
    from perpetual_analyst import substrate

    res = await substrate.answer(args.topic, args.question, args.k)
    ans = res.get("answer") if isinstance(res, dict) else res
    print(f"{BAR}\nQ: {args.question}\n{BAR}\n{ans}")


async def _cmd_reset(args) -> None:
    from app.db.models import Document, WatchTopic
    from sqlalchemy import delete, select, text

    from perpetual_analyst import substrate

    factory = substrate._session_factory()
    async with factory() as s:
        tid = await s.scalar(select(WatchTopic.id).where(WatchTopic.slug == args.topic))
        await s.execute(delete(Document).where(Document.scope == args.topic))
        if tid is not None:
            # analytical tables cascade on watch_topics delete
            await s.execute(text("DELETE FROM watch_topics WHERE id = :id"), {"id": tid})
        await s.commit()
    print(f"Reset topic '{args.topic}' (corpus + analysis wiped).")


def main() -> None:
    p = argparse.ArgumentParser(description="PA analyst inspection harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--topic", required=True, help="topic slug (lowercase, e.g. demo)")

    r = sub.add_parser("run", help="ingest an article + synthesize + print the analysis")
    add_common(r)
    r.add_argument("--name", default=None, help="display name for the topic")
    r.add_argument("--brief", default=None, help="what you care about (steers retrieval focus)")
    r.add_argument("--url", default=None, help="fetch + extract article from this URL")
    r.add_argument("--file", default=None, help="read article text from this file")
    r.add_argument("--title", default=None, help="article title")
    r.add_argument("-k", type=int, default=15, help="passages to retrieve (default 15)")

    sh = sub.add_parser("show", help="print the topic's current narrative/claims/hypotheses")
    add_common(sh)

    a = sub.add_parser("ask", help="grounded Q&A over the topic corpus")
    add_common(a)
    a.add_argument("question")
    a.add_argument("-k", type=int, default=15)

    rs = sub.add_parser("reset", help="wipe this topic's corpus + analysis")
    add_common(rs)

    args = p.parse_args()
    fn = {"run": _cmd_run, "show": _cmd_show, "ask": _cmd_ask, "reset": _cmd_reset}[args.cmd]
    asyncio.run(fn(args))


if __name__ == "__main__":
    main()
