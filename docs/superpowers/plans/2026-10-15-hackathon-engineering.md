# Hackathon Engineering Implementation Plan

> Execute natively in the isolated feature branch; use a fresh review after implementation.

**Goal:** Prepare a tested, reusable Codex development kit before the event.
**Architecture:** Deterministic Python scheduler, official CLI workers, per-task Git worktrees, independent verification and a separate integration branch.
**Tech Stack:** Python 3.11 standard library; Codex CLI at runtime.
**Spec:** docs/superpowers/specs/2026-10-15-hackathon-engineering.md

## Global constraints
No contest implementation; no live inference during kit preparation; no API-key fallback; two simultaneous workers maximum; no main-branch changes.

## Review focus
Interrupted usage accounting; concurrent state writers; task dependency snapshots; untracked files outside scope; failed checks during patch integration.

## Task 1: Validated bounded runner
- [x] Write tests for invalid DAG/path/limits, actual fake-process dispatch, missing usage, timeout, retry exhaustion, scope rejection, integration rollback and resume.
- [x] Run tests red; implement scripts/hackathon.py and runner.py against these behaviors.
- [x] Run all runner tests green, with no real model calls.

## Task 2: Skills and installation
- [x] Initialize six instruction-only skills; keep each under 300 words and use explicit triggers.
- [x] Add plugin manifests, marketplace entry, event-day README, machine-readable RECON plan and source references.
- [x] Validate skills, JSON, example plan and a dry run. Forward-test operational skills on a realistic pressured scenario.

## Task 3: Whole-kit verification and persistence
- [x] Run existing repository suites plus new tests and CLI smoke checks.
- [x] Review the full patch independently; reproduce and fix material findings.
- [x] Commit and push the isolated feature branch; provide a reviewable pull request and clear setup commands.

## Validation record

- New package: 37 offline tests pass, including real fake-worker subprocesses, DAG dependencies, scope rejection, timeout/global-stop handling, independent watchdog deadline, metering, interrupt retry, integration rollback and transaction recovery.
- Existing suites: 9 Autonomous Operator tests and 17 Overnight Work tests pass; dashboard check has no failures.
- Six skill folders pass the skill validator. JSON manifests and example plan validate. The four-skill pressure scenario respects ownership, stale-state handling, evidence requirements and refuses a 50000-token dispatch reservation when only 20000 observed tokens remain. This is a scenario check, not evidence of improved competition performance.
- Installed official Codex CLI 0.162.1: help/feature flags, plugin marketplace ref syntax and zero-inference doctor verified. No live model inference or competition entry code was executed.
- Independent review identified timeout/interrupt/process-lifetime risks. Added a standalone lifetime supervisor, global stop propagation, metered interruption retry and crash-consistent integration journaling. Offline process tests run in a managed host; they are not an adversarial OS containment proof.
