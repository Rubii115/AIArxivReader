from pathlib import Path
import os

from arxiv_reader.env import load_dotenv


def test_load_dotenv_reads_key_values(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # comment
        DEEPSEEK_API_KEY="abc123"
        DEEPSEEK_MODEL=deepseek-v4-flash
        """,
        encoding="utf-8",
    )

    load_dotenv(env_file)

    assert os.environ["DEEPSEEK_API_KEY"] == "abc123"
    assert os.environ["DEEPSEEK_MODEL"] == "deepseek-v4-flash"


def test_load_dotenv_does_not_override_existing_values(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-shell")
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-file\n", encoding="utf-8")

    load_dotenv(env_file)

    assert os.environ["DEEPSEEK_API_KEY"] == "from-shell"
