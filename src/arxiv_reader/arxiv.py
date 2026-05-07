from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import gzip
import io
import os
import re
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_EPRINT = "https://arxiv.org/e-print/{paper_id}"
DEFAULT_USER_AGENT = "AIArxivReader/0.1 (https://github.com/Rubii115/AIArxivReader; mailto:local@example.invalid)"
RETRYABLE_HTTP_STATUS = {429, 503}
MAX_HTTP_ATTEMPTS = 5
ARXIV_API_MIN_INTERVAL_SECONDS = 3.1
_ARXIV_API_LOCK = threading.Lock()
_LAST_ARXIV_API_REQUEST_AT = 0.0


@dataclass(frozen=True)
class Paper:
    arxiv_id: str
    title: str
    summary: str
    authors: tuple[str, ...]
    published: str
    updated: str
    categories: tuple[str, ...]
    pdf_url: str
    abs_url: str


@dataclass(frozen=True)
class SearchResult:
    papers: list[Paper]
    total_results: int


def normalize_arxiv_id(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://arxiv\.org/(abs|pdf|e-print)/", "", value)
    value = value.removesuffix(".pdf")
    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)", value)
    if not match:
        raise ValueError(f"Not an arXiv id or URL: {value}")
    return match.group(1)


def build_interest_query(categories: tuple[str, ...], keywords: tuple[str, ...], day: date) -> str:
    start = day.strftime("%Y%m%d") + "0000"
    end = day.strftime("%Y%m%d") + "2359"
    parts = [f"submittedDate:[{start} TO {end}]"]

    interest_terms: list[str] = []
    interest_terms.extend(f"cat:{category}" for category in categories)
    interest_terms.extend(f'all:"{keyword}"' for keyword in keywords)
    if interest_terms:
        parts.append("(" + " OR ".join(interest_terms) + ")")
    return " AND ".join(parts)


def search(query: str, *, max_results: int = 10, sort_by: str = "relevance", progress=None) -> list[Paper]:
    return search_with_total(query, max_results=max_results, sort_by=sort_by, progress=progress).papers


def search_with_total(query: str, *, max_results: int = 10, sort_by: str = "relevance", start: int = 0, progress=None) -> SearchResult:
    params = {
        "search_query": query,
        "start": str(start),
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    xml_bytes = _http_get(url, progress=progress)
    return SearchResult(parse_atom(xml_bytes), parse_total_results(xml_bytes))


def get_paper(paper_id: str, *, progress=None) -> Paper:
    normalized = normalize_arxiv_id(paper_id)
    try:
        results = search(f"id:{normalized}", max_results=1, progress=progress)
    except RuntimeError:
        return get_paper_from_abs_page(normalized, progress=progress)
    if not results:
        return get_paper_from_abs_page(normalized, progress=progress)
    return results[0]


def get_paper_from_abs_page(paper_id: str, *, progress=None) -> Paper:
    normalized = normalize_arxiv_id(paper_id)
    url = f"https://arxiv.org/abs/{urllib.parse.quote(normalized)}"
    html = _http_get(url, progress=progress).decode("utf-8", errors="ignore")
    title = _html_text(_match_html(html, r'<h1 class="title mathjax">\s*<span class="descriptor">Title:</span>(.*?)</h1>'))
    summary = _html_text(
        _match_html(html, r'<blockquote class="abstract mathjax">\s*<span class="descriptor">Abstract:</span>(.*?)</blockquote>')
    )
    authors_html = _match_html(html, r'<div class="authors">\s*<span class="descriptor">Authors:</span>(.*?)</div>')
    authors = tuple(_html_text(match) for match in re.findall(r"<a\b[^>]*>(.*?)</a>", authors_html, flags=re.S))
    if not authors and authors_html:
        authors = tuple(part.strip() for part in _html_text(authors_html).split(",") if part.strip())
    categories = tuple(
        re.findall(r"\(([a-z-]+(?:\.[A-Z]{2})?)\)", _html_text(_match_html(html, r'<td class="tablecell subjects">(.*?)</td>')), flags=re.S)
    )
    if not categories:
        categories = tuple(re.findall(r"\[([a-z-]+(?:\.[A-Z]{2})?)\]", html))
    submitted = _submitted_date(_html_text(_match_html(html, r'<div class="dateline">(.*?)</div>')))
    if not title:
        raise LookupError(f"No arXiv paper found for {paper_id}")
    return Paper(
        arxiv_id=normalized,
        title=title,
        summary=summary,
        authors=authors,
        published=submitted,
        updated=submitted,
        categories=categories,
        pdf_url=f"https://arxiv.org/pdf/{normalized}",
        abs_url=f"https://arxiv.org/abs/{normalized}",
    )


def download_source(paper_id: str, destination: str | Path | None = None, *, progress=None) -> Path:
    normalized = normalize_arxiv_id(paper_id)
    raw = _http_get(ARXIV_EPRINT.format(paper_id=urllib.parse.quote(normalized)), progress=progress)
    target = Path(destination) if destination else Path(tempfile.mkdtemp(prefix="arxiv-reader-")) / normalized.replace("/", "_")
    target.mkdir(parents=True, exist_ok=True)

    fileobj = io.BytesIO(raw)
    try:
        with tarfile.open(fileobj=fileobj, mode="r:*") as archive:
            _safe_extract(archive, target)
        return target
    except tarfile.TarError:
        pass

    try:
        payload = gzip.decompress(raw)
    except gzip.BadGzipFile:
        payload = raw

    tex_name = target / f"{normalized.replace('/', '_')}.tex"
    tex_name.write_bytes(payload)
    return target


def parse_atom(xml_bytes: bytes) -> list[Paper]:
    root = ET.fromstring(xml_bytes)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", ns):
        raw_id = _text(entry, "atom:id", ns)
        arxiv_id = raw_id.rsplit("/", 1)[-1]
        links = entry.findall("atom:link", ns)
        pdf_url = ""
        for link in links:
            if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                pdf_url = link.attrib.get("href", "")
                break
        categories = tuple(cat.attrib.get("term", "") for cat in entry.findall("atom:category", ns) if cat.attrib.get("term"))
        papers.append(
            Paper(
                arxiv_id=arxiv_id,
                title=_clean_space(_text(entry, "atom:title", ns)),
                summary=_clean_space(_text(entry, "atom:summary", ns)),
                authors=tuple(_clean_space(_text(author, "atom:name", ns)) for author in entry.findall("atom:author", ns)),
                published=_format_date(_text(entry, "atom:published", ns)),
                updated=_format_date(_text(entry, "atom:updated", ns)),
                categories=categories,
                pdf_url=pdf_url,
                abs_url=f"https://arxiv.org/abs/{arxiv_id}",
            )
        )
    return papers


def parse_total_results(xml_bytes: bytes) -> int:
    root = ET.fromstring(xml_bytes)
    ns = {"opensearch": "http://a9.com/-/spec/opensearch/1.1/"}
    value = _text(root, "opensearch:totalResults", ns)
    try:
        return int(value)
    except ValueError:
        return 0


def _http_get(url: str, *, progress=None) -> bytes:
    _respect_arxiv_api_rate_limit(url, progress=progress)
    request = urllib.request.Request(url, headers=_request_headers())
    last_error: Exception | None = None
    for attempt in range(MAX_HTTP_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return _decode_response(response.read(), response.headers.get("Content-Encoding", ""))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in RETRYABLE_HTTP_STATUS and attempt < MAX_HTTP_ATTEMPTS - 1:
                delay = _retry_delay(exc, attempt)
                _emit_wait(progress, _retry_message(exc, delay, attempt), delay=delay, attempt=attempt + 1, url=url, reason=f"http_{exc.code}")
                time.sleep(delay)
                continue
            raise RuntimeError(_http_error_message(exc, url)) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < MAX_HTTP_ATTEMPTS - 1:
                delay = 0.8 * (attempt + 1)
                _emit_wait(progress, f"Network error while contacting arXiv; waiting {delay:.1f}s before retry.", delay=delay, attempt=attempt + 1, url=url, reason="network")
                time.sleep(delay)
                continue
            break
    assert last_error is not None
    reason = getattr(last_error, "reason", last_error)
    raise RuntimeError(f"Network error while requesting {url}: {reason}") from last_error


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get("ARXIV_USER_AGENT", DEFAULT_USER_AGENT),
        "Accept": "application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    }


def _decode_response(data: bytes, encoding: str) -> bytes:
    if encoding.lower() == "gzip":
        try:
            return gzip.decompress(data)
        except gzip.BadGzipFile:
            return data
    return data


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                return max(1.0, retry_at.timestamp() - time.time())
            except (TypeError, ValueError):
                pass
    return min(60.0, 5.0 * (2**attempt))


def _http_error_message(exc: urllib.error.HTTPError, url: str) -> str:
    if exc.code == 429:
        return (
            f"HTTP 429 while requesting {url}. arXiv is rate-limiting requests; "
            "wait a few minutes, reduce the candidate count, or retry later."
        )
    return f"HTTP {exc.code} while requesting {url}"


def _respect_arxiv_api_rate_limit(url: str, *, progress=None) -> None:
    if not url.startswith(ARXIV_API):
        return
    global _LAST_ARXIV_API_REQUEST_AT
    with _ARXIV_API_LOCK:
        now = time.monotonic()
        wait_for = ARXIV_API_MIN_INTERVAL_SECONDS - (now - _LAST_ARXIV_API_REQUEST_AT)
        if wait_for > 0:
            _emit_wait(
                progress,
                f"Waiting {wait_for:.1f}s before the next arXiv API request to avoid rate limiting.",
                delay=wait_for,
                attempt=0,
                url=url,
                reason="polite_rate_limit",
            )
            time.sleep(wait_for)
        _LAST_ARXIV_API_REQUEST_AT = time.monotonic()


def _retry_message(exc: urllib.error.HTTPError, delay: float, attempt: int) -> str:
    if exc.code == 429:
        return f"arXiv is rate-limiting requests. Waiting {delay:.1f}s before retry {attempt + 2}/{MAX_HTTP_ATTEMPTS}."
    return f"arXiv returned HTTP {exc.code}. Waiting {delay:.1f}s before retry {attempt + 2}/{MAX_HTTP_ATTEMPTS}."


def _emit_wait(progress, message: str, **extra) -> None:
    if progress:
        progress({"type": "wait", "message": message, **extra})


def _text(node: ET.Element, path: str, ns: dict[str, str]) -> str:
    found = node.find(path, ns)
    return found.text or "" if found is not None else ""


def _clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _match_html(html: str, pattern: str) -> str:
    match = re.search(pattern, html, flags=re.S)
    return match.group(1) if match else ""


def _html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return _clean_space(unescape(without_tags))


def _submitted_date(value: str) -> str:
    match = re.search(r"Submitted on ([^\]]+)", value)
    if not match:
        return ""
    raw = match.group(1).strip()
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return raw


def _format_date(value: str) -> str:
    if not value:
        return ""
    return parsedate_to_datetime(value).date().isoformat() if "," in value else value[:10]


def _safe_extract(archive: tarfile.TarFile, target: Path) -> None:
    target_root = target.resolve()
    for member in archive.getmembers():
        member_path = (target / member.name).resolve()
        if os.path.commonpath([str(target_root), str(member_path)]) != str(target_root):
            raise RuntimeError(f"Unsafe path in arXiv source archive: {member.name}")
    archive.extractall(target)
