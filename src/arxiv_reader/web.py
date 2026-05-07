from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from .ai import SummaryResult, answer_question, stream_answer_chunks, stream_summary_chunks, summarize_paper, triage_paper
from .arxiv import Paper, build_interest_query, download_source, get_paper, search
from .config import load_config
from .env import load_dotenv
from .publication import publication_query
from .tex import collect_source_text


FRONTEND_INDEX = Path(__file__).with_name("static") / "index.html"


@dataclass
class PaperSession:
    paper: Paper
    source_text: str
    summary: str
    history: list[dict[str, str]] = field(default_factory=list)


class AppState:
    def __init__(self, config_path: str | None):
        path = Path(config_path) if config_path else Path("config.toml")
        self.config = load_config(path if path.exists() else None)
        self.sessions: dict[str, PaperSession] = {}
        self.runs_dir = Path("runs")
        self.lock = threading.Lock()


def make_handler(state: AppState):
    class ArxivReaderHandler(BaseHTTPRequestHandler):
        server_version = "arxiv-reader-web/0.4"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(_load_index_html())
                return
            if parsed.path == "/api/config":
                self._send_json(
                    {
                        "categories": list(state.config.interests.categories),
                        "keywords": list(state.config.interests.keywords),
                        "explain_for": state.config.interests.explain_for,
                        "default_limit": state.config.reading.max_papers_per_run,
                        "default_candidates": state.config.reading.candidate_count,
                        "ai_provider": os.environ.get("AI_PROVIDER", "deepseek"),
                        "deepseek_model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                        "deepseek_key_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
                        "openai_key_present": bool(os.environ.get("OPENAI_API_KEY")),
                    }
                )
                return
            if parsed.path == "/api/runs":
                self._send_json({"runs": _list_runs(state)})
                return
            if parsed.path == "/api/run":
                run_id = parse_qs(parsed.query).get("id", [""])[0]
                self._send_json(_load_run(state, run_id))
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                payload = self._read_json()
                if self.path == "/api/screen":
                    self._screen(payload)
                    return
                if self.path == "/api/screen/stream":
                    self._screen_stream(payload)
                    return
                if self.path == "/api/find":
                    self._find(payload)
                    return
                if self.path == "/api/summarize":
                    self._summarize(payload)
                    return
                if self.path == "/api/session":
                    self._create_session(payload)
                    return
                if self.path == "/api/session/stream":
                    self._create_session_stream(payload)
                    return
                if self.path == "/api/session/message":
                    self._session_message(payload)
                    return
                if self.path == "/api/session/message/stream":
                    self._session_message_stream(payload)
                    return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def _screen(self, payload: dict) -> None:
            self._send_json(_screen_payload(payload, state, progress=None))

        def _screen_stream(self, payload: dict) -> None:
            self._begin_sse()
            try:
                result = _screen_payload(payload, state, progress=self._write_sse)
                self._write_sse({"type": "done", "result": result})
            except Exception as exc:
                self._write_sse({"type": "error", "error": str(exc)})
            finally:
                self.close_connection = True

        def _find(self, payload: dict) -> None:
            query = publication_query(str(payload.get("index", "")))
            papers = search(query, max_results=int(payload.get("limit", 5)))
            self._send_json({"query": query, "papers": [_paper_json(paper) for paper in papers]})

        def _summarize(self, payload: dict) -> None:
            paper_id = _required(payload, "paper")
            interest = str(payload.get("interest") or state.config.interests.explain_for).strip()
            paper, _, result = _deep_read(paper_id, state, interest, progress=None)
            self._send_json({"paper": _paper_json(paper), "summary": result.text, "used_ai": result.used_ai, "provider": result.provider})

        def _create_session(self, payload: dict) -> None:
            self._send_json(_create_session_payload(payload, state, progress=None))

        def _create_session_stream(self, payload: dict) -> None:
            self._begin_sse()
            try:
                result = _create_session_payload(payload, state, progress=self._write_sse, stream_summary=True)
                self._write_sse({"type": "done", "result": result})
            except Exception as exc:
                self._write_sse({"type": "error", "error": str(exc)})
            finally:
                self.close_connection = True

        def _session_message(self, payload: dict) -> None:
            session_id, question, interest, session, history = self._load_session_turn(payload)
            result = answer_question(session.paper, session.source_text, session.summary, history, question, explain_for=interest)
            self._save_turn(session_id, question, result.text)
            self._send_json({"session_id": session_id, "answer": result.text, "provider": result.provider, "used_ai": result.used_ai})

        def _session_message_stream(self, payload: dict) -> None:
            session_id, question, interest, session, history = self._load_session_turn(payload)
            self._begin_sse()
            answer_parts: list[str] = []
            provider = "local"
            try:
                for provider, chunk in stream_answer_chunks(
                    session.paper,
                    session.source_text,
                    session.summary,
                    history,
                    question,
                    explain_for=interest,
                ):
                    answer_parts.append(chunk)
                    self._write_sse({"type": "chunk", "provider": provider, "text": chunk})
                self._save_turn(session_id, question, "".join(answer_parts))
                self._write_sse({"type": "done", "provider": provider})
            except Exception as exc:
                self._write_sse({"type": "error", "error": str(exc)})
            finally:
                self.close_connection = True

        def _load_session_turn(self, payload: dict):
            session_id = _required(payload, "session_id")
            question = _required(payload, "message")
            interest = str(payload.get("interest") or state.config.interests.explain_for).strip()
            with state.lock:
                session = state.sessions.get(session_id)
                if session is None:
                    raise ValueError("Unknown session")
                history = list(session.history)
            return session_id, question, interest, session, history

        def _save_turn(self, session_id: str, question: str, answer: str) -> None:
            with state.lock:
                session = state.sessions[session_id]
                session.history.append({"role": "user", "content": question})
                session.history.append({"role": "assistant", "content": answer})

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        def _send_html(self, html: str) -> None:
            data = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _begin_sse(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

        def _write_sse(self, payload: dict) -> None:
            data = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
            self.wfile.write(data)
            self.wfile.flush()

        def log_message(self, format: str, *args) -> None:
            print(f"{self.address_string()} - {format % args}")

    return ArxivReaderHandler



def _screen_payload(payload: dict, state: AppState, progress) -> dict:
    selected = date.fromisoformat(str(payload.get("date") or date.today().isoformat()))
    candidate_count = int(payload.get("candidate_count", state.config.reading.candidate_count))
    lookback_days = int(payload.get("lookback_days", 7))
    interest = str(payload.get("interest") or state.config.interests.explain_for).strip()

    def emit(text: str, **extra) -> None:
        if progress:
            progress({"type": "progress", "message": text, **extra})

    emit(f"Searching {selected.isoformat()} in {', '.join(state.config.interests.categories)} for candidate papers.")
    actual_date, arxiv_query, candidates = _search_with_lookback(
        selected,
        state.config.interests.categories,
        candidate_count,
        lookback_days,
        progress=progress,
    )
    if actual_date != selected:
        emit(f"No candidates found on {selected.isoformat()}; looked back to {actual_date.isoformat()}.")
    emit(f"Fetched {len(candidates)} candidate papers. Starting title/abstract relevance triage.", count=len(candidates))

    screened = []
    for index, paper in enumerate(candidates, start=1):
        emit(f"Analyzing relevance {index}/{len(candidates)}: {paper.title}", index=index, total=len(candidates), title=paper.title)
        triage = triage_paper(paper, interest_description=interest)
        screened.append(
            {
                "paper": _paper_json(paper),
                "triage": {
                    "keep": triage.keep,
                    "score": triage.score,
                    "reason": triage.reason,
                    "matched_interests": list(triage.matched_interests),
                    "provider": triage.provider,
                },
            }
        )
        emit(
            f"Finished relevance analysis {index}/{len(candidates)}: {paper.title}; score {triage.score}/100.",
            index=index,
            total=len(candidates),
            score=triage.score,
            keep=triage.keep,
        )

    screened.sort(key=lambda item: (item["triage"]["keep"], item["triage"]["score"]), reverse=True)
    kept = _select_relevant(screened)
    emit(f"Screening complete. {len(kept)} papers were marked relevant.")
    result = {
        "query": arxiv_query,
        "interest": interest,
        "requested_date": selected.isoformat(),
        "actual_date": actual_date.isoformat(),
        "lookback_used": actual_date != selected,
        "papers": kept,
        "screened": screened,
    }
    _save_screen_run(state, result)
    emit(f"Screening report saved: {result['run_path']}")
    return result

def _save_screen_run(state: AppState, result: dict) -> None:
    state.runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    path = state.runs_dir / f"{run_id}.json"
    result["run_id"] = run_id
    result["saved_at"] = datetime.now().isoformat(timespec="seconds")
    result["run_path"] = str(path)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _select_relevant(screened: list[dict]) -> list[dict]:
    return [item for item in screened if item["triage"]["keep"]]


def _list_runs(state: AppState) -> list[dict]:
    if not state.runs_dir.exists():
        return []
    runs = []
    for path in sorted(state.runs_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append(
            {
                "run_id": data.get("run_id", path.stem),
                "saved_at": data.get("saved_at", ""),
                "requested_date": data.get("requested_date", ""),
                "actual_date": data.get("actual_date", ""),
                "paper_count": len(data.get("papers", [])),
                "screened_count": len(data.get("screened", [])),
                "run_path": str(path),
            }
        )
    return runs


def _load_run(state: AppState, run_id: str) -> dict:
    if not run_id:
        raise ValueError("id is required")
    path = (state.runs_dir / f"{Path(run_id).stem}.json").resolve()
    runs_root = state.runs_dir.resolve()
    if os.path.commonpath([str(runs_root), str(path)]) != str(runs_root):
        raise ValueError("Invalid run id")
    if not path.exists():
        raise ValueError(f"Run not found: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _create_session_payload(payload: dict, state: AppState, progress, stream_summary: bool = False) -> dict:
    paper_id = _required(payload, "paper")
    interest = str(payload.get("interest") or state.config.interests.explain_for).strip()
    paper, source_text, result = _deep_read(paper_id, state, interest, progress=progress, stream_summary=stream_summary)
    session_id = uuid4().hex
    with state.lock:
        state.sessions[session_id] = PaperSession(paper=paper, source_text=source_text, summary=result.text)
    return {
        "session_id": session_id,
        "paper": _paper_json(paper),
        "summary": result.text,
        "provider": result.provider,
        "used_ai": result.used_ai,
        "messages": [],
    }



def _deep_read(paper_id: str, state: AppState, interest: str, progress, stream_summary: bool = False):
    def emit(text: str, **extra) -> None:
        if progress:
            progress({"type": "progress", "message": text, **extra})

    emit(f"Fetching paper metadata: {paper_id}")
    paper = get_paper(paper_id)
    emit(f"Fetched title: {paper.title}", title=paper.title, arxiv_id=paper.arxiv_id)
    emit("Downloading arXiv TeX source.")
    source_dir = download_source(paper.arxiv_id)
    emit("Source download complete. Parsing TeX files.")
    source_text = collect_source_text(source_dir, max_chars=state.config.reading.max_source_chars)
    emit(f"TeX parsing complete. Sending source excerpt to the model: {len(source_text)} characters.")
    if stream_summary and progress:
        summary_parts: list[str] = []
        provider = "local"
        used_ai = False
        progress({"type": "summary_start", "paper": _paper_json(paper), "provider": provider, "used_ai": used_ai})
        for provider, chunk in stream_summary_chunks(paper, source_text, explain_for=interest):
            used_ai = provider != "local"
            summary_parts.append(chunk)
            progress({"type": "summary_chunk", "provider": provider, "used_ai": used_ai, "text": chunk})
        result = SummaryResult("".join(summary_parts), used_ai, provider)
    else:
        result = summarize_paper(paper, source_text, explain_for=interest)
    emit("Summary report generated.", provider=result.provider, used_ai=result.used_ai)
    return paper, source_text, result


def _search_with_lookback(
    selected: date,
    categories: tuple[str, ...],
    candidate_count: int,
    lookback_days: int,
    progress=None,
):
    for offset in range(max(lookback_days, 0) + 1):
        current = selected - timedelta(days=offset)
        query = build_interest_query(categories, (), current)
        if progress:
            progress({"type": "progress", "message": f"Requesting arXiv: {current.isoformat()}, up to {candidate_count} papers.", "query": query})
        papers = search(query, max_results=candidate_count, sort_by="submittedDate")
        if progress:
            titles = [paper.title for paper in papers[:8]]
            progress({"type": "progress", "message": f"{current.isoformat()} fetched {len(papers)} papers.", "count": len(papers), "titles": titles})
        if papers or offset == lookback_days:
            return current, query, papers
    raise RuntimeError("unreachable")

def _required(payload: dict, key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _paper_json(paper: Paper) -> dict:
    return {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "summary": paper.summary,
        "authors": list(paper.authors),
        "published": paper.published,
        "updated": paper.updated,
        "categories": list(paper.categories),
        "pdf_url": paper.pdf_url,
        "abs_url": paper.abs_url,
    }


def _load_index_html() -> str:
    return FRONTEND_INDEX.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="arxiv-reader-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args(argv)

    state = AppState(args.config)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"arxiv-reader web UI: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

