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


def test_load_config_applies_ai_settings(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("IPHY_API_KEY", raising=False)
    monkeypatch.delenv("IPHY_MODEL", raising=False)
    config = tmp_path / "config.toml"
    config.write_text(
        """
        [ai]
        provider = "iphy"
        api_key = "secret"
        model = "demo-model"

        [interests]
        categories = ["quant-ph"]
        keywords = []
        explain_for = "demo"
        """,
        encoding="utf-8",
    )

    load_config(config)

    import os

    assert os.environ["AI_PROVIDER"] == "iphy"
    assert os.environ["IPHY_API_KEY"] == "secret"
    assert os.environ["IPHY_MODEL"] == "demo-model"


def test_load_config_applies_ai_settings_for_configured_provider(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    config = tmp_path / "config.toml"
    config.write_text(
        """
        [ai]
        provider = "deepseek"
        base_url = "https://api.deepseek.com"
        api_key = "secret"
        model = "deepseek-v4-flash"

        [interests]
        categories = ["quant-ph"]
        keywords = []
        explain_for = "demo"
        """,
        encoding="utf-8",
    )

    load_config(config)

    import os

    assert os.environ["AI_PROVIDER"] == "deepseek"
    assert os.environ["DEEPSEEK_API_KEY"] == "secret"
    assert os.environ["DEEPSEEK_MODEL"] == "deepseek-v4-flash"
    assert os.environ["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com"
