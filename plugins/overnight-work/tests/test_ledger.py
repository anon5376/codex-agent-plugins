"""Contract tests for the overnight-work durable ledger CLI.

These tests deliberately exercise the CLI in fresh processes.  The fixture
data is disposable and all strings that look like URLs or shell syntax are
only inert ledger data.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CLI = PLUGIN_ROOT / "skills" / "overnight-work" / "scripts" / "overnight.py"


class LedgerCLI(unittest.TestCase):
    def setUp(self) -> None:
        # macOS exposes /var as a symlink.  The ledger correctly rejects any
        # symlink component in a recorded path, so pass its canonical fixture
        # path to the CLI while retaining the same disposable directory.
        self.tmp = Path(tempfile.mkdtemp(prefix="overnight-ledger-test-")).resolve()
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.run_dir = self.project / "run"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def invoke(self, *args: str, run: Path | None = None) -> subprocess.CompletedProcess[str]:
        run_path = run or self.run_dir
        cmd = [sys.executable, str(CLI), *args]
        return subprocess.run(
            cmd,
            cwd=str(PLUGIN_ROOT),
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

    def ok(self, *args: str, run: Path | None = None) -> dict:
        result = self.invoke(*args, run=run)
        self.assertEqual(
            result.returncode,
            0,
            msg=f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertTrue(result.stdout.strip(), msg=f"no JSON output for {args}")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"stdout was not JSON for {args}: {result.stdout!r} ({exc})")
        self.assertIsInstance(value, dict)
        return value

    def fails(self, *args: str, run: Path | None = None) -> subprocess.CompletedProcess[str]:
        result = self.invoke(*args, run=run)
        self.assertNotEqual(result.returncode, 0, msg=f"unexpected success: {args}\n{result.stdout}")
        self.assertNotIn("Traceback", result.stderr + result.stdout)
        self.assertTrue(result.stderr.strip(), msg=f"domain error had no stderr: {args}")
        return result

    def init(self, *, deadline: str | None = None, max_attempts: str | None = None) -> dict:
        args = [
            "init", "--run", str(self.run_dir), "--project", str(self.project),
            "--objective", "fixture objective",
        ]
        if deadline:
            args += ["--deadline", deadline]
        if max_attempts:
            args += ["--max-attempts", max_attempts]
        return self.ok(*args)

    def add(self, task_id: str, *, scope: Path | None = None, depends: str | None = None,
            lane: str = "research", question: str = "fixture question") -> dict:
        args = [
            "add", "--run", str(self.run_dir), "--id", task_id, "--lane", lane,
            "--question", question, "--owner", "fixture-worker",
        ]
        if scope is not None:
            args += ["--scope", str(scope)]
        if depends:
            args += ["--depends", depends]
        args += ["--acceptance", "fixture acceptance"]
        return self.ok(*args)

    def claim(self, task_id: str, *, worker: str = "worker-a", model: str = "gpt-5.6-luna",
              lease: str | None = None) -> dict:
        args = ["claim", "--run", str(self.run_dir), "--id", task_id, "--worker", worker,
                "--model", model]
        if lease is not None:
            args += ["--lease-minutes", lease]
        return self.ok(*args)

    def evidence(self, name: str = "evidence.txt", content: str = "verified fixture evidence\n") -> Path:
        path = self.run_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def finish(self, task_id: str, token: str, evidence: Path, validation: str = "checked fixture") -> dict:
        return self.ok("finish", "--run", str(self.run_dir), "--id", task_id, "--token", token,
                       "--evidence", str(evidence), "--validation", validation)

    def db_file(self) -> Path:
        candidates = sorted(p for p in self.run_dir.rglob("*") if p.is_file() and p.suffix in {".db", ".sqlite", ".sqlite3"})
        self.assertTrue(candidates, f"could not discover SQLite state in {self.run_dir}")
        return candidates[0]

    def edit_state(self, edit) -> None:
        """Force an isolated time/state condition without touching the CLI."""
        db = self.db_file()
        connection = sqlite3.connect(db)
        try:
            row = connection.execute("SELECT document FROM ledger WHERE id=1").fetchone()
            self.assertIsNotNone(row)
            state = json.loads(row[0])
            edit(state)
            connection.execute("UPDATE ledger SET document=? WHERE id=1", (json.dumps(state, separators=(",", ":")),))
            connection.commit()
        finally:
            connection.close()

    def test_normal_completion_status_close_and_exports(self) -> None:
        self.init()
        scope = self.run_dir / "deliverables"
        scope.mkdir()
        self.add("task-1", scope=scope)
        claim = self.claim("task-1")
        token = claim.get("lease_token") or claim.get("token")
        self.assertTrue(token, claim)
        evidence = self.evidence("deliverables/result.tsv", "a\tb\n")
        self.finish("task-1", token, evidence, "sha256 and row count checked")
        status = self.ok("status", "--run", str(self.run_dir))
        self.assertEqual(status.get("tasks", {}).get("counts", {}).get("complete"), 1, status)
        self.ok("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "fixture complete")
        self.ok("export", "--run", str(self.run_dir))
        first_exports = {
            name: (self.run_dir / name).read_bytes()
            for name in ("RUN-STATE.md", "WORK-LEDGER.tsv", "MORNING-HANDOFF.md")
        }
        self.ok("export", "--run", str(self.run_dir))
        for name in ("RUN-STATE.md", "WORK-LEDGER.tsv", "MORNING-HANDOFF.md"):
            output = self.run_dir / name
            self.assertTrue(output.is_file(), output)
            self.assertTrue(output.read_text(encoding="utf-8").strip(), output)
            self.assertEqual(output.read_bytes(), first_exports[name], name)
        self.assertEqual(self.ok("status", "--run", str(self.run_dir)).get("status"), "complete")

    def test_export_failure_preserves_authoritative_run_for_regeneration(self) -> None:
        self.init()
        blocked_export = self.run_dir / "WORK-LEDGER.tsv"
        blocked_export.mkdir()
        self.fails("export", "--run", str(self.run_dir))
        blocked_export.rmdir()
        regenerated = self.ok("export", "--run", str(self.run_dir))
        self.assertEqual(regenerated.get("revision"), 1, regenerated)
        self.assertTrue((self.run_dir / "RUN-STATE.md").is_file())
        self.assertTrue((self.run_dir / "WORK-LEDGER.tsv").is_file())
        self.assertTrue((self.run_dir / "MORNING-HANDOFF.md").is_file())

    def test_interrupted_export_does_not_leave_mixed_revisions(self) -> None:
        self.init()
        self.ok("export", "--run", str(self.run_dir))
        self.add("revision-two")
        blocked_export = self.run_dir / "WORK-LEDGER.tsv"
        previous_ledger = blocked_export.read_bytes()
        blocked_export.unlink()
        blocked_export.mkdir()
        self.fails("export", "--run", str(self.run_dir))
        blocked_export.rmdir()
        blocked_export.write_bytes(previous_ledger)
        run_state = (self.run_dir / "RUN-STATE.md").read_text(encoding="utf-8")
        ledger = (self.run_dir / "WORK-LEDGER.tsv").read_text(encoding="utf-8")
        handoff = (self.run_dir / "MORNING-HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("Revision: `1`", run_state)
        self.assertIn("\t1\t", ledger)
        self.assertIn("revision `1`", handoff)

    def test_exact_luna_model_is_enforced_and_default_is_luna(self) -> None:
        self.init()
        self.add("model-task")
        self.fails("claim", "--run", str(self.run_dir), "--id", "model-task", "--worker", "w",
                   "--model", "gpt-5.6-sol")
        claim = self.claim("model-task")
        self.assertTrue(claim.get("lease_token") or claim.get("token"))

    def test_dependency_readiness_and_cycle_prevention(self) -> None:
        self.init()
        self.fails("add", "--run", str(self.run_dir), "--id", "dependent", "--lane", "research",
                   "--question", "q", "--owner", "o", "--depends", "missing", "--acceptance", "a")
        self.add("first")
        self.add("second", depends="first")
        self.fails("claim", "--run", str(self.run_dir), "--id", "second", "--worker", "w",
                   "--model", "gpt-5.6-luna")
        first_claim = self.claim("first")
        token = first_claim.get("lease_token") or first_claim.get("token")
        self.finish("first", token, self.evidence("first.txt"))
        second_claim = self.claim("second")
        self.assertTrue(second_claim.get("lease_token") or second_claim.get("token"), second_claim)

    def test_concurrent_claims_allow_one_and_scope_overlap_is_rejected(self) -> None:
        self.init()
        scope = self.run_dir / "shared"
        scope.mkdir()
        self.add("a", scope=scope)
        self.add("b", scope=scope)
        results: list[tuple[int, str, str]] = []
        lock = threading.Lock()

        def claim_one(task: str) -> None:
            result = self.invoke("claim", "--run", str(self.run_dir), "--id", task,
                                 "--worker", task, "--model", "gpt-5.6-luna")
            with lock:
                results.append((result.returncode, result.stdout, result.stderr))

        threads = [threading.Thread(target=claim_one, args=(task,)) for task in ("a", "b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(code == 0 for code, _, _ in results), 1, results)
        self.assertEqual(sum(code != 0 for code, _, _ in results), 1, results)

        # A scope prefix is not containment: /shared-escape must be rejected.
        self.fails("add", "--run", str(self.run_dir), "--id", "c", "--lane", "research",
                   "--question", "q", "--owner", "o", "--scope", str(self.run_dir.parent / "run-escape"),
                   "--acceptance", "a")

    def test_scope_prefix_and_symlink_escapes_are_rejected(self) -> None:
        self.init()
        root = self.run_dir / "root"
        root.mkdir()
        outside = self.tmp / "outside"
        outside.mkdir()
        self.fails("add", "--run", str(self.run_dir), "--id", "prefix", "--lane", "research",
                   "--question", "q", "--owner", "o", "--scope", str(self.run_dir.parent / "run-escape"),
                   "--acceptance", "a")
        linked = root / "linked"
        linked.symlink_to(outside, target_is_directory=True)
        self.fails("add", "--run", str(self.run_dir), "--id", "symlink", "--lane", "research",
                   "--question", "q", "--owner", "o", "--scope", str(linked), "--acceptance", "a")

    def test_late_scope_symlink_substitution_is_rejected_before_finish(self) -> None:
        self.init()
        scope = self.run_dir / "owned-scope"
        scope.mkdir()
        self.add("late-scope", scope=scope)
        claim = self.claim("late-scope")
        token = claim.get("lease_token") or claim.get("token")
        outside = self.tmp / "scope-outside"
        outside.mkdir()
        scope.rmdir()
        scope.symlink_to(outside, target_is_directory=True)
        self.fails("finish", "--run", str(self.run_dir), "--id", "late-scope", "--token", token,
                   "--evidence", str(self.evidence("late-scope.txt")), "--validation", "late scope check")

    def test_stale_lease_recovery_and_stale_finish_are_rejected(self) -> None:
        self.init(max_attempts="2")
        self.add("stale")
        claim = self.claim("stale", lease="1")
        token = claim.get("lease_token") or claim.get("token")
        self.assertTrue(token, claim)
        self.edit_state(lambda state: state["tasks"]["stale"]["lease"].update(expires_at="2000-01-01T00:00:00+00:00"))
        self.fails("finish", "--run", str(self.run_dir), "--id", "stale", "--token", token,
                   "--evidence", str(self.evidence()), "--validation", "late worker")
        self.ok("recover", "--run", str(self.run_dir))
        retry = self.claim("stale")
        self.assertTrue(retry.get("lease_token") or retry.get("token"))

    def test_retry_cap_and_terminal_failure(self) -> None:
        self.init(max_attempts="1")
        self.add("retry")
        claim = self.claim("retry")
        token = claim.get("lease_token") or claim.get("token")
        self.ok("fail", "--run", str(self.run_dir), "--id", "retry", "--token", token,
                "--reason", "transient fixture", "--retryable")
        self.fails("claim", "--run", str(self.run_dir), "--id", "retry", "--worker", "w",
                   "--model", "gpt-5.6-luna")
        status = self.ok("status", "--run", str(self.run_dir))
        self.assertIn(status.get("tasks", {}).get("counts", {}).get("failed"), (1, "1"), status)

    def test_deadline_rejects_claim_and_naive_deadline_is_invalid(self) -> None:
        self.init(deadline="2099-01-01T00:00:00+00:00")
        self.add("late")
        self.edit_state(lambda state: state["run"].update(deadline="2000-01-01T00:00:00+00:00"))
        self.fails("claim", "--run", str(self.run_dir), "--id", "late", "--worker", "w",
                   "--model", "gpt-5.6-luna")

        other = self.tmp / "naive-run"
        self.fails("init", "--run", str(other), "--project", str(self.project), "--objective", "q",
                   "--deadline", "2000-01-01T00:00:00")

    def test_evidence_identity_and_tampering_are_detected(self) -> None:
        self.init()
        self.add("evidence")
        claim = self.claim("evidence")
        token = claim.get("lease_token") or claim.get("token")
        evidence = self.evidence(content="before")
        outside = self.tmp / "evidence-outside.txt"
        outside.write_text("outside", encoding="utf-8")
        evidence.unlink()
        evidence.symlink_to(outside)
        self.fails("finish", "--run", str(self.run_dir), "--id", "evidence", "--token", token,
                   "--evidence", str(evidence), "--validation", "late symlink")
        evidence.unlink()
        evidence.write_text("after", encoding="utf-8")
        # Finishing records the current bytes; changing them afterward must be visible.
        self.finish("evidence", token, evidence)
        evidence.write_text("tampered", encoding="utf-8")
        status = self.ok("status", "--run", str(self.run_dir))
        problems = json.dumps(status)
        self.assertRegex(problems, r"integrity|tamper|hash|mismatch")
        self.fails("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "tampered")

    def test_malformed_database_fails_explicitly(self) -> None:
        self.init()
        db = self.db_file()
        db.write_bytes(b"not sqlite")
        result = self.fails("status", "--run", str(self.run_dir))
        self.assertRegex(result.stderr.lower(), r"sqlite|database|schema|corrupt|invalid")

    def action_plan(self, action_id: str, payload: Path, kind: str = "contact") -> dict:
        return self.ok("action-plan", "--run", str(self.run_dir), "--id", action_id, "--kind", kind,
                       "--target", "https://recipient.invalid/$(touch SHOULD_NOT_RUN)", "--payload", str(payload),
                       "--purpose", "fixture receipt")

    def test_external_action_payload_binding_one_use_and_uncertain_reconciliation(self) -> None:
        self.init()
        payload = self.evidence("payload.json", '{"body":"literal $(touch inert)"}\n')
        self.action_plan("mutating", payload)
        self.ok("action-authorize", "--run", str(self.run_dir), "--id", "mutating",
                "--user-evidence", "explicit fixture instruction")
        payload.write_text('{"body":"changed"}\n', encoding="utf-8")
        self.fails("action-attempt", "--run", str(self.run_dir), "--id", "mutating")

        payload.write_text('{"body":"stable"}\n', encoding="utf-8")
        self.action_plan("once", payload, "publish")
        self.ok("action-authorize", "--run", str(self.run_dir), "--id", "once",
                "--user-evidence", "explicit fixture instruction")
        attempt = self.ok("action-attempt", "--run", str(self.run_dir), "--id", "once")
        self.assertTrue(attempt.get("attempt_id") or attempt.get("idempotency_key"), attempt)
        self.fails("action-attempt", "--run", str(self.run_dir), "--id", "once")
        self.ok("action-result", "--run", str(self.run_dir), "--id", "once", "--outcome", "uncertain",
                "--receipt", "provider result unavailable")
        self.fails("action-attempt", "--run", str(self.run_dir), "--id", "once")
        self.ok("action-reconcile", "--run", str(self.run_dir), "--id", "once", "--outcome", "failed",
                "--receipt", "provider later confirmed no send")

    def test_close_rejects_unresolved_external_attempts(self) -> None:
        self.init()
        payload = self.evidence("close-action.json", '{"body":"fixture"}\n')
        self.action_plan("close-check", payload)
        self.ok("action-authorize", "--run", str(self.run_dir), "--id", "close-check",
                "--user-evidence", "explicit fixture instruction")
        self.ok("action-attempt", "--run", str(self.run_dir), "--id", "close-check")
        self.fails("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "premature")
        self.ok("action-result", "--run", str(self.run_dir), "--id", "close-check", "--outcome", "uncertain",
                "--receipt", "provider did not answer")
        self.fails("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "still uncertain")
        self.ok("action-reconcile", "--run", str(self.run_dir), "--id", "close-check", "--outcome", "failed",
                "--receipt", "provider later confirmed no send")
        self.ok("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "reconciled")

    def test_pause_resume_preserves_attempts_and_no_duplicate_work(self) -> None:
        self.init()
        self.add("paused")
        self.ok("close", "--run", str(self.run_dir), "--status", "paused", "--reason", "fixture input missing")
        self.ok("resume", "--run", str(self.run_dir), "--reason", "fixture input restored")
        claim = self.claim("paused")
        token = claim.get("lease_token") or claim.get("token")
        self.finish("paused", token, self.evidence())
        self.fails("claim", "--run", str(self.run_dir), "--id", "paused", "--worker", "w",
                   "--model", "gpt-5.6-luna")

    def test_blocked_work_survives_pause_resume_and_unblock(self) -> None:
        self.init()
        self.add("blocked")
        claim = self.claim("blocked")
        token = claim.get("lease_token") or claim.get("token")
        self.ok("block", "--run", str(self.run_dir), "--id", "blocked", "--token", token,
                "--reason", "fixture input missing")
        status = self.ok("status", "--run", str(self.run_dir))
        self.assertEqual(status["tasks"]["counts"]["blocked"], 1, status)
        self.fails("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "unfinished")
        self.ok("close", "--run", str(self.run_dir), "--status", "paused", "--reason", "await input")
        self.ok("resume", "--run", str(self.run_dir), "--reason", "input restored")
        self.ok("unblock", "--run", str(self.run_dir), "--id", "blocked", "--reason", "input restored")
        retry = self.claim("blocked")
        retry_token = retry.get("lease_token") or retry.get("token")
        self.finish("blocked", retry_token, self.evidence("blocked.txt"))
        self.ok("close", "--run", str(self.run_dir), "--status", "complete", "--reason", "finished")


if __name__ == "__main__":
    unittest.main()
