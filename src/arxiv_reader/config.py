from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Interests:
    categories: tuple[str, ...]
    keywords: tuple[str, ...]
    explain_for: str


@dataclass(frozen=True)
class ReadingConfig:
    max_source_chars: int = 120_000
    max_papers_per_run: int = 10
    candidate_count: int = 120


@dataclass(frozen=True)
class AppConfig:
    interests: Interests
    reading: ReadingConfig


DEFAULT_CONFIG = AppConfig(
    interests=Interests(
        categories=("quant-ph",),
        keywords=(
            "quantum information",
            "quantum computing",
            "quantum simulation",
            "entanglement",
            "quantum error correction",
            "many-body",
        ),
        explain_for=(
            "我是超导量子计算实验方向的研究者。请把论文按是否值得我进一步读来筛选，"
            "同时保留有清晰物理机制或新量子图像的理论模型。"
        ),
    ),
    reading=ReadingConfig(),
)


def load_config(path: str | Path | None) -> AppConfig:
    if path is None:
        return DEFAULT_CONFIG

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    interests_data = data.get("interests", {})
    reading_data = data.get("reading", {})

    return AppConfig(
        interests=Interests(
            categories=tuple(interests_data.get("categories", DEFAULT_CONFIG.interests.categories)),
            keywords=tuple(interests_data.get("keywords", DEFAULT_CONFIG.interests.keywords)),
            explain_for=interests_data.get("explain_for", DEFAULT_CONFIG.interests.explain_for),
        ),
        reading=ReadingConfig(
            max_source_chars=int(reading_data.get("max_source_chars", DEFAULT_CONFIG.reading.max_source_chars)),
            max_papers_per_run=int(reading_data.get("max_papers_per_run", DEFAULT_CONFIG.reading.max_papers_per_run)),
            candidate_count=int(reading_data.get("candidate_count", DEFAULT_CONFIG.reading.candidate_count)),
        ),
    )
