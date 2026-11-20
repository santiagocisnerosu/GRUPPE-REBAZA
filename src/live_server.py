"""Serve Morning Edition and build new listeners on the finals laptop."""
import io
import json
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import traceback
import uuid
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import ValidationError

from .listeners import roster
from .wildcard import LANGUAGES, ROOT, generate, run_cost

DOCS = ROOT / "docs"
LIVE = ROOT / "out" / "live"
ASSETS = ROOT / "web" / "live"


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: float = field(default_factory=time.monotonic)
    step: str = "profile"
    ended: float | None = None
    listener_id: str | None = None
    error: str | None = None


def error_message(exc, step):
    if isinstance(exc, KeyError) and exc.args and exc.args[0] in (
        "OPENAI_API_KEY", "OPENAI_SMALL_MODEL", "OPENAI_LARGE_MODEL", "ELEVENLABS_MODEL", "ELEVENLABS_API_KEY"
    ):
        return f"Set {exc.args[0]} in the laptop’s .env and restart the server."
    if isinstance(exc, ValidationError):
        # Report which field failed without echoing the submitted document.
        errors = exc.errors(include_input=False, include_context=False, include_url=False)
        detail = ", ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in errors)
    else:
        detail = str(exc) or type(exc).__name__
    for name in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        secret = os.getenv(name)
        if secret:
            detail = detail.replace(secret, "[redacted]")
    return f"{step.capitalize()} failed. {detail[:500]}"


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}
        self.active = None
        self.models = {os.getenv("OPENAI_SMALL_MODEL"): "small_model", os.getenv("OPENAI_LARGE_MODEL"): "large_model"}

    def start(self, description, language):
        with self.lock:
            if self.active:
                return None
            job = Job()
            self.items[job.id] = job
            self.active = job.id
            threading.Thread(target=self.run, args=(job, description, language)).start()
            return job.id

    def run(self, job, description, language):
        def progress(step):
            with self.lock:
                job.step = step

        listener_id = error = None
        try:
            for key in ("OPENAI_API_KEY", "OPENAI_SMALL_MODEL", "OPENAI_LARGE_MODEL", "ELEVENLABS_API_KEY", "ELEVENLABS_MODEL"):
                if not os.getenv(key):
                    raise KeyError(key)
            args = Namespace(description=description, language=None if language == "auto" else language,
                             dry_run=False, no_publish=True)
            _, folder = generate(args, os.environ["OPENAI_SMALL_MODEL"], os.environ["OPENAI_LARGE_MODEL"],
                                 job.id, progress=progress, local_root=LIVE)
            listener_id = folder.name
        except (Exception, SystemExit) as exc:
            error = error_message(exc, job.step)
            traceback.print_tb(exc.__traceback__)
            print(f"Job {job.id} ({type(exc).__name__}): {error}", file=sys.stderr, flush=True)
        finally:
            with self.lock:
                job.listener_id, job.error = listener_id, error
                job.step = "done" if listener_id else "failed"
                job.ended = time.monotonic()
                self.active = None

    def status(self, job_id):
        with self.lock:
            job = self.items.get(job_id)
            if not job:
                return None
            status = dict(job=job.id, step=job.step, listener_id=job.listener_id, error=job.error,
                          elapsed_seconds=round((job.ended or time.monotonic()) - job.started, 1))
        status["cost"] = float(round(run_cost(job_id, self.models), 6))
        return status


def local_roster():
    published = roster(DOCS / "out")
    frozen = {entry["id"] for entry in published}
    return published + [entry for entry in roster(LIVE) if entry["id"] not in frozen]


def reset_live():
    output = LIVE.parent.resolve()
    live = output / LIVE.name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = output / "live-archive" / timestamp
    if live.resolve() != live or archive.resolve() != archive:
        raise ValueError("Expected the live directory and archive inside the local output directory")
    if live.exists() and any(live.iterdir()):
        archive.parent.mkdir(exist_ok=True)
        if archive.exists():
            raise FileExistsError(f"Archive already exists: {archive}")
        live.rename(archive)
        print(f"Archived live listeners to {archive}", flush=True)
    live.mkdir(parents=True, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def local_request(self):
        port = self.server.server_port
        host = self.headers.get("Host", "")
        if host not in {f"localhost:{port}", f"127.0.0.1:{port}"}:
            self.send_error(403)
            return False
        return True

    def buffered(self, content, kind, status=200):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        return io.BytesIO(content)

    def json(self, value, status=200):
        return self.buffered(json.dumps(value).encode(), "application/json; charset=utf-8", status)

    def send_head(self):
        if not self.local_request():
            return None
        path = urlsplit(self.path).path
        if path == "/api/health":
            return self.json({"service": "receipts-live", "active_job": self.server.jobs.active})
        if path.startswith("/api/"):
            match = re.fullmatch(r"/api/wildcard/([a-f0-9]{32})", path)
            result = self.server.jobs.status(match[1]) if match else None
            return self.json(result or {"error": "Job not found."}, 200 if result else 404)
        if path in ("/", "/index.html"):
            page = (DOCS / "index.html").read_bytes().replace(b"</body>", (ASSETS / "panel.html").read_bytes() + b"\n</body>")
            return self.buffered(page, "text/html; charset=utf-8")
        if path in ("/_live/panel.css", "/_live/panel.js"):
            file = ASSETS / Path(path).name
            return self.buffered(file.read_bytes(), "text/css" if file.suffix == ".css" else "text/javascript")
        if path == "/out/listeners.json":
            return self.json(local_roster())
        match = re.fullmatch(r"/out/(wildcard-(?:en|de|nl)-[a-f0-9]{12})/(briefing\.mp3|transcript\.json)", path)
        if match and not (DOCS / "out" / match[1]).exists():
            if any(entry["id"] == match[1] for entry in roster(LIVE)):
                file = LIVE / match[1] / match[2]
                if file.is_file():
                    return self.buffered(file.read_bytes(), mimetypes.guess_type(file.name)[0])
            self.send_error(404)
            return None
        return super().send_head()

    def do_POST(self):
        if not self.local_request():
            return
        if self.path != "/api/wildcard":
            self.send_error(404)
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + self.headers["Host"]:
            self.send_error(403)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            size = int(self.headers.get("Content-Length", ""))
            if not 0 < size <= 16384:
                raise ValueError
            body = json.loads(self.rfile.read(size))
            description = body["description"].strip()
            language = body["language"]
            if not description or len(description) > 2000 or language not in ("auto", *LANGUAGES):
                raise ValueError
        except (AttributeError, KeyError, TypeError, ValueError):
            result = self.json({"error": "Enter a listener description and select a supported language."}, 400)
        else:
            job = self.server.jobs.start(description, language)
            result = (self.json({"job": job}, 202) if job else
                      self.json({"error": "Another briefing is being created. Try again when it finishes."}, 409))
        with result:
            self.copyfile(result, self.wfile)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="Archive all of out/live and start with only the three core listeners")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    with ThreadingHTTPServer(("127.0.0.1", 8000), Handler, bind_and_activate=False) as server:
        server.allow_reuse_port = False
        if os.name == "nt":
            server.allow_reuse_address = False
            server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            server.server_bind()
            server.server_activate()
        except OSError as exc:
            raise SystemExit(f"Cannot listen on 127.0.0.1:8000. Stop the server already using that port and retry. ({exc})") from None
        if args.reset:
            reset_live()
        server.jobs = Jobs()
        print("Morning Edition is live at http://localhost:8000", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
