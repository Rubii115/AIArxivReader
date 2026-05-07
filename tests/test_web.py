from datetime import date
from types import SimpleNamespace

from arxiv_reader.web import _list_runs, _load_run, _save_screen_run, _search_with_lookback, _select_relevant


def test_search_with_lookback_uses_recent_non_empty_day(monkeypatch):
    calls = []

    def fake_search(query, *, max_results, sort_by, progress=None):
        calls.append(query)
        return SimpleNamespace(papers=["paper"], total_results=1) if "20260505" in query else SimpleNamespace(papers=[], total_results=0)

    monkeypatch.setattr("arxiv_reader.web.search_with_total", fake_search)
    actual_date, query, papers, total_results = _search_with_lookback(date(2026, 5, 7), ("quant-ph",), 60, 7)
    assert actual_date == date(2026, 5, 5)
    assert "20260505" in query
    assert papers == ["paper"]
    assert total_results == 1
    assert len(calls) == 3


def test_save_and_load_screen_run(tmp_path):
    state = SimpleNamespace(runs_dir=tmp_path)
    result = {
        "requested_date": "2026-05-07",
        "actual_date": "2026-05-05",
        "papers": [{"paper": {"title": "selected"}}],
        "screened": [{"paper": {"title": "candidate"}}],
    }
    _save_screen_run(state, result)
    runs = _list_runs(state)
    assert len(runs) == 1
    assert runs[0]["paper_count"] == 1
    assert runs[0]["screened_count"] == 1
    loaded = _load_run(state, runs[0]["run_id"])
    assert loaded["run_id"] == runs[0]["run_id"]
    assert loaded["screened"][0]["paper"]["title"] == "candidate"


def test_select_relevant_keeps_all_true_items():
    screened = [
        {"triage": {"keep": True, "score": 91}},
        {"triage": {"keep": False, "score": 88}},
        {"triage": {"keep": True, "score": 63}},
    ]
    assert _select_relevant(screened) == [screened[0], screened[2]]
