from __future__ import annotations

import re


def publication_query(index_text: str) -> str:
    arxiv_id = _find_arxiv_id(index_text)
    if arxiv_id:
        return f"id:{arxiv_id}"

    doi = _find_doi(index_text)
    title = _find_title(index_text)
    authors = _find_authors(index_text)

    terms: list[str] = []
    if title:
        terms.append(f'ti:"{title}"')
    if doi:
        terms.append(f'all:"{doi}"')
    for author in authors[:2]:
        terms.append(f'au:"{author}"')
    if terms:
        return " AND ".join(terms[:3])
    return f'all:"{_compact(index_text)[:120]}"'


def _find_arxiv_id(text: str) -> str:
    match = re.search(r"(?:arXiv:|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)", text, re.I)
    if match:
        return match.group(1)
    stripped = text.strip()
    match = re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", stripped)
    return match.group(1) if match else ""


def _find_doi(text: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    return match.group(0).rstrip(".,;") if match else ""


def _find_title(text: str) -> str:
    bib_title = re.search(r"title\s*=\s*[{\"\'](.+?)[}\"']", text, re.I | re.S)
    if bib_title:
        return _compact(bib_title.group(1))

    lines = [_compact(line) for line in text.splitlines() if _compact(line)]
    for line in lines:
        if 8 <= len(line) <= 220 and not re.search(r"\b(author|doi|journal|booktitle|year)\b\s*=", line, re.I):
            return line.strip(" .")
    return ""


def _find_authors(text: str) -> list[str]:
    bib_author = re.search(r"author\s*=\s*[{\"\'](.+?)[}\"']", text, re.I | re.S)
    if not bib_author:
        return []
    raw = bib_author.group(1)
    names = re.split(r"\s+and\s+|;", raw)
    return [_compact(name) for name in names if _compact(name)]


def _compact(text: str) -> str:
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()
