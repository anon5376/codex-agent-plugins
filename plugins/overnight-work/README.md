# Overnight Work

Overnight Work is a resumable operating workflow for substantial project work while you are away. It pairs a Codex skill with a durable SQLite task ledger, explicit ownership and dependencies, bounded attempts, evidence identities, recovery of expired leases, and a concise morning handoff.

## Install

```sh
codex plugin marketplace add anon5376/codex-agent-plugins
codex plugin add overnight-work@codex-agent-plugins
```

Restart the ChatGPT desktop app, then start a new task with explicit outcomes and boundaries:

> Use $overnight-work to finish this project's website and research brief while I sleep. Keep the full study private, prepare contact drafts, and stop when the deliverables and checks are complete.

To resume a run:

> Use $overnight-work to resume the run at /absolute/path/to/run. Inspect its state first and finish only the remaining work.

## What it provides

- A durable task queue with ownership, dependencies, leases, bounded attempts, and crash recovery.
- Evidence identities and completion checks, plus readable `RUN-STATE.md` and `WORK-LEDGER.tsv` exports.
- Separate lanes for evidence synthesis, speculative proposals, website work, visual work, and contact preparation.
- Reviewable external-action payloads with exact authority and single-attempt receipts.
- Continuation guidance and a morning handoff covering artifacts, failures, and decisions.

The ledger never invokes a model, sends a message, deploys a site, or purchases credits. Codex performs the actual work with the tools and authority available in the task. A recorded approval is bookkeeping, not identity proof; a checksum identifies bytes, not truth.

## Requirements

- Python 3.9 or newer
- No third-party Python dependencies
- The host must remain awake and have enough runtime usage to continue

## Verify

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```
