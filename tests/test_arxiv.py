from datetime import date
from email.message import Message
import urllib.error

from arxiv_reader import arxiv
from arxiv_reader.arxiv import build_interest_query, get_paper_from_abs_page, normalize_arxiv_id, parse_total_results


def test_normalize_arxiv_id_accepts_urls_and_plain_ids():
    assert normalize_arxiv_id("https://arxiv.org/pdf/2401.01234.pdf") == "2401.01234"
    assert normalize_arxiv_id("2401.01234v2") == "2401.01234v2"


def test_build_interest_query_contains_date_categories_and_keywords():
    query = build_interest_query(("cs.CL",), ("language model",), date(2026, 5, 7))
    assert "submittedDate:[202605070000 TO 202605072359]" in query
    assert "cat:cs.CL" in query
    assert 'all:"language model"' in query


def test_get_paper_from_abs_page_parses_arxiv_html(monkeypatch):
    html = b"""
    <div class="dateline">[Submitted on 5 May 2026]</div>
    <h1 class="title mathjax"><span class="descriptor">Title:</span>Demo Paper</h1>
    <div class="authors"><span class="descriptor">Authors:</span><a>Ada Lovelace</a>, <a>Alan Turing</a></div>
    <blockquote class="abstract mathjax"><span class="descriptor">Abstract:</span>A useful abstract.</blockquote>
    <td class="tablecell subjects"><span class="primary-subject">Quantum Physics (quant-ph)</span></td>
    """
    monkeypatch.setattr(arxiv, "_http_get", lambda url, **kwargs: html)
    paper = get_paper_from_abs_page("2605.04049")
    assert paper.title == "Demo Paper"
    assert paper.authors == ("Ada Lovelace", "Alan Turing")
    assert paper.summary == "A useful abstract."
    assert paper.categories == ("quant-ph",)


def test_parse_total_results_reads_opensearch_count():
    xml = b"""
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
      <opensearch:totalResults>67</opensearch:totalResults>
    </feed>
    """
    assert parse_total_results(xml) == 67


def test_http_get_retries_429_with_retry_after(monkeypatch):
    calls = []
    sleeps = []
    events = []
    headers = Message()
    headers["Retry-After"] = "1"

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", headers, None)
        return Response()

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(arxiv.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert arxiv._http_get("https://export.arxiv.org/api/query?q=test", progress=events.append) == b"ok"
    assert len(calls) == 2
    assert sleeps == [1.0]
    assert events[0]["type"] == "wait"
    assert events[0]["reason"] == "http_429"


def test_http_get_rate_limits_arxiv_api_requests(monkeypatch):
    sleeps = []
    events = []
    timestamps = iter([10.0, 10.0, 10.5, 13.6])

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"ok"

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", lambda request, timeout: Response())
    monkeypatch.setattr(arxiv.time, "monotonic", lambda: next(timestamps))
    monkeypatch.setattr(arxiv.time, "sleep", lambda seconds: sleeps.append(round(seconds, 1)))
    monkeypatch.setattr(arxiv, "_LAST_ARXIV_API_REQUEST_AT", 0.0)

    assert arxiv._http_get(arxiv.ARXIV_API + "?q=one", progress=events.append) == b"ok"
    assert arxiv._http_get(arxiv.ARXIV_API + "?q=two", progress=events.append) == b"ok"
    assert sleeps == [2.6]
    assert events[0]["reason"] == "polite_rate_limit"


def test_request_headers_use_configurable_user_agent(monkeypatch):
    monkeypatch.setenv("ARXIV_USER_AGENT", "DemoClient/1.0 (mailto:demo@example.com)")

    headers = arxiv._request_headers()

    assert headers["User-Agent"] == "DemoClient/1.0 (mailto:demo@example.com)"
    assert "application/atom+xml" in headers["Accept"]
