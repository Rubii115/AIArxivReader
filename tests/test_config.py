from pathlib import Path

from arxiv_reader.config import DEFAULT_CONFIG, load_config


def test_default_config_includes_candidate_count():
    assert DEFAULT_CONFIG.reading.candidate_count == 120


def test_load_config_reads_candidate_count(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text(
        """
        [interests]
        categories = ["quant-ph"]
        keywords = []
        explain_for = "demo"

        [reading]
        max_source_chars = 1000
        max_papers_per_run = 7
        candidate_count = 42
        """,
        encoding="utf-8",
    )
    loaded = load_config(config)
    assert loaded.reading.max_papers_per_run == 7
    assert loaded.reading.candidate_count == 42
