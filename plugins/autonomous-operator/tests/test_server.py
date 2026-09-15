from __future__ import annotations

import http.client
import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "server.py"
URL_PATTERN = re.compile(r"http://127\.0\.0\.1:(\d+)")


class RunningServer:
    def __init__(
        self,
        data_dir: Path,
        *,
        environment: dict[str, str] | None = None,
    ) -> None:
        command = [
            sys.executable,
            "-u",
            str(SERVER),
            "--port",
            "0",
            "--data-dir",
            str(data_dir),
        ]
        child_environment = os.environ.copy()
        child_environment.update(environment or {})
        self.process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=child_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.base_url = self._read_url()
        self.port = int(self.base_url.rsplit(":", 1)[1])

    def _read_url(self) -> str:
        assert self.process.stdout is not None
        deadline = time.monotonic() + 8
        seen: list[str] = []
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            ready, _, _ = select.select([self.process.stdout], [], [], 0.2)
            if not ready:
                continue
            line = self.process.stdout.readline()
            if not line:
                continue
            seen.append(line.rstrip())
            match = URL_PATTERN.search(line)
            if match:
                return f"http://127.0.0.1:{match.group(1)}"
        stderr = ""
        if self.process.poll() is not None and self.process.stderr is not None:
            stderr = self.process.stderr.read()
        self.close()
        raise AssertionError(
            "server did not announce its loopback URL; "
            f"stdout={seen!r} stderr={stderr!r}"
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: object | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], object]:
        request_headers = dict(headers or {})
        payload: bytes | None
        if isinstance(body, bytes):
            payload = body
        elif body is None:
            payload = None
        else:
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, body=payload, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        if response_headers.get("content-type", "").startswith("application/json"):
            parsed: object = json.loads(raw.decode("utf-8"))
        else:
            parsed = raw
        return response.status, response_headers, parsed

    def close(self) -> None:
        if getattr(self, "process", None) is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()


class OperatorServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temporary.name).resolve()
        self.data_dir = self.temp_path / "data"
        self.project_dir = self.temp_path / "project"
        self.project_dir.mkdir()
        self.context_file = self.project_dir / "context.txt"
        self.context_file.write_text("reference only\n", encoding="utf-8")
        self.server: RunningServer | None = None

    def tearDown(self) -> None:
        if self.server is not None:
            self.server.close()
        self.temporary.cleanup()

    def start_server(
        self,
        *,
        environment: dict[str, str] | None = None,
    ) -> RunningServer:
        if self.server is not None:
            self.server.close()
        self.server = RunningServer(
            self.data_dir,
            environment=environment,
        )
        return self.server

    def valid_mission(self, **updates: object) -> dict[str, object]:
        mission: dict[str, object] = {
            "title": "Bounded operator test",
            "objective": "Inspect the local fixture and prepare an evidence-backed result.",
            "project_path": str(self.project_dir),
            "work_types": ["research", "testing"],
            "deliverables": "A concise local report.",
            "success_criteria": "The stated checks pass with exact output.",
            "constraints": "Do not contact anyone or publish anything.",
            "context_files": [str(self.context_file)],
            "max_astra": 1,
            "max_luna": 8,
            "budget_mode": "hours",
            "budget_value": 8,
            "pro_enabled": True,
            "pro_messages": 5,
            "pro_project": "Novel Biotech",
            "external_mode": "prepare",
            "external_scope": "",
            "private_boundary": "Keep private records local.",
        }
        mission.update(updates)
        return mission

    def config(self, server: RunningServer) -> tuple[str, dict[str, object]]:
        status, headers, body = server.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertIsInstance(body, dict)
        config = body
        self.assertEqual(headers.get("cache-control"), "no-store")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(
            set(config),
            {"csrf_token", "default_project", "defaults", "models", "work_types"},
        )
        return str(config["csrf_token"]), config

    def post_json(
        self,
        server: RunningServer,
        path: str,
        body: object,
        token: str,
        **headers: str,
    ) -> tuple[int, dict[str, str], object]:
        request_headers = {"X-Operator-Token": token, **headers}
        return server.request("POST", path, body=body, headers=request_headers)

    def test_config_preview_save_list_detail_and_restart_round_trip(self) -> None:
        server = self.start_server()
        token, config = self.config(server)
        self.assertIn("gpt-6-astra", json.dumps(config["models"]))
        self.assertIn("xhigh", json.dumps(config["models"]).lower())
        self.assertIn("gpt-5.6-sol", json.dumps(config["models"]))
        self.assertIn("high", json.dumps(config["models"]).lower())
        self.assertIn("gpt-5.6-luna", json.dumps(config["models"]))
        self.assertIn("max", json.dumps(config["models"]).lower())
        self.assertEqual(
            config["work_types"],
            [
                "research",
                "development",
                "brainstorm",
                "simulation",
                "testing",
                "visuals",
                "outreach",
                "email_setup",
                "meetings",
            ],
        )

        mission = self.valid_mission()
        status, _, preview = self.post_json(server, "/api/preview", mission, token)
        self.assertEqual(status, 200)
        self.assertEqual(preview["mission"]["project_path"], str(self.project_dir))
        prompt = preview["prompt"]
        for expected in (
            "gpt-6-astra",
            "xhigh",
            "gpt-5.6-sol",
            "high",
            "gpt-5.6-luna",
            "max",
            "ordinary ChatGPT Web",
            "Novel Biotech",
            "8 hours",
            "prepare",
            "smallest sufficient",
            "runtime",
            "luna max",
            "sol high",
            "astra xhigh",
            "bounded correction",
            "affected review",
        ):
            self.assertIn(expected.lower(), prompt.lower())
        prompt_lower = prompt.lower()
        order_section = prompt_lower.split("delegation and review order", 1)[1].split(
            "execution rules", 1
        )[0]
        review_section = order_section.index("review upward")
        delegation_text = order_section[:review_section]
        review_text = order_section[review_section:]
        self.assertLess(
            delegation_text.index("astra xhigh"), delegation_text.index("sol high")
        )
        self.assertLess(
            delegation_text.index("sol high"), delegation_text.index("luna max")
        )
        self.assertLess(
            review_text.index("luna max"), review_text.index("sol high")
        )
        self.assertLess(
            review_text.index("sol high"), review_text.index("astra xhigh")
        )

        status, _, saved = self.post_json(server, "/api/missions", mission, token)
        self.assertEqual(status, 201)
        mission_id = saved["id"]
        self.assertRegex(mission_id, r"^[A-Za-z0-9_-]{16,}$")
        self.assertEqual(saved["status"], "prepared")
        self.assertEqual(saved["prompt"], prompt)
        self.assertEqual(self.data_dir.stat().st_mode & 0o777, 0o700)
        mission_file = next((self.data_dir / "missions").glob("*/mission.json"))
        self.assertEqual(mission_file.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(mission_file.stat().st_mode & 0o777, 0o600)

        status, _, listing = server.request("GET", "/api/missions")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in listing["missions"]], [mission_id])
        status, _, detail = server.request("GET", f"/api/missions/{mission_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["mission"], saved["mission"])
        self.assertEqual(detail["prompt"], prompt)

        server.close()
        self.server = None
        restarted = self.start_server()
        status, _, detail_after_restart = restarted.request(
            "GET", f"/api/missions/{mission_id}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(detail_after_restart["prompt"], prompt)

    def test_defaults_and_validation_errors_are_explicit(self) -> None:
        server = self.start_server()
        token, _ = self.config(server)

        minimal = {
            "objective": "Prepare a bounded local mission.",
            "project_path": str(self.project_dir),
            "work_types": ["research"],
        }
        status, _, preview = self.post_json(server, "/api/preview", minimal, token)
        self.assertEqual(status, 200)
        normalized = preview["mission"]
        self.assertEqual(normalized["max_astra"], 1)
        self.assertEqual(normalized["max_luna"], 8)
        self.assertEqual(normalized["budget_mode"], "hours")
        self.assertEqual(normalized["budget_value"], 8)
        self.assertTrue(normalized["pro_enabled"])
        self.assertEqual(normalized["pro_messages"], 5)
        self.assertEqual(normalized["external_mode"], "prepare")
        self.assertTrue(normalized["title"])

        invalid_cases = (
            ({**minimal, "unexpected": True}, "unexpected"),
            ({**minimal, "objective": ""}, "objective"),
            ({**minimal, "project_path": "relative/path"}, "project_path"),
            ({**minimal, "project_path": str(self.temp_path / "missing")}, "project_path"),
            ({**minimal, "work_types": []}, "work_types"),
            ({**minimal, "work_types": ["research", "research"]}, "work_types"),
            ({**minimal, "max_astra": 5}, "max_astra"),
            ({**minimal, "max_luna": 65}, "max_luna"),
            ({**minimal, "budget_mode": "manual", "budget_value": 1}, "budget_value"),
            ({**minimal, "budget_mode": "tokens", "budget_value": 100000001}, "budget_value"),
            ({**minimal, "pro_enabled": True, "pro_messages": 0}, "pro_messages"),
            ({**minimal, "external_mode": "scoped", "external_scope": ""}, "external_scope"),
            ({**minimal, "context_files": ["relative.txt"]}, "context_files"),
        )
        for payload, field in invalid_cases:
            with self.subTest(field=field, payload=payload):
                status, _, error = self.post_json(server, "/api/preview", payload, token)
                self.assertEqual(status, 400)
                self.assertIn("error", error)
                fields = error.get("fields", {})
                self.assertTrue(
                    field in fields or field in str(error["error"]),
                    f"{field!r} missing from {error!r}",
                )

    def test_host_origin_csrf_json_size_and_route_controls(self) -> None:
        server = self.start_server()
        token, _ = self.config(server)
        mission = self.valid_mission()

        status, _, _ = server.request(
            "GET", "/api/config", headers={"Host": "operator.example"}
        )
        self.assertIn(status, (400, 403))

        status, _, error = server.request("POST", "/api/preview", body=mission)
        self.assertIn(status, (400, 403))
        self.assertIn("error", error)
        status, _, error = self.post_json(
            server,
            "/api/preview",
            mission,
            token,
            Origin="https://operator.example",
        )
        self.assertIn(status, (400, 403))
        self.assertIn("error", error)

        status, _, malformed = server.request(
            "POST",
            "/api/preview",
            body=b"{not-json",
            headers={
                "Content-Type": "application/json",
                "X-Operator-Token": token,
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("error", malformed)

        status, _, too_large = server.request(
            "POST",
            "/api/preview",
            body=b"x" * 300_000,
            headers={
                "Content-Type": "application/json",
                "X-Operator-Token": token,
            },
        )
        self.assertIn(status, (400, 413))
        self.assertIn("error", too_large)

        status, _, _ = server.request("GET", "/api/not-real")
        self.assertEqual(status, 404)
        status, _, _ = server.request("GET", "/../PRODUCT.md")
        self.assertEqual(status, 404)

    def test_preview_save_reload_and_launch_like_route_never_execute_codex(self) -> None:
        marker = self.temp_path / "fake-codex-ran"
        injection_marker = self.temp_path / "user-text-ran"
        fake_bin = self.temp_path / "bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        fake_codex.write_text(
            "#!/bin/sh\n"
            f"printf ran > {marker!s}\n"
            "exit 99\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o700)
        server = self.start_server(
            environment={
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            }
        )
        token, _ = self.config(server)
        objective = f"Prepare evidence; $(touch {injection_marker})"
        mission = self.valid_mission(objective=objective)
        status, _, preview = self.post_json(server, "/api/preview", mission, token)
        self.assertEqual(status, 200)
        self.assertIn(objective, preview["prompt"])
        self.assertFalse(injection_marker.exists())
        status, _, saved = self.post_json(server, "/api/missions", mission, token)
        self.assertEqual(status, 201)
        server.request("GET", "/api/missions")
        server.request("GET", f"/api/missions/{saved['id']}")
        server.close()
        self.server = None
        restarted = self.start_server(
            environment={
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            }
        )
        restarted.request("GET", "/api/missions")
        restarted.request("GET", f"/api/missions/{saved['id']}")
        self.assertFalse(marker.exists())

        restart_token, _ = self.config(restarted)
        status, _, disabled = self.post_json(
            restarted,
            f"/api/missions/{saved['id']}/launch",
            {},
            restart_token,
        )
        self.assertEqual(status, 404)
        self.assertIn("error", disabled)
        self.assertFalse(marker.exists())
        self.assertFalse(injection_marker.exists())

    def test_user_values_exist_only_inside_delimited_mission_json(self) -> None:
        server = self.start_server()
        token, _ = self.config(server)
        scoped = "SCOPE_SENTINEL $(touch should-not-run)"
        private = "PRIVATE_SENTINEL never disclose this line"
        context = str(self.context_file)
        mission = self.valid_mission(
            external_mode="scoped",
            external_scope=scoped,
            private_boundary=private,
        )
        status, _, preview = self.post_json(server, "/api/preview", mission, token)
        self.assertEqual(status, 200)
        prompt = preview["prompt"]
        before, remainder = prompt.split("--- BEGIN MISSION JSON ---", 1)
        inside, after = remainder.split("--- END MISSION JSON ---", 1)
        for value in (scoped, private, context):
            self.assertNotIn(value, before)
            self.assertIn(value, inside)
            self.assertNotIn(value, after)


if __name__ == "__main__":
    unittest.main()
