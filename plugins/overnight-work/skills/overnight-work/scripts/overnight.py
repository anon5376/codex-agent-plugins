#!/usr/bin/env python3
"""Durable, local-only ledger for bounded overnight work.

The ledger records work and external-action receipts.  It never invokes a
model, connector, shell command, or network operation.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
DB_NAME = "run.sqlite3"
DEFAULT_MODEL = "gpt-5.6-luna"
LANES = ("website", "research", "brainstorm", "contact", "visual", "integration")
MAX_INTEGER = 1000


class LedgerError(Exception):
    """Expected user or state error; rendered without a traceback."""


def _nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{label} must be nonempty")
    return value


def _flatten(values) -> list[str]:
    """Flatten repeatable nargs='+' options while accepting one occurrence."""
    if not values:
        return []
    return [item for group in values for item in (group if isinstance(group, list) else [group])]


def _positive(value: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("must be a positive integer")
    if number < 1 or number > MAX_INTEGER:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_INTEGER}")
    return number


def _absolute(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise LedgerError("path must be nonempty")
    return os.path.abspath(os.path.expanduser(path))


def _reject_symlink_components(path: str) -> None:
    """Reject a path whose existing component is a symlink."""
    absolute = _absolute(path)
    absolute_path = Path(absolute)
    current = Path(absolute_path.anchor or os.sep)
    for component in absolute_path.parts[1:]:
        current /= component
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise LedgerError(f"cannot inspect path {absolute}: {exc}")
        if stat.S_ISLNK(info.st_mode):
            raise LedgerError(f"symlink path is not allowed: {absolute}")


def _existing_directory(path: str, label: str) -> str:
    absolute = _absolute(path)
    _reject_symlink_components(absolute)
    try:
        info = os.stat(absolute)
    except OSError as exc:
        raise LedgerError(f"{label} must be an existing directory: {exc}")
    if not stat.S_ISDIR(info.st_mode):
        raise LedgerError(f"{label} must be an existing directory")
    return absolute


def _within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def _parse_deadline(value: str | None, label: str = "deadline") -> str | None:
    if value is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LedgerError(f"{label} must be ISO8601")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerError(f"{label} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_time(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise LedgerError("invalid stored timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerError("invalid stored timestamp timezone")
    return parsed.astimezone(dt.timezone.utc)


def _deadline_expired(state: dict) -> bool:
    deadline = state["run"].get("deadline")
    return deadline is not None and _now() >= _parse_time(deadline)


def _ensure_safe_root(path: str) -> str:
    absolute = _absolute(path)
    _reject_symlink_components(absolute)
    if os.path.lexists(absolute) and not os.path.isdir(absolute):
        raise LedgerError(f"write root must be a directory: {absolute}")
    return absolute


def _ensure_inside_roots(path: str, roots: list[str], label: str, *, must_exist: bool = False) -> str:
    absolute = _absolute(path)
    _reject_symlink_components(absolute)
    if not any(_within(absolute, root) for root in roots):
        raise LedgerError(f"{label} is outside recorded write roots: {absolute}")
    if must_exist and not os.path.exists(absolute):
        raise LedgerError(f"{label} does not exist: {absolute}")
    return absolute


def _load_file_bytes(path: str, label: str) -> tuple[bytes, int]:
    """Open safely and read a regular file without following final symlinks."""
    _reject_symlink_components(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise LedgerError(f"{label} cannot be opened: {exc}")
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise LedgerError(f"{label} must be a regular file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        return content, len(content)
    except OSError as exc:
        raise LedgerError(f"{label} cannot be read: {exc}")
    finally:
        os.close(fd)


def _digest_file(path: str, label: str) -> tuple[str, int]:
    content, size = _load_file_bytes(path, label)
    return hashlib.sha256(content).hexdigest(), size


def _connect(run_dir: str) -> sqlite3.Connection:
    absolute = _existing_directory(run_dir, "run directory")
    db_path = os.path.join(absolute, DB_NAME)
    _reject_symlink_components(db_path)
    if not os.path.isfile(db_path):
        raise LedgerError(f"missing ledger database: {db_path}")
    try:
        connection = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection
    except sqlite3.Error as exc:
        raise LedgerError(f"cannot open ledger database: {exc}")


def _decode_state(connection: sqlite3.Connection) -> dict:
    try:
        row = connection.execute("SELECT revision, document FROM ledger WHERE id=1").fetchone()
    except sqlite3.Error as exc:
        raise LedgerError(f"unsupported or corrupt ledger database: {exc}")
    if row is None:
        raise LedgerError("unsupported or corrupt ledger database: missing state")
    try:
        state = json.loads(row["document"])
    except (TypeError, json.JSONDecodeError):
        raise LedgerError("unsupported or corrupt ledger database: invalid JSON")
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError("unsupported ledger schema")
    if state.get("revision") != row["revision"]:
        raise LedgerError("corrupt ledger database: revision mismatch")
    for key in ("run", "tasks", "actions", "events"):
        if key not in state:
            raise LedgerError(f"corrupt ledger database: missing {key}")
    return state


def _new_database(run_dir: str, state: dict) -> None:
    db_path = os.path.join(run_dir, DB_NAME)
    try:
        connection = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE ledger (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, document TEXT NOT NULL)")
        connection.execute("INSERT INTO ledger(id, revision, document) VALUES(1, ?, ?)", (state["revision"], json.dumps(state, separators=(",", ":"))))
        connection.commit()
    except sqlite3.Error as exc:
        raise LedgerError(f"cannot create ledger database: {exc}")
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass


def _mutate(run_dir: str, command: str, function) -> dict:
    connection = _connect(run_dir)
    try:
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = _decode_state(connection)
            result = function(state)
            state["revision"] += 1
            state["events"].append({"revision": state["revision"], "at": _now_iso(), "command": command})
            # Keep the audit log bounded while retaining recent evidence.
            state["events"] = state["events"][-500:]
            connection.execute("UPDATE ledger SET revision=?, document=? WHERE id=1", (state["revision"], json.dumps(state, separators=(",", ":"))))
            connection.commit()
            if isinstance(result, dict):
                result.setdefault("revision", state["revision"])
            return result
        except LedgerError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise LedgerError(f"ledger transaction failed: {exc}")
    finally:
        connection.close()


def _read(run_dir: str) -> dict:
    connection = _connect(run_dir)
    try:
        return _decode_state(connection)
    finally:
        connection.close()


def _validate_roots(state: dict) -> list[str]:
    roots = state["run"].get("write_roots")
    if not isinstance(roots, list) or not roots:
        raise LedgerError("corrupt ledger state: write roots")
    checked = []
    for root in roots:
        absolute = _ensure_safe_root(root)
        checked.append(absolute)
    return checked


def _check_active_and_deadline(state: dict) -> None:
    if state["run"].get("status") != "active":
        raise LedgerError(f"run is {state['run'].get('status')}, not active")
    if _deadline_expired(state):
        raise LedgerError("run deadline has passed")


def _task(state: dict, task_id: str) -> dict:
    task = state["tasks"].get(task_id)
    if task is None:
        raise LedgerError(f"unknown task: {task_id}")
    return task


def _check_task_lease(task: dict, token: str) -> None:
    lease = task.get("lease")
    if task.get("status") != "running" or not lease or not secrets.compare_digest(lease.get("token", ""), token):
        raise LedgerError("invalid or stale lease token")
    if _now() >= _parse_time(lease["expires_at"]):
        raise LedgerError("lease has expired; run recover first")


def _check_scope_paths(state: dict, scopes: list[str]) -> list[str]:
    roots = _validate_roots(state)
    checked = []
    for scope in scopes:
        checked.append(_ensure_inside_roots(scope, roots, "scope"))
    return checked


def _scopes_overlap(first: list[str], second: list[str]) -> bool:
    return any(_within(a, b) or _within(b, a) for a in first for b in second)


def _action(state: dict, action_id: str) -> dict:
    action = state["actions"].get(action_id)
    if action is None:
        raise LedgerError(f"unknown action: {action_id}")
    return action


def _evidence_integrity(state: dict) -> list[dict]:
    problems = []
    try:
        roots = _validate_roots(state)
    except LedgerError as exc:
        return [{"path": None, "problem": str(exc)}]
    for task in state["tasks"].values():
        for evidence in task.get("evidence", []):
            path = evidence.get("path")
            try:
                _ensure_inside_roots(path, roots, "evidence", must_exist=True)
                digest, size = _digest_file(path, "evidence")
                if digest != evidence.get("sha256") or size != evidence.get("bytes"):
                    raise LedgerError("hash or byte size changed")
            except LedgerError as exc:
                problems.append({"task_id": task["id"], "path": path, "problem": str(exc)})
    return problems


def _payload_integrity(state: dict, action: dict) -> None:
    roots = _validate_roots(state)
    path = _ensure_inside_roots(action["payload"], roots, "action payload", must_exist=True)
    digest, size = _digest_file(path, "action payload")
    if digest != action["payload_sha256"] or size != action["payload_bytes"]:
        raise LedgerError("action payload changed since it was recorded")


def _cmd_init(args: argparse.Namespace) -> dict:
    run_dir = _absolute(args.run)
    _reject_symlink_components(run_dir)
    if os.path.exists(run_dir):
        if os.path.islink(run_dir):
            raise LedgerError("run directory cannot be a symlink")
        if not os.path.isdir(run_dir):
            raise LedgerError("run path must be a directory")
        if os.listdir(run_dir):
            raise LedgerError("refusing to overwrite an existing run directory")
    else:
        try:
            os.makedirs(run_dir)
        except OSError as exc:
            raise LedgerError(f"cannot create run directory: {exc}")
    project = _existing_directory(args.project, "project")
    write_roots = [run_dir]
    for extra in args.write_root or []:
        root = _ensure_safe_root(extra)
        if not _within(root, project):
            raise LedgerError("stated write root must be within the selected project")
        write_roots.append(root)
    for index, first in enumerate(write_roots):
        for second in write_roots[index + 1 :]:
            if _within(first, second) or _within(second, first):
                raise LedgerError("write roots must not overlap")
    if os.path.exists(os.path.join(run_dir, DB_NAME)):
        raise LedgerError("run already has a ledger")
    created_at = _now_iso()
    state = {
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "run": {
            "run_dir": run_dir,
            "project": project,
            "objective": _nonempty(args.objective, "objective"),
            "allowed_models": list(dict.fromkeys(args.allowed_model or [DEFAULT_MODEL])),
            "write_roots": write_roots,
            "deadline": _parse_deadline(args.deadline),
            "max_workers": args.max_workers or 3,
            "max_attempts": args.max_attempts or 3,
            "status": "active",
            "created_at": created_at,
            "paused_reason": None,
        },
        "tasks": {},
        "actions": {},
        "events": [{"revision": 1, "at": created_at, "command": "init"}],
    }
    for model in state["run"]["allowed_models"]:
        _nonempty(model, "allowed model")
    _new_database(run_dir, state)
    return {"ok": True, "command": "init", "run": run_dir, "revision": 1, "schema_version": SCHEMA_VERSION}


def _cmd_add(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        if args.id in state["tasks"]:
            raise LedgerError(f"task ID already exists: {args.id}")
        if not args.id.strip():
            raise LedgerError("task ID must be nonempty")
        depends = _flatten(args.depends)
        if len(set(depends)) != len(depends):
            raise LedgerError("duplicate task dependency")
        for dependency in depends:
            if dependency == args.id or dependency not in state["tasks"]:
                raise LedgerError(f"dependency must already exist and differ from task: {dependency}")
        scopes = _check_scope_paths(state, _flatten(args.scope))
        state["tasks"][args.id] = {
            "id": args.id,
            "lane": args.lane,
            "question": _nonempty(args.question, "question"),
            "owner": _nonempty(args.owner, "owner"),
            "scope": scopes,
            "depends": depends,
            "acceptance": _nonempty(args.acceptance, "acceptance"),
            "status": "pending",
            "attempts": 0,
            "retryable": False,
            "failure": None,
            "lease": None,
            "evidence": [],
            "validation": None,
            "model_requested": None,
            "verified_runtime_model": None,
        }
        return {"ok": True, "command": "add", "task_id": args.id}

    return _mutate(args.run, "add", mutate)


def _cmd_claim(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        task = _task(state, args.id)
        if task["status"] == "failed" and not task.get("retryable"):
            raise LedgerError("task has a terminal failure")
        if task["status"] not in ("pending", "failed"):
            raise LedgerError(f"task is {task['status']}, not claimable")
        if task["attempts"] >= state["run"]["max_attempts"]:
            raise LedgerError("task retry cap exhausted")
        model = _nonempty(args.model, "model")
        if model not in state["run"]["allowed_models"]:
            raise LedgerError(f"model is not allowlisted: {model}")
        for dependency in task["depends"]:
            if state["tasks"][dependency]["status"] != "complete":
                raise LedgerError(f"dependency is not complete: {dependency}")
        scopes = _check_scope_paths(state, task["scope"])
        active_workers = sum(1 for item in state["tasks"].values() if item["status"] == "running")
        if active_workers >= state["run"]["max_workers"]:
            raise LedgerError("worker limit reached")
        for other in state["tasks"].values():
            if other["status"] == "running" and _scopes_overlap(scopes, other["scope"]):
                raise LedgerError(f"write scope overlaps active task: {other['id']}")
            if other["status"] == "running":
                # Recheck every active scope so a directory swapped for a
                # symlink after claim cannot silently remain in the active set.
                _check_scope_paths(state, other["scope"])
        now = _now()
        expires = now + dt.timedelta(minutes=args.lease_minutes or 60)
        if state["run"].get("deadline"):
            expires = min(expires, _parse_time(state["run"]["deadline"]))
        # Hex avoids an option-looking leading '-' when callers pass the
        # returned token as a separate command-line argument.
        token = secrets.token_hex(32)
        task["status"] = "running"
        task["attempts"] += 1
        task["retryable"] = False
        task["failure"] = None
        task["model_requested"] = model
        task["verified_runtime_model"] = None
        task["lease"] = {"worker": _nonempty(args.worker, "worker"), "model": model, "token": token, "claimed_at": now.isoformat(), "expires_at": expires.isoformat()}
        return {"ok": True, "command": "claim", "task_id": task["id"], "lease_token": token, "expires_at": expires.isoformat(), "model_requested": model}

    return _mutate(args.run, "claim", mutate)


def _cmd_finish(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        task = _task(state, args.id)
        _check_task_lease(task, args.token)
        # Scope authorization remains live until completion.  A directory
        # swapped for a symlink after claim must invalidate the lease result.
        _check_scope_paths(state, task["scope"])
        roots = _validate_roots(state)
        evidence = []
        for given in _flatten(args.evidence):
            path = _ensure_inside_roots(given, roots, "evidence", must_exist=True)
            digest, size = _digest_file(path, "evidence")
            evidence.append({"path": path, "sha256": digest, "bytes": size})
        task["status"] = "complete"
        task["lease"] = None
        task["evidence"] = evidence
        task["validation"] = _nonempty(args.validation, "validation")
        task["failure"] = None
        return {"ok": True, "command": "finish", "task_id": task["id"], "evidence": evidence}

    return _mutate(args.run, "finish", mutate)


def _cmd_fail(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        task = _task(state, args.id)
        _check_task_lease(task, args.token)
        retryable = bool(args.retryable) and task["attempts"] < state["run"]["max_attempts"]
        task["status"] = "failed"
        task["retryable"] = retryable
        task["failure"] = _nonempty(args.reason, "reason")
        task["lease"] = None
        return {"ok": True, "command": "fail", "task_id": task["id"], "retryable": retryable}

    return _mutate(args.run, "fail", mutate)


def _cmd_block(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        task = _task(state, args.id)
        if task["status"] == "running":
            if not args.token:
                raise LedgerError("running task requires its lease token")
            _check_task_lease(task, args.token)
        elif task["status"] not in ("pending", "failed"):
            raise LedgerError(f"task is {task['status']}, not blockable")
        task["status"] = "blocked"
        task["retryable"] = False
        task["failure"] = _nonempty(args.reason, "reason")
        task["lease"] = None
        return {"ok": True, "command": "block", "task_id": task["id"]}

    return _mutate(args.run, "block", mutate)


def _cmd_unblock(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        task = _task(state, args.id)
        if task["status"] != "blocked":
            raise LedgerError("only blocked tasks can be unblocked")
        task["status"] = "pending"
        task["failure"] = _nonempty(args.reason, "reason")
        return {"ok": True, "command": "unblock", "task_id": task["id"]}

    return _mutate(args.run, "unblock", mutate)


def _cmd_recover(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        recovered = []
        now = _now()
        for task in state["tasks"].values():
            lease = task.get("lease")
            if task["status"] != "running" or not lease:
                continue
            if now < _parse_time(lease["expires_at"]):
                continue
            terminal = task["attempts"] >= state["run"]["max_attempts"]
            task["status"] = "failed"
            task["retryable"] = not terminal
            task["failure"] = "lease expired; recovered without completion"
            task["lease"] = None
            recovered.append({"task_id": task["id"], "retryable": not terminal})
        return {"ok": True, "command": "recover", "recovered": recovered}

    return _mutate(args.run, "recover", mutate)


def _task_readiness(state: dict) -> list[dict]:
    ready = []
    for task in state["tasks"].values():
        if task["status"] not in ("pending", "failed"):
            continue
        if task["status"] == "failed" and (not task.get("retryable") or task["attempts"] >= state["run"]["max_attempts"]):
            continue
        missing = [dependency for dependency in task["depends"] if state["tasks"][dependency]["status"] != "complete"]
        ready.append({"task_id": task["id"], "ready": not missing, "waiting_on": missing})
    return ready


def _status_object(state: dict) -> dict:
    counts = {status: 0 for status in ("pending", "running", "complete", "failed", "blocked")}
    for task in state["tasks"].values():
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    integrity = _evidence_integrity(state)
    actions = [{"id": action["id"], "kind": action["kind"], "status": action["status"], "target": action["target"]} for action in state["actions"].values()]
    requests = [{"task_id": task["id"], "requested_model": task.get("model_requested"), "verified_runtime_model": task.get("verified_runtime_model")} for task in state["tasks"].values() if task.get("model_requested")]
    return {
        "schema_version": state["schema_version"],
        "revision": state["revision"],
        "status": state["run"]["status"],
        "run": state["run"],
        "tasks": {"counts": counts, "items": list(state["tasks"].values())},
        "remaining_task_readiness": _task_readiness(state),
        "runtime_model_requests": requests,
        "outstanding_actions": [action for action in actions if action["status"] in ("planned", "authorized", "attempted", "uncertain")],
        "evidence_integrity_problems": integrity,
        "export_integrity": _export_diagnostics(state),
    }


def _cmd_status(args: argparse.Namespace) -> dict:
    return _status_object(_read(args.run))


def _cmd_close(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        if state["run"]["status"] == "complete":
            raise LedgerError("run is already complete")
        reason = _nonempty(args.reason, "reason")
        if args.status == "complete":
            if any(task["status"] != "complete" for task in state["tasks"].values()):
                raise LedgerError("cannot complete run while tasks remain unfinished")
            problems = _evidence_integrity(state)
            if problems:
                raise LedgerError("cannot complete run with evidence integrity problems")
            pending = [action["id"] for action in state["actions"].values() if action["status"] in ("authorized", "attempted", "uncertain")]
            if pending:
                raise LedgerError(f"cannot complete run with outstanding action receipts: {', '.join(pending)}")
            state["run"]["status"] = "complete"
        else:
            state["run"]["status"] = "paused"
        state["run"]["paused_reason"] = reason
        return {"ok": True, "command": "close", "status": args.status, "reason": reason}

    return _mutate(args.run, "close", mutate)


def _cmd_resume(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        if state["run"]["status"] != "paused":
            raise LedgerError("only a paused run can be resumed")
        state["run"]["status"] = "active"
        state["run"]["paused_reason"] = _nonempty(args.reason, "reason")
        if _deadline_expired(state):
            raise LedgerError("run deadline has passed")
        return {"ok": True, "command": "resume", "status": "active"}

    return _mutate(args.run, "resume", mutate)


def _cmd_action_plan(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        _nonempty(args.id, "action ID")
        if args.id in state["actions"]:
            raise LedgerError(f"action ID already exists: {args.id}")
        path = _ensure_inside_roots(args.payload, _validate_roots(state), "action payload", must_exist=True)
        digest, size = _digest_file(path, "action payload")
        state["actions"][args.id] = {"id": args.id, "kind": args.kind, "target": _nonempty(args.target, "target"), "payload": path, "purpose": _nonempty(args.purpose, "purpose"), "payload_sha256": digest, "payload_bytes": size, "status": "planned", "authorization": None, "attempt_id": None, "result": None}
        return {"ok": True, "command": "action-plan", "action_id": args.id, "payload_sha256": digest, "payload_bytes": size}

    return _mutate(args.run, "action-plan", mutate)


def _cmd_action_authorize(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        action = _action(state, args.id)
        if action["status"] != "planned":
            raise LedgerError("only planned actions can be authorized")
        _payload_integrity(state, action)
        expires = _parse_deadline(args.expires, "authorization expiry") if args.expires else None
        if expires is not None and _now() >= _parse_time(expires):
            raise LedgerError("authorization expiry is in the past")
        action["status"] = "authorized"
        action["authorization"] = {"user_evidence": _nonempty(args.user_evidence, "user evidence"), "expires_at": expires, "recorded_at": _now_iso()}
        return {"ok": True, "command": "action-authorize", "action_id": action["id"], "expires_at": expires}

    return _mutate(args.run, "action-authorize", mutate)


def _cmd_action_attempt(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        _check_active_and_deadline(state)
        action = _action(state, args.id)
        if action["status"] != "authorized":
            raise LedgerError("only authorized actions can be attempted")
        authorization = action.get("authorization") or {}
        if authorization.get("expires_at") and _now() >= _parse_time(authorization["expires_at"]):
            raise LedgerError("authorization has expired")
        _payload_integrity(state, action)
        attempt_id = secrets.token_hex(24)
        action["status"] = "attempted"
        action["attempt_id"] = attempt_id
        return {"ok": True, "command": "action-attempt", "action_id": action["id"], "attempt_id": attempt_id, "idempotency_key": attempt_id}

    return _mutate(args.run, "action-attempt", mutate)


def _cmd_action_result(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        action = _action(state, args.id)
        if action["status"] != "attempted":
            raise LedgerError("only attempted actions can receive a result")
        outcome = args.outcome
        action["status"] = outcome
        action["result"] = {"outcome": outcome, "receipt": _nonempty(args.receipt, "receipt"), "recorded_at": _now_iso()}
        return {"ok": True, "command": "action-result", "action_id": action["id"], "outcome": outcome}

    return _mutate(args.run, "action-result", mutate)


def _cmd_action_reconcile(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        action = _action(state, args.id)
        if action["status"] != "uncertain":
            raise LedgerError("only uncertain actions can be reconciled")
        action["status"] = args.outcome
        action["result"] = {"outcome": args.outcome, "receipt": _nonempty(args.receipt, "receipt"), "reconciled_at": _now_iso()}
        return {"ok": True, "command": "action-reconcile", "action_id": action["id"], "outcome": args.outcome}

    return _mutate(args.run, "action-reconcile", mutate)


def _cmd_action_cancel(args: argparse.Namespace) -> dict:
    def mutate(state: dict) -> dict:
        action = _action(state, args.id)
        if action["status"] not in ("planned", "authorized"):
            raise LedgerError("only planned or authorized actions can be canceled")
        action["status"] = "cancelled"
        action["result"] = {"outcome": "cancelled", "reason": _nonempty(args.reason, "reason"), "recorded_at": _now_iso()}
        return {"ok": True, "command": "action-cancel", "action_id": action["id"]}

    return _mutate(args.run, "action-cancel", mutate)


def _escape_tsv(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


def _markdown_path(path: str) -> str:
    return f"[file](<{path}>)"


def _export_contents(state: dict) -> tuple[str, str, str]:
    status = _status_object(state)
    run = state["run"]
    lines = ["# Run state", "", f"- Status: `{run['status']}`", f"- Revision: `{state['revision']}`", f"- Objective: {run['objective']}", f"- Project: `{run['project']}`", f"- Deadline: `{run.get('deadline') or 'none'}`", f"- Allowed models (requested): {', '.join(run['allowed_models'])}", "- Verified runtime model: none recorded by this local ledger", "", "## Tasks", ""]
    for task in state["tasks"].values():
        lines.append(f"- `{task['id']}` ({task['lane']}): **{task['status']}**; owner `{task['owner']}`; attempts {task['attempts']}/{run['max_attempts']}")
        if task.get("evidence"):
            for evidence in task["evidence"]:
                lines.append(f"  - Evidence: {_markdown_path(evidence['path'])} ({evidence['bytes']} bytes, SHA-256 `{evidence['sha256']}`)")
    lines.extend(["", "## Evidence integrity", ""])
    problems = status["evidence_integrity_problems"]
    lines.append("- No recorded evidence integrity problems." if not problems else "- Problems:")
    for problem in problems:
        lines.append(f"  - {problem.get('task_id', '')}: `{problem.get('path')}` — {problem['problem']}")
    state_md = "\n".join(lines) + "\n"

    ledger_lines = [f"# revision: {state['revision']}", f"# export_revision\t{state['revision']}\t", "revision\ttask_id\tlane\tstatus\towner\tattempts\tmodel_requested\tverified_runtime_model\tevidence\tfailure"]
    for task in state["tasks"].values():
        evidence = ",".join(item["path"] for item in task.get("evidence", []))
        ledger_lines.append("\t".join(_escape_tsv(value) for value in (state["revision"], task["id"], task["lane"], task["status"], task["owner"], task["attempts"], task.get("model_requested"), task.get("verified_runtime_model"), evidence, task.get("failure"))))
    tsv = "\n".join(ledger_lines) + "\n"

    handoff = ["# Morning handoff", "", f"Run `{run['run_dir']}` is **{run['status']}** at revision `{state['revision']}`.", "", "## Completed deliverables", ""]
    completed = [task for task in state["tasks"].values() if task["status"] == "complete"]
    handoff.extend([f"- `{task['id']}`: {task['acceptance']}" for task in completed] or ["- None."])
    handoff.extend(["", "## Failed or blocked tasks", ""])
    stalled = [task for task in state["tasks"].values() if task["status"] in ("failed", "blocked")]
    handoff.extend([f"- `{task['id']}`: {task.get('failure') or 'no reason recorded'}" for task in stalled] or ["- None."])
    handoff.extend(["", "## Next ready work", ""])
    ready = [item for item in status["remaining_task_readiness"] if item["ready"]]
    handoff.extend([f"- `{item['task_id']}`" for item in ready] or ["- None."])
    handoff.extend(["", "## Pending user decisions", ""])
    pending = [action for action in state["actions"].values() if action["status"] in ("planned", "authorized", "attempted", "uncertain")]
    handoff.extend([f"- Action `{action['id']}` ({action['kind']}) for `{action['target']}` is `{action['status']}`; payload: `{action['payload']}`" for action in pending] or ["- None."])
    handoff.extend(["", "## Model and evidence notes", "", "- Stored model names are requests. This helper never verifies runtime model identity.", "- Evidence hashes identify recorded bytes; they do not establish scientific truth.", f"- Evidence integrity problems: {len(problems)}."])
    handoff_md = "\n".join(handoff) + "\n"
    return state_md, tsv, handoff_md


@contextlib.contextmanager
def _export_lock(run_dir: str):
    """Serialize export publishers on platforms with advisory file locks."""
    absolute = _existing_directory(run_dir, "run directory")
    lock_path = os.path.join(absolute, ".overnight-export.lock")
    _reject_symlink_components(lock_path)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise LedgerError(f"cannot open export lock: {exc}")
    locked = False
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            locked = True
        except (ImportError, OSError):
            # SQLite BEGIN IMMEDIATE below still serializes against mutations;
            # platforms without fcntl get the bounded fallback.
            pass
        yield absolute
    finally:
        if locked:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def _export_paths(run_dir: str) -> list[str]:
    return [
        os.path.join(run_dir, "RUN-STATE.md"),
        os.path.join(run_dir, "WORK-LEDGER.tsv"),
        os.path.join(run_dir, "MORNING-HANDOFF.md"),
    ]


def _stale_export_artifacts(run_dir: str) -> list[str]:
    try:
        names = os.listdir(run_dir)
    except OSError as exc:
        raise LedgerError(f"cannot inspect export directory: {exc}")
    return [
        os.path.join(run_dir, name)
        for name in names
        if name.startswith(".overnight-export-stage-") or name.startswith(".overnight-export-backup-")
    ]


def _stage_bytes(directory: str, content: bytes, prefix: str) -> str:
    try:
        fd, path = tempfile.mkstemp(prefix=prefix, dir=directory)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return path
    except OSError as exc:
        try:
            os.unlink(path)
        except (OSError, UnboundLocalError):
            pass
        raise LedgerError(f"cannot stage export: {exc}")


def _fsync_directory(directory: str) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # Some filesystems do not permit directory fsync.  SQLite remains the
        # authority and revision diagnostics detect a hard-crash split.
        pass


def _preflight_export_target(path: str) -> None:
    _reject_symlink_components(path)
    if not os.path.lexists(path):
        return
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise LedgerError(f"cannot inspect export target {path}: {exc}")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise LedgerError(f"export target is not a regular file: {path}")


def _remove_artifact(path: str) -> None:
    try:
        info = os.lstat(path)
        if stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _publish_exports(paths: list[str], contents: tuple[str, str, str]) -> int:
    """Stage every output and publish with rollback for ordinary failures."""
    for path in paths:
        _preflight_export_target(path)
    run_dir = os.path.dirname(paths[0])
    stale = _stale_export_artifacts(run_dir)
    staged: list[str] = []
    backups: list[tuple[str, str | None]] = []
    published: list[tuple[str, str | None]] = []
    try:
        for content in contents:
            staged.append(_stage_bytes(run_dir, content.encode("utf-8"), ".overnight-export-stage-"))
        for path in paths:
            if os.path.lexists(path):
                old_content, _ = _load_file_bytes(path, "previous export")
                backups.append((path, _stage_bytes(run_dir, old_content, ".overnight-export-backup-")))
            else:
                backups.append((path, None))
        _fsync_directory(run_dir)
        for stage, (path, backup) in zip(staged, backups):
            os.replace(stage, path)
            published.append((path, backup))
        _fsync_directory(run_dir)
    except (OSError, LedgerError) as exc:
        rollback_error = None
        for path, backup in reversed(published):
            try:
                if backup is not None:
                    os.replace(backup, path)
                else:
                    _remove_artifact(path)
            except OSError as rollback_exc:
                rollback_error = rollback_exc
        _fsync_directory(run_dir)
        if rollback_error is not None:
            raise LedgerError(f"export publication failed and rollback was incomplete; authoritative SQLite is unchanged; run export again: {rollback_error}")
        raise LedgerError(f"export publication failed; authoritative SQLite is unchanged; run export again: {exc}")
    finally:
        for path in staged:
            _remove_artifact(path)
        for _, backup in backups:
            if backup is not None:
                _remove_artifact(backup)
    for path in stale:
        _remove_artifact(path)
    _fsync_directory(run_dir)
    return len(stale)


def _extract_export_revision(name: str, text: str) -> int | None:
    if name == "RUN-STATE.md":
        pattern = r"^- Revision: `(\d+)`$"
    elif name == "WORK-LEDGER.tsv":
        pattern = r"^# revision: (\d+)$"
    else:
        pattern = r"revision `(\d+)`"
    match = re.search(pattern, text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _export_diagnostics(state: dict) -> dict:
    run_dir = state["run"]["run_dir"]
    paths = _export_paths(run_dir)
    problems: list[str] = []
    revisions: dict[str, int | None] = {}
    present = 0
    for path in paths:
        name = os.path.basename(path)
        if not os.path.lexists(path):
            revisions[name] = None
            continue
        present += 1
        try:
            _preflight_export_target(path)
            content, _ = _load_file_bytes(path, "export summary")
            revisions[name] = _extract_export_revision(name, content.decode("utf-8"))
            if revisions[name] is None:
                problems.append(f"{name} has no readable revision")
        except (LedgerError, UnicodeDecodeError) as exc:
            revisions[name] = None
            problems.append(f"{name}: {exc}")
    if present and present != len(paths):
        problems.append("export summaries are incomplete")
    known = [revision for revision in revisions.values() if revision is not None]
    if known and any(revision != state["revision"] for revision in known):
        problems.append(f"export revision differs from authoritative SQLite revision {state['revision']}")
    if len(set(known)) > 1:
        problems.append("export summaries have mixed revisions")
    stale = _stale_export_artifacts(run_dir)
    if stale:
        problems.append("stale export staging artifacts indicate an interrupted publication")
    return {
        "authoritative_revision": state["revision"],
        "exported_revisions": revisions,
        "recovery_required": bool(problems),
        "problems": problems,
    }


def _cmd_export(args: argparse.Namespace) -> dict:
    with _export_lock(args.run) as run_dir:
        connection = _connect(run_dir)
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
                state = _decode_state(connection)
                state_md, tsv, handoff_md = _export_contents(state)
                paths = _export_paths(run_dir)
                recovered = _publish_exports(paths, (state_md, tsv, handoff_md))
                connection.commit()
            except LedgerError:
                connection.rollback()
                raise
            except sqlite3.Error as exc:
                connection.rollback()
                raise LedgerError(f"export transaction failed: {exc}")
        finally:
            connection.close()
    diagnostics = _export_diagnostics(state)
    return {"ok": True, "command": "export", "revision": state["revision"], "files": paths, "recovered_stale_artifacts": recovered, "recovery_required": diagnostics["recovery_required"]}


def _add_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="overnight.py", description="Durable local ledger; records work and receipts without performing external actions.")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("init", help="create a new run")
    command.add_argument("--run", required=True)
    command.add_argument("--project", required=True)
    command.add_argument("--objective", required=True)
    command.add_argument("--allowed-model", action="append")
    command.add_argument("--write-root", action="append")
    command.add_argument("--deadline")
    command.add_argument("--max-workers", type=_positive)
    command.add_argument("--max-attempts", type=_positive)
    command.set_defaults(handler=_cmd_init)

    command = sub.add_parser("add", help="add a pending task")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--lane", choices=LANES, required=True); command.add_argument("--question", required=True); command.add_argument("--owner", required=True); command.add_argument("--scope", action="append", nargs="+"); command.add_argument("--depends", action="append", nargs="+"); command.add_argument("--acceptance", required=True); command.set_defaults(handler=_cmd_add)
    command = sub.add_parser("claim", help="claim a ready task")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--worker", required=True); command.add_argument("--model", required=True); command.add_argument("--lease-minutes", type=_positive); command.set_defaults(handler=_cmd_claim)
    command = sub.add_parser("finish", help="finish a leased task")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--token", required=True); command.add_argument("--evidence", action="append", nargs="+", required=True); command.add_argument("--validation", required=True); command.set_defaults(handler=_cmd_finish)
    command = sub.add_parser("fail", help="record a failed leased task")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--token", required=True); command.add_argument("--reason", required=True); command.add_argument("--retryable", action="store_true"); command.set_defaults(handler=_cmd_fail)
    command = sub.add_parser("block", help="record a blocked task")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--reason", required=True); command.add_argument("--token"); command.set_defaults(handler=_cmd_block)
    command = sub.add_parser("unblock", help="return a blocked task to pending")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--reason", required=True); command.set_defaults(handler=_cmd_unblock)
    command = sub.add_parser("recover", help="recover expired leases")
    _add_run(command); command.set_defaults(handler=_cmd_recover)
    command = sub.add_parser("status", help="show current state")
    _add_run(command); command.set_defaults(handler=_cmd_status)
    command = sub.add_parser("close", help="complete or pause a run")
    _add_run(command); command.add_argument("--status", choices=("complete", "paused"), required=True); command.add_argument("--reason", required=True); command.set_defaults(handler=_cmd_close)
    command = sub.add_parser("resume", help="resume a paused run")
    _add_run(command); command.add_argument("--reason", required=True); command.set_defaults(handler=_cmd_resume)
    command = sub.add_parser("export", help="write human-readable exports")
    _add_run(command); command.set_defaults(handler=_cmd_export)

    command = sub.add_parser("action-plan", help="record a reviewable external action")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--kind", choices=("contact", "publish", "purchase"), required=True); command.add_argument("--target", required=True); command.add_argument("--payload", required=True); command.add_argument("--purpose", required=True); command.set_defaults(handler=_cmd_action_plan)
    command = sub.add_parser("action-authorize", help="record exact user authorization")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--user-evidence", required=True); command.add_argument("--expires"); command.set_defaults(handler=_cmd_action_authorize)
    command = sub.add_parser("action-attempt", help="consume authorization once")
    _add_run(command); command.add_argument("--id", required=True); command.set_defaults(handler=_cmd_action_attempt)
    command = sub.add_parser("action-result", help="record provider observation")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--outcome", choices=("confirmed", "failed", "uncertain"), required=True); command.add_argument("--receipt", required=True); command.set_defaults(handler=_cmd_action_result)
    command = sub.add_parser("action-reconcile", help="reconcile an uncertain action")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--outcome", choices=("confirmed", "failed"), required=True); command.add_argument("--receipt", required=True); command.set_defaults(handler=_cmd_action_reconcile)
    command = sub.add_parser("action-cancel", help="cancel an unattempted action")
    _add_run(command); command.add_argument("--id", required=True); command.add_argument("--reason", required=True); command.set_defaults(handler=_cmd_action_cancel)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        result = args.handler(args)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
