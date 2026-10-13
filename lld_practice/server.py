"""Thin JSON-over-HTTP adapter (stdlib only). All logic lives in PracticeService."""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .domain import InvalidTransition, LLDError, NotFoundError, ValidationError

STATIC = Path(__file__).parent / "static"
MAX_BODY = 200_000
ROUTES = []


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return deco


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        # -- helpers
        def _send(self, code: int, payload, ctype="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValidationError("Request body too large.")
            if not n:
                return {}
            try:
                data = json.loads(self.rfile.read(n))
            except json.JSONDecodeError:
                raise ValidationError("Body must be valid JSON.")
            if not isinstance(data, dict):
                raise ValidationError("Body must be a JSON object.")
            return data

        def _dispatch(self, method: str):
            path, _, query = self.path.partition("?")
            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)
            q = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            learner = self.headers.get("X-Learner-Id", "demo-learner")
            try:
                for m, rx, fn in ROUTES:
                    match = rx.match(path)
                    if m == method and match:
                        code, payload = fn(service, learner, q, self._body() if method in ("POST", "PUT") else {},
                                           *match.groups())
                        return self._send(code, payload)
                self._send(404, {"error": "Not found"})
            except NotFoundError as e:
                self._send(404, {"error": str(e)})
            except ValidationError as e:
                self._send(422, {"error": str(e)})
            except InvalidTransition as e:
                self._send(409, {"error": str(e)})
            except LLDError as e:
                self._send(400, {"error": str(e)})
            except Exception:
                self._send(500, {"error": "Internal error"})

        def _static(self, path: str):
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (STATIC / name).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._send(404, {"error": "Not found"})
            ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(f.suffix[1:], "application/octet-stream")
            self._send(200, f.read_bytes(), ctype + "; charset=utf-8")

        def do_GET(self): self._dispatch("GET")
        def do_POST(self): self._dispatch("POST")
        def do_PUT(self): self._dispatch("PUT")

    return Handler


# ------------------------------------------------------------------ routes
@route("GET", "/api/problems")
def _problems(s, learner, q, body): return 200, s.list_problems()

@route("GET", r"/api/problems/([\w-]+)")
def _problem(s, learner, q, body, pid): return 200, s.get_problem(pid)

@route("GET", "/api/formats")
def _formats(s, learner, q, body): return 200, s.list_formats()

@route("POST", "/api/attempts")
def _start(s, learner, q, body):
    a = s.start_attempt(learner, str(body.get("problem_id", "")), body.get("based_on"))
    return 201, s.get_attempt(a.id)

@route("GET", "/api/attempts")
def _history(s, learner, q, body): return 200, s.history(learner, q.get("problem_id"))

@route("GET", r"/api/attempts/(\w+)")
def _attempt(s, learner, q, body, aid): return 200, s.get_attempt(aid)

@route("PUT", r"/api/attempts/(\w+)")
def _save(s, learner, q, body, aid):
    s.save_draft(aid, str(body.get("content", "")), str(body.get("format", "python")), str(body.get("rationale", "")))
    return 200, s.get_attempt(aid)

@route("POST", r"/api/attempts/(\w+)/submit")
def _submit(s, learner, q, body, aid):
    s.submit(aid)
    return 202, s.get_attempt(aid)

@route("POST", r"/api/attempts/(\w+)/retry")
def _retry(s, learner, q, body, aid):
    s.retry(aid)
    return 202, s.get_attempt(aid)


def serve(service, host="127.0.0.1", port=8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(service))
