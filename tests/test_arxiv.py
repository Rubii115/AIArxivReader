from datetime import date

from arxiv_reader import arxiv
from arxiv_reader.arxiv import build_interest_query, get_paper_from_abs_page, normalize_arxiv_id


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
    monkeypatch.setattr(arxiv, "_http_get", lambda url: html)
    paper = get_paper_from_abs_page("2605.04049")
    assert paper.title == "Demo Paper"
    assert paper.authors == ("Ada Lovelace", "Alan Turing")
    assert paper.summary == "A useful abstract."
    assert paper.categories == ("quant-ph",)
