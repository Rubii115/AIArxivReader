from pathlib import Path
import os

from arxiv_reader.env import load_dotenv


def test_load_dotenv_reads_key_values(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("IPHY_API_KEY", raising=False)
    monkeypatch.delenv("IPHY_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # comment
        IPHY_API_KEY="abc123"
        IPHY_MODEL=demo-model
        """,
        encoding="utf-8",
    )

    load_dotenv(env_file)

    assert os.environ["IPHY_API_KEY"] == "abc123"
    assert os.environ["IPHY_MODEL"] == "demo-model"


def test_load_dotenv_does_not_override_existing_values(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IPHY_API_KEY", "from-shell")
    env_file = tmp_path / ".env"
    env_file.write_text("IPHY_API_KEY=from-file\n", encoding="utf-8")

    load_dotenv(env_file)

    assert os.environ["IPHY_API_KEY"] == "from-shell"
