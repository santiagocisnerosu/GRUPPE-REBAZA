import http.client
import json
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import live_server as live
from src.listeners import CORE, register


class LiveServerTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        root = Path(stack.enter_context(TemporaryDirectory()))
        self.public, self.private = root / "docs", root / "live"
        (self.public / "out").mkdir(parents=True)
        self.private.mkdir()
        self.page = b"<html><body>Morning Edition</body></html>"
        (self.public / "index.html").write_bytes(self.page)
        stack.enter_context(patch.object(live, "DOCS", self.public))
        stack.enter_context(patch.object(live, "LIVE", self.private))
        stack.enter_context(patch.object(live, "run_cost", return_value=0.0123))
        stack.enter_context(patch.dict("os.environ", {k: "fixture" for k in (
            "OPENAI_API_KEY", "OPENAI_SMALL_MODEL", "OPENAI_LARGE_MODEL", "ELEVENLABS_API_KEY", "ELEVENLABS_MODEL")}))
        server = live.ThreadingHTTPServer(("127.0.0.1", 0), live.Handler)
        server.jobs = live.Jobs()
        self.port = server.server_port
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None,
                               headers or {"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read()
            if response.getheader("Content-Type", "").startswith("application/json"):
                data = json.loads(data)
            return response.status, data
        finally:
            connection.close()

    def finished(self, job):
        for _ in range(100):
            status, result = self.request("GET", "/api/wildcard/" + job)
            if status == 200 and result["step"] in ("failed", "done"):
                return result
            time.sleep(0.01)
        self.fail("Worker did not finish")

    def test_reset_archives_the_entire_session_and_clears_the_live_roster(self):
        listener = "wildcard-nl-0123456789ab"
        register(self.private, dict(id=listener, name="Jan", role="Retiree", language="nl"))
        manifest = (self.private / "listeners.json").read_bytes()
        (self.private / listener).mkdir()
        (self.private / listener / "briefing.mp3").write_bytes(b"audio")
        (self.private / "profiles_wildcard.yaml").write_bytes(b"profiles")
        (self.private / ".session").write_bytes(b"log")
        live.reset_live()
        parent = self.private.parent / "live-archive"
        archive, = parent.iterdir()
        self.assertRegex(archive.name, r"^\d{8}T\d{12}Z$")
        self.assertEqual((archive / "listeners.json").read_bytes(), manifest)
        self.assertEqual((archive / listener / "briefing.mp3").read_bytes(), b"audio")
        self.assertEqual((archive / "profiles_wildcard.yaml").read_bytes(), b"profiles")
        self.assertEqual((archive / ".session").read_bytes(), b"log")
        self.assertEqual(list(self.private.iterdir()), [])
        self.assertEqual(self.request("GET", "/out/listeners.json"), (200, CORE))
        self.assertEqual(self.request("GET", f"/out/{listener}/briefing.mp3")[0], 404)
        live.reset_live()
        self.assertEqual(list(parent.iterdir()), [archive])

    def test_reset_requires_a_successful_bind(self):
        with patch("sys.argv", ["src.live_server", "--reset"]), patch.object(live, "load_dotenv"), \
             patch.object(live.ThreadingHTTPServer, "server_bind", side_effect=OSError("occupied")), \
             patch.object(live, "reset_live") as reset:
            with self.assertRaisesRegex(SystemExit, "already using that port"):
                live.main()
            reset.assert_not_called()

    def test_job_progress_and_private_delivery(self):
        writing, finish = threading.Event(), threading.Event()
        listener = "wildcard-en-0123456789ab"

        def generate(args, small, large, run_id, *, progress, local_root):
            self.assertTrue(args.no_publish)
            self.assertIsNone(args.language)
            self.assertEqual(local_root, self.private)
            progress("writing and checking")
            writing.set()
            self.assertTrue(finish.wait(5))
            progress("voicing")
            folder = local_root / listener
            folder.mkdir()
            (folder / "briefing.mp3").write_bytes(b"mock audio")
            (folder / "transcript.json").write_text('{"name":"Sam"}', encoding="utf8")
            (folder / "script.json").write_text("private", encoding="utf8")
            register(local_root, dict(id=listener, role="Teacher", name="Sam", language="en"))
            return 3, folder

        with patch.object(live, "generate", generate):
            payload = dict(description="A retired teacher", language="auto")
            status, accepted = self.request("POST", "/api/wildcard", payload)
            try:
                self.assertEqual(status, 202)
                self.assertTrue(writing.wait(2))
                self.assertEqual(self.request("POST", "/api/wildcard", payload)[0], 409)
                state = self.request("GET", "/api/wildcard/" + accepted["job"])[1]
                self.assertEqual(state["step"], "writing and checking")
                self.assertGreaterEqual(state["elapsed_seconds"], 0)
                self.assertEqual(state["cost"], 0.0123)
                self.assertIsNone(state["listener_id"])
            finally:
                finish.set()
            done = self.finished(accepted["job"])
        self.assertEqual((done["step"], done["listener_id"]), ("done", listener))
        self.assertIsNone(self.request("GET", "/api/health")[1]["active_job"])
        self.assertEqual(self.request("GET", "/out/listeners.json")[1][-1]["id"], listener)
        self.assertEqual(self.request("GET", f"/out/{listener}/briefing.mp3"), (200, b"mock audio"))
        self.assertEqual(self.request("GET", f"/out/{listener}/script.json")[0], 404)
        self.assertFalse(list((self.public / "out").iterdir()))

    def test_local_page_input_and_failure(self):
        self.assertIn(b"listener-panel", self.request("GET", "/")[1])
        self.assertEqual((self.public / "index.html").read_bytes(), self.page)
        self.assertEqual(self.request("GET", "/api/health")[1]["service"], "receipts-live")
        self.assertEqual(self.request("GET", "/api/wildcard/unknown")[0], 404)
        payload = dict(description="A teacher", language="en")
        self.assertEqual(self.request("POST", "/api/wildcard", {**payload, "language": "xx"})[0], 400)
        self.assertEqual(self.request("POST", "/api/wildcard", payload, {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/wildcard", payload,
                                      {"Content-Type": "application/json", "Origin": "https://example.org"})[0], 403)
        def fail_mastering(*args, progress, **kwargs):
            progress("voicing")
            raise ValueError("MP3 missed mastering targets: -17.2 LUFS, -5.4 dBTP")

        with patch.object(live, "generate", side_effect=fail_mastering):
            for _ in range(2):
                status, accepted = self.request("POST", "/api/wildcard", payload)
                self.assertEqual(status, 202)
                result = self.finished(accepted["job"])
                self.assertEqual(result["step"], "failed")
                self.assertEqual(result["error"], "Voicing failed. MP3 missed mastering targets: -17.2 LUFS, -5.4 dBTP")
        self.assertEqual(live.error_message(RuntimeError("Invalid key fixture"), "voicing"),
                         "Voicing failed. Invalid key [redacted]")
