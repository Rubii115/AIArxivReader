from arxiv_reader.ai import _extract_stream_delta, _parse_triage, stream_summary_chunks
from arxiv_reader.arxiv import Paper


def test_parse_triage_json_from_model_text():
    result = _parse_triage(
        """
        {"keep": true, "score": 86, "reason": "matches quantum error correction", "matched_interests": ["QEC"]}
        """,
        provider="deepseek",
    )
    assert result.keep is True
    assert result.score == 86
    assert result.matched_interests == ("QEC",)
    assert result.provider == "deepseek"


def test_parse_triage_clamps_score():
    result = _parse_triage(
        '{"keep": false, "score": 200, "reason": "not relevant", "matched_interests": []}',
        provider="local",
    )
    assert result.score == 100


def test_extract_stream_delta_reads_deepseek_chunk():
    assert (
        _extract_stream_delta({"choices": [{"delta": {"content": "hello"}}]})
        == "hello"
    )


def test_stream_summary_chunks_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
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
