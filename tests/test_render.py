from __future__ import annotations

from perpetual_analyst.report.render import render_citations


def _item(db, source_id, title, url):
    cur = db.execute(
        "INSERT INTO items (source_id, content_hash, title, url) VALUES (?, ?, ?, ?)",
        (source_id, f"hash_{title}", title, url),
    )
    db.commit()
    return cur.lastrowid


def test_tags_become_numbered_footnotes(db, sample_source):
    a = _item(db, sample_source, "Alpha Post", "https://example.com/a")
    b = _item(db, sample_source, "Beta Post", "https://example.com/b")
    text = f"First [item:{a}] then [item:{b}] then [item:{a}] again."
    rendered = render_citations(text, db)
    assert "[^1]" in rendered and "[^2]" in rendered
    assert rendered.count("[^1]") == 3  # two inline occurrences + one footnote definition
    assert "## Sources reviewed" in rendered
    assert "[^1]: Alpha Post — https://example.com/a" in rendered
    assert "[^2]: Beta Post — https://example.com/b" in rendered


def test_unknown_item_id_renders_plain(db):
    rendered = render_citations("See [item:999].", db)
    assert "item:999" in rendered
    assert "[^" not in rendered
    assert "## Sources reviewed" not in rendered


def test_obs_and_thesis_tags_untouched(db, sample_source):
    a = _item(db, sample_source, "Alpha", None)
    rendered = render_citations(f"[obs:3] and [thesis:4] and [item:{a}]", db)
    assert "[obs:3]" in rendered and "[thesis:4]" in rendered
    assert "(no url)" in rendered


def test_no_tags_passthrough(db):
    assert render_citations("Plain text.", db) == "Plain text."
