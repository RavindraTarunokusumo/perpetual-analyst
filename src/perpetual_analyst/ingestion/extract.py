"""Text extraction helpers: trafilatura for web pages, pypdf for PDFs."""

# TODO (Task 5/7): Implement
# - extract_url(url: str) -> str | None
#   - use trafilatura.fetch_url + trafilatura.extract
#   - return None on failure
#
# - extract_pdf(path: Path) -> str
#   - use pypdf.PdfReader
#   - join all page text
