from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import json
import os
import re
import urllib.error
import urllib.request

from .arxiv import Paper


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


@dataclass(frozen=True)
class SummaryResult:
    text: str
    used_ai: bool
    provider: str


@dataclass(frozen=True)
class TriageResult:
    keep: bool
    score: int
    reason: str
    matched_interests: tuple[str, ...]
    provider: str


def summarize_paper(paper: Paper, source_text: str, *, explain_for: str) -> SummaryResult:
    provider = os.environ.get("AI_PROVIDER", "iphy").strip().lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        if api_key:
            return SummaryResult(_openai_summary(api_key, model, paper, source_text, explain_for), True, "openai")
    else:
        api_key = _chat_api_key(provider)
        if api_key:
            model = _chat_model(provider, api_key)
            return SummaryResult(_chat_summary(provider, api_key, model, paper, source_text, explain_for), True, provider)
    return SummaryResult(_local_summary(paper, source_text, explain_for), False, "local")


def stream_summary_chunks(paper: Paper, source_text: str, *, explain_for: str) -> Iterator[tuple[str, str]]:
    provider = os.environ.get("AI_PROVIDER", "iphy").strip().lower()
    if provider != "openai":
        api_key = _chat_api_key(provider)
        if api_key:
            model = _chat_model(provider, api_key)
            yield from _chat_summary_stream(provider, api_key, model, paper, source_text, explain_for)
            return

    result = summarize_paper(paper, source_text, explain_for=explain_for)
    yield result.provider, result.text


def triage_paper(paper: Paper, *, interest_description: str) -> TriageResult:
    provider = os.environ.get("AI_PROVIDER", "iphy").strip().lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        if api_key:
            return _openai_triage(api_key, model, paper, interest_description)
    else:
        api_key = _chat_api_key(provider)
        if api_key:
            model = _chat_model(provider, api_key)
            return _chat_triage(provider, api_key, model, paper, interest_description)
    return _local_triage(paper, interest_description)


def answer_question(
    paper: Paper,
    source_text: str,
    summary: str,
    history: list[dict[str, str]],
    question: str,
    *,
    explain_for: str,
) -> SummaryResult:
    provider = os.environ.get("AI_PROVIDER", "iphy").strip().lower()
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
        if api_key:
            return SummaryResult(
                _openai_chat(api_key, model, paper, source_text, summary, history, question, explain_for),
                True,
                "openai",
            )
    else:
        api_key = _chat_api_key(provider)
        if api_key:
            model = _chat_model(provider, api_key)
            return SummaryResult(
                _chat_completion_chat(provider, api_key, model, paper, source_text, summary, history, question, explain_for),
                True,
                provider,
            )
    return SummaryResult(_local_answer(paper, question, summary), False, "local")


def stream_answer_chunks(
    paper: Paper,
    source_text: str,
    summary: str,
    history: list[dict[str, str]],
    question: str,
    *,
    explain_for: str,
) -> Iterator[tuple[str, str]]:
    provider = os.environ.get("AI_PROVIDER", "iphy").strip().lower()
    if provider != "openai":
        api_key = _chat_api_key(provider)
        if api_key:
            model = _chat_model(provider, api_key)
            yield from _chat_completion_chat_stream(provider, api_key, model, paper, source_text, summary, history, question, explain_for)
            return

    result = answer_question(paper, source_text, summary, history, question, explain_for=explain_for)
    yield result.provider, result.text


def build_reading_prompt(paper: Paper, source_text: str, explain_for: str) -> str:
    return f"""
You are a research paper reading assistant for a quantum physics specialist.
Read the arXiv metadata and TeX source excerpt, then answer in Chinese.

Reader profile and interests:
{explain_for}

Output format:
1. One-sentence takeaway
2. Problem and physics context
3. Core method, model, or theoretical argument
4. Key equations, approximations, or experimental setup worth checking
5. Evidence quality and limitations
6. What to read first in the source paper
7. Relevance to quantum physics research

Metadata:
Title: {paper.title}
Authors: {", ".join(paper.authors)}
Categories: {", ".join(paper.categories)}
Abstract: {paper.summary}

TeX source excerpt:
{source_text}
""".strip()


def build_triage_prompt(paper: Paper, interest_description: str) -> str:
    return f"""
Judge whether this paper matches the reader's interests using ONLY the title and abstract.
Do not claim to have read the full paper. Answer in strict JSON only.

Reader interests:
{interest_description}

Paper:
Title: {paper.title}
Authors: {", ".join(paper.authors)}
Categories: {", ".join(paper.categories)}
Abstract: {paper.summary}

JSON schema:
{{
  "keep": true,
  "score": 0,
  "reason": "one concise Chinese sentence",
  "matched_interests": ["matched interest phrases"]
}}
""".strip()


def build_chat_messages(
    paper: Paper,
    source_text: str,
    summary: str,
    history: list[dict[str, str]],
    question: str,
    explain_for: str,
) -> list[dict[str, str]]:
    source_excerpt = source_text[:80_000]
    messages = [
        {
            "role": "system",
            "content": (
                "You are a rigorous paper discussion assistant for a quantum physics researcher. "
                "Answer in Chinese, ground claims in the paper source, and say when evidence is absent."
            ),
        },
        {
            "role": "user",
            "content": f"""
Reader background:
{explain_for}

Paper metadata:
Title: {paper.title}
Authors: {", ".join(paper.authors)}
Categories: {", ".join(paper.categories)}
Abstract: {paper.summary}

Existing deep-read summary:
{summary}

TeX source excerpt:
{source_excerpt}
""".strip(),
        },
        {
            "role": "assistant",
            "content": "I have loaded this paper's metadata, deep-read summary, and source excerpt. You can ask follow-up questions.",
        },
    ]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": question})
    return messages


def _chat_summary(provider: str, api_key: str, model: str, paper: Paper, source_text: str, explain_for: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You extract rigorous, useful paper insights for a quantum physics researcher."},
            {"role": "user", "content": build_reading_prompt(paper, source_text, explain_for)},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    data = _post_json(_chat_completions_url(provider), payload, api_key, timeout=180)
    return _extract_chat_text(data)


def _chat_summary_stream(
    provider: str, api_key: str, model: str, paper: Paper, source_text: str, explain_for: str
) -> Iterator[tuple[str, str]]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You extract rigorous, useful paper insights for a quantum physics researcher."},
            {"role": "user", "content": build_reading_prompt(paper, source_text, explain_for)},
        ],
        "temperature": 0.2,
        "stream": True,
    }
    for event in _post_json_stream(_chat_completions_url(provider), payload, api_key, timeout=180):
        chunk = _extract_stream_delta(event)
        if chunk:
            yield provider, chunk


def _chat_triage(provider: str, api_key: str, model: str, paper: Paper, interest_description: str) -> TriageResult:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise arXiv paper triage classifier."},
            {"role": "user", "content": build_triage_prompt(paper, interest_description)},
        ],
        "temperature": 0,
        "stream": False,
    }
    data = _post_json(_chat_completions_url(provider), payload, api_key, timeout=90)
    return _parse_triage(_extract_chat_text(data), provider=provider)


def _chat_completion_chat(
    provider: str,
    api_key: str,
    model: str,
    paper: Paper,
    source_text: str,
    summary: str,
    history: list[dict[str, str]],
    question: str,
    explain_for: str,
) -> str:
    payload = {
        "model": model,
        "messages": build_chat_messages(paper, source_text, summary, history, question, explain_for),
        "temperature": 0.2,
        "stream": False,
    }
    data = _post_json(_chat_completions_url(provider), payload, api_key, timeout=180)
    return _extract_chat_text(data)


def _chat_completion_chat_stream(
    provider: str,
    api_key: str,
    model: str,
    paper: Paper,
    source_text: str,
    summary: str,
    history: list[dict[str, str]],
    question: str,
    explain_for: str,
) -> Iterator[tuple[str, str]]:
    payload = {
        "model": model,
        "messages": build_chat_messages(paper, source_text, summary, history, question, explain_for),
        "temperature": 0.2,
        "stream": True,
    }
    for event in _post_json_stream(_chat_completions_url(provider), payload, api_key, timeout=180):
        chunk = _extract_stream_delta(event)
        if chunk:
            yield provider, chunk


def _openai_summary(api_key: str, model: str, paper: Paper, source_text: str, explain_for: str) -> str:
    payload = {"model": model, "input": build_reading_prompt(paper, source_text, explain_for)}
    data = _post_json(OPENAI_RESPONSES_URL, payload, api_key, timeout=180)
    return _extract_response_text(data)


def _openai_triage(api_key: str, model: str, paper: Paper, interest_description: str) -> TriageResult:
    payload = {"model": model, "input": build_triage_prompt(paper, interest_description)}
    data = _post_json(OPENAI_RESPONSES_URL, payload, api_key, timeout=90)
    return _parse_triage(_extract_response_text(data), provider="openai")


def _openai_chat(
    api_key: str,
    model: str,
    paper: Paper,
    source_text: str,
    summary: str,
    history: list[dict[str, str]],
    question: str,
    explain_for: str,
) -> str:
    payload = {
        "model": model,
        "input": "\n\n".join(
            message["content"] for message in build_chat_messages(paper, source_text, summary, history, question, explain_for)
        ),
    }
    data = _post_json(OPENAI_RESPONSES_URL, payload, api_key, timeout=180)
    return _extract_response_text(data)


def _chat_api_key(provider: str) -> str | None:
    if provider == "iphy":
        return os.environ.get("IPHY_API_KEY")
    return os.environ.get(f"{provider.upper()}_API_KEY")


def _chat_model(provider: str, api_key: str) -> str:
    if provider == "iphy":
        model = os.environ.get("IPHY_MODEL")
        return model.strip() if model and model.strip() else _first_available_model(provider, api_key)
    model = os.environ.get(f"{provider.upper()}_MODEL")
    if model and model.strip():
        return model.strip()
    return _first_available_model(provider, api_key)


def _chat_completions_url(provider: str) -> str:
    base_url = _chat_base_url(provider)
    return f"{base_url}/chat/completions"


def _chat_models_url(provider: str) -> str:
    base_url = _chat_base_url(provider)
    return f"{base_url}/models"


def _chat_base_url(provider: str) -> str:
    base_url = os.environ.get(f"{provider.upper()}_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError(f"{provider} base URL is not configured; set [ai].base_url in config.toml")
    return base_url.rstrip("/")


def _first_available_model(provider: str, api_key: str) -> str:
    data = _get_json(_chat_models_url(provider), api_key, timeout=30)
    models = data.get("data", [])
    for item in models:
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id.strip():
            return model_id.strip()
    raise RuntimeError(f"{provider} models response did not contain any model id")


def _get_json(url: str, api_key: str, *, timeout: int) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI network error: {exc.reason}") from exc


def _post_json(url: str, payload: dict, api_key: str, *, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI network error: {exc.reason}") from exc


def _post_json_stream(url: str, payload: dict, api_key: str, *, timeout: int) -> Iterator[dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                if data:
                    yield json.loads(data)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"AI API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI network error: {exc.reason}") from exc


def _extract_chat_text(data: dict) -> str:
    choices = data.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return content
    raise RuntimeError("Chat completion response did not contain text output")


def _extract_stream_delta(data: dict) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""
    delta = choices[0].get("delta", {})
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _parse_triage(text: str, *, provider: str) -> TriageResult:
    payload_text = text.strip()
    match = re.search(r"\{.*\}", payload_text, re.S)
    if match:
        payload_text = match.group(0)
    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI triage response was not valid JSON: {text[:300]}") from exc
    return TriageResult(
        keep=bool(data.get("keep", False)),
        score=max(0, min(100, int(data.get("score", 0)))),
        reason=str(data.get("reason", "")).strip(),
        matched_interests=tuple(str(item) for item in data.get("matched_interests", []) if str(item).strip()),
        provider=provider,
    )


def _extract_response_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                parts.append(content["text"])
    if not parts:
        raise RuntimeError("OpenAI response did not contain text output")
    return "\n".join(parts)


def _local_triage(paper: Paper, interest_description: str) -> TriageResult:
    words = {
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", interest_description)
        if word.lower() not in {"quantum", "paper", "study", "about", "with", "from"}
    }
    haystack = f"{paper.title} {paper.summary}".lower()
    matches = tuple(sorted(word for word in words if word in haystack))
    score = min(100, 35 + len(matches) * 12) if matches else 25
    return TriageResult(
        keep=bool(matches),
        score=score,
        reason="Local keyword fallback; set IPHY_API_KEY for semantic title/abstract triage.",
        matched_interests=matches,
        provider="local",
    )


def _local_summary(paper: Paper, source_text: str, explain_for: str) -> str:
    sections = _section_snippets(source_text)
    likely_theory = _first_matching(sections, ("theory", "hamiltonian", "model", "method", "formalism"))
    likely_experiment = _first_matching(sections, ("experiment", "measurement", "result", "simulation", "implementation"))
    return "\n".join(
        [
            "[Local fallback: IPHY_API_KEY is not set, so no AI model was called.]",
            "",
            f"Title: {paper.title}",
            f"Authors: {', '.join(paper.authors[:8])}",
            f"Categories: {', '.join(paper.categories)}",
            f"URL: {paper.abs_url}",
            "",
            "Abstract:",
            paper.summary,
            "",
            "Likely theory/method section:",
            likely_theory or "No obvious theory or method section was found in the source excerpt.",
            "",
            "Likely experiment/result section:",
            likely_experiment or "No obvious experiment or result section was found in the source excerpt.",
            "",
            f"Reader interests: {explain_for.strip()}",
        ]
    )


def _local_answer(paper: Paper, question: str, summary: str) -> str:
    return "\n".join(
        [
            "[Local fallback: IPHY_API_KEY is not set, so no AI model was called.]",
            f"Paper: {paper.title}",
            f"Question: {question}",
            "",
            "Current deep-read context:",
            summary[:3000],
        ]
    )


def _section_snippets(source_text: str) -> list[str]:
    chunks = re.split(r"\n\s*##\s+", source_text)
    return [re.sub(r"\s+", " ", chunk).strip()[:1800] for chunk in chunks if chunk.strip()]


def _first_matching(chunks: list[str], needles: tuple[str, ...]) -> str:
    lowered_needles = tuple(needle.lower() for needle in needles)
    for chunk in chunks:
        head = chunk[:220].lower()
        if any(needle in head for needle in lowered_needles):
            return chunk
    return ""
