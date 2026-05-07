from __future__ import annotations

from pathlib import Path
import re


TEX_EXTENSIONS = {".tex", ".bbl", ".sty", ".cls"}


def collect_source_text(source_dir: str | Path, *, max_chars: int = 120_000) -> str:
    root = Path(source_dir)
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in TEX_EXTENSIONS),
        key=lambda path: (0 if path.name.lower() == "main.tex" else 1, path.name),
    )
    chunks: list[str] = []
    remaining = max_chars
    for path in files:
        if remaining <= 0:
            break
        text = _read_text(path)
        cleaned = clean_tex(text)
        if not cleaned:
            continue
        chunk = f"\n\n===== {path.relative_to(root)} =====\n{cleaned}"
        chunks.append(chunk[:remaining])
        remaining -= len(chunk)
    return "".join(chunks).strip()


def clean_tex(text: str) -> str:
    text = _strip_comments(text)
    text = re.sub(r"\\(begin|end)\{(figure|table|algorithm|tikzpicture|picture)\}.*?\\end\{\2\}", " ", text, flags=re.S)
    text = re.sub(r"\\(includegraphics|bibliography|addbibresource)(\[[^\]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\(cite|citep|citet|ref|eqref|label)(\[[^\]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\(section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}", r"\n\n## \2\n", text)
    text = re.sub(r"\\(title|author|date|caption)\*?\{([^}]*)\}", r"\n\1: \2\n", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+##\s+", "\n\n## ", text)
    return text.strip()


def _strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        escaped = False
        result = []
        for char in line:
            if char == "%" and not escaped:
                break
            result.append(char)
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
        lines.append("".join(result))
    return "\n".join(lines)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="ignore")
