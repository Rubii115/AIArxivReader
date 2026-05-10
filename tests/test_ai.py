import pytest

from arxiv_reader.ai import _chat_base_url, _extract_stream_delta, _parse_triage, stream_summary_chunks
from arxiv_reader.arxiv import Paper


def test_parse_triage_json_from_model_text():
    result = _parse_triage(
        """
        {"keep": true, "score": 86, "reason": "matches quantum error correction", "matched_interests": ["QEC"]}
        """,
        provider="iphy",
    )
    assert result.keep is True
    assert result.score == 86
    assert result.matched_interests == ("QEC",)
    assert result.provider == "iphy"


def test_parse_triage_clamps_score():
    result = _parse_triage(
        '{"keep": false, "score": 200, "reason": "not relevant", "matched_interests": []}',
        provider="local",
    )
    assert result.score == 100


def test_extract_stream_delta_reads_chat_completion_chunk():
    assert (
        _extract_stream_delta({"choices": [{"delta": {"content": "hello"}}]})
        == "hello"
    )


def test_chat_base_url_must_be_configured(monkeypatch):
    monkeypatch.delenv("IPHY_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="base URL is not configured"):
        _chat_base_url("iphy")


def test_stream_summary_chunks_falls_back_without_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "iphy")
    monkeypatch.delenv("IPHY_API_KEY", raising=False)
    paper = Paper(
        arxiv_id="2605.04049",
        title="Demo",
        summary="Abstract",
        authors=("Ada",),
        published="2026-05-05",
        updated="2026-05-05",
        categories=("quant-ph",),
        pdf_url="https://arxiv.org/pdf/2605.04049",
        abs_url="https://arxiv.org/abs/2605.04049",
    )
    chunks = list(stream_summary_chunks(paper, "method experiment", explain_for="quantum"))
    assert chunks
    assert chunks[0][0] == "local"
