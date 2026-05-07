from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from .ai import summarize_paper
from .arxiv import build_interest_query, download_source, get_paper, search
from .config import load_config
from .publication import publication_query
from .tex import collect_source_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arxiv-reader")
    parser.add_argument("--config", default="config.toml", help="Path to TOML config. Defaults to config.toml.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize_parser = subparsers.add_parser("summarize", help="Download arXiv source and summarize one paper.")
    summarize_parser.add_argument("paper", help="arXiv id or arXiv URL.")
    summarize_parser.add_argument("--source-dir", help="Use an existing extracted source directory instead of downloading.")

    today_parser = subparsers.add_parser("today", help="Find and summarize papers matching your interests.")
    today_parser.add_argument("--date", help="Date in YYYY-MM-DD. Defaults to local today.")
    today_parser.add_argument("--limit", type=int, help="Max papers to summarize.")

    find_parser = subparsers.add_parser("find", help="Search arXiv from publication index text.")
    find_parser.add_argument("index", nargs="+", help="Publication index text, title, DOI, or BibTeX.")
    find_parser.add_argument("--limit", type=int, default=5)

    args = parser.parse_args(argv)
    config = _load_config_if_present(args.config)

    try:
        if args.command == "summarize":
            return _summarize(args.paper, args.source_dir, config)
        if args.command == "today":
            return _today(args.date, args.limit, config)
        if args.command == "find":
            return _find(" ".join(args.index), args.limit)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def _summarize(paper_id: str, source_dir: str | None, config) -> int:
    paper = get_paper(paper_id)
    extracted = Path(source_dir) if source_dir else download_source(paper.arxiv_id)
    source_text = collect_source_text(extracted, max_chars=config.reading.max_source_chars)
    result = summarize_paper(paper, source_text, explain_for=config.interests.explain_for)
    _print_paper_header(paper)
    print()
    print(result.text)
    return 0


def _today(day_text: str | None, limit: int | None, config) -> int:
    selected_day = date.fromisoformat(day_text) if day_text else date.today()
    max_results = limit or config.reading.max_papers_per_run
    query = build_interest_query(config.interests.categories, config.interests.keywords, selected_day)
    papers = search(query, max_results=max_results, sort_by="submittedDate")
    if not papers:
        print(f"No matching papers found for {selected_day.isoformat()}.")
        return 0

    print(f"Found {len(papers)} matching papers for {selected_day.isoformat()}.\n")
    for index, paper in enumerate(papers, start=1):
        print(f"========== {index}. {paper.title} ==========")
        try:
            source_dir = download_source(paper.arxiv_id)
            source_text = collect_source_text(source_dir, max_chars=config.reading.max_source_chars)
            result = summarize_paper(paper, source_text, explain_for=config.interests.explain_for)
            _print_paper_header(paper)
            print(result.text)
        except Exception as exc:
            _print_paper_header(paper)
            print(f"Could not summarize source: {exc}")
            print(f"Abstract fallback: {paper.summary}")
        print()
    return 0


def _find(index_text: str, limit: int) -> int:
    query = publication_query(index_text)
    papers = search(query, max_results=limit)
    print(f"Query: {query}\n")
    if not papers:
        print("No candidates found.")
        return 0
    for paper in papers:
        _print_paper_header(paper)
        print(paper.summary[:600] + ("..." if len(paper.summary) > 600 else ""))
        print()
    return 0


def _print_paper_header(paper) -> None:
    print(f"arXiv: {paper.arxiv_id}")
    print(f"Title: {paper.title}")
    print(f"Authors: {', '.join(paper.authors[:8])}")
    print(f"Categories: {', '.join(paper.categories)}")
    print(f"URL: {paper.abs_url}")


def _load_config_if_present(path: str):
    config_path = Path(path)
    if config_path.exists():
        return load_config(config_path)
    return load_config(None)


if __name__ == "__main__":
    raise SystemExit(main())
