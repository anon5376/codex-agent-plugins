# Ledger commands

Run the helper with Python 3. It uses only the standard library. Resolve `scripts/overnight.py` relative to the skill folder; do not assume the source or installed-cache location is fixed. Every command accepts `--run` and prints JSON; errors return a nonzero exit code. Use subcommand `--help` for complete options.

## A small run

These examples describe project work, not a Python lesson. Substitute actual authorized absolute paths. Do not initialize over an existing run.

```sh
python3 scripts/overnight.py init --run /project/output/night-01 --project /project --objective 'Finish the requested brief' --allowed-model gpt-5.6-luna
python3 scripts/overnight.py add --run /project/output/night-01 --id brief --lane research --question 'Reconcile the two source records' --owner writer --scope /project/output/night-01/brief.md --acceptance 'Every conclusion cites the inspected source and retains uncertainty'
python3 scripts/overnight.py claim --run /project/output/night-01 --id brief --worker writer --model gpt-5.6-luna
```

Save the returned lease token. Do the work, verify the artifact, then finish using that exact token:

```sh
python3 scripts/overnight.py finish --run /project/output/night-01 --id brief --token TOKEN_FROM_CLAIM --evidence /project/output/night-01/brief.md --validation 'Inspected both source records; checked each citation and retained the unresolved conflict'
python3 scripts/overnight.py status --run /project/output/night-01
python3 scripts/overnight.py close --run /project/output/night-01 --status complete --reason 'Requested brief and checks are complete'
python3 scripts/overnight.py export --run /project/output/night-01
```

The text supplied to `--validation` records a check the agent actually ran. It does not run that check or certify the content. Evidence hashes are rechecked before complete; stale files invalidate the recorded identity.

## Scope and dependencies

The default write root is the run directory. Add explicit `--write-root` values at initialization only for authorized paths within the selected project. Existing scopes must not contain symlinks; later symlink substitutions must also be rejected. Give each task its actual files or narrow directory. A read-only task omits scope. Every task still needs a report artifact under the allowed roots to finish.

Use `--depends` for existing task IDs. A dependent task cannot start before its prerequisites finish. Simultaneous writers cannot claim overlapping paths, including a directory and its child. Sequential reuse does not transfer scientific or release authority. Respect any project owner that exists outside this ledger too.

The default allowed model is gpt-5.6-luna, with at most three simultaneous claims and three attempts per task. Explicit user/model choices can be recorded at initialization; do not silently expand them to fix a blocked claim. The requested model string is not independent runtime verification.

## Interruption and failures

- `fail --id ... --token ... --reason ... --retryable` preserves a failed attempt and permits another claim within the cap. Omitting retryable makes the failure terminal for that task.
- `block --id ... --reason ...` records missing input or permission. Supply the token for running work. `unblock --id ... --reason ...` records the changed condition without resetting attempts.
- `recover` releases expired leases. Confirm the old worker cannot still write before redispatch. An expired token cannot finish another worker's attempt.
- `close --status paused --reason ...` saves unfinished work. `resume --reason ...` reactivates a paused run without resetting deadlines or attempts. It never reopens a completed run.

Deadlines must include a timezone. An expired deadline prevents new claims; it is not evidence that the work finished. Use a new explicitly scoped continuation if the user extends the window, preserving the old run.

## External actions

Use action-plan, action-authorize, action-attempt, action-result, action-reconcile and action-cancel as described in [external-actions.md](external-actions.md). Payloads are ordinary reviewable files; no command is executed by the helper. An uncertain result cannot be retried as if nothing happened.

Planned future proposals remain visible in the handoff. An authorized action still awaiting execution, an attempted action without a result, or an uncertain result prevents completion. A contact-drafting task should not manufacture authorization simply to close the run.

The authoritative DB is `run.sqlite3`. Never edit it to promote a task or erase a failure. Export stages all outputs before publication and rolls back ordinary publication failures. A hard process or power loss can still interrupt the replacement sequence; `status` reports exported revisions and `export_integrity.recovery_required`. Regenerate the Markdown/TSV files with `export` when they disagree with the authoritative revision. Do not place secret values or unnecessary personal details in question, reason, receipt or validation strings.
