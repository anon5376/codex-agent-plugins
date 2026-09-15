# Continuation and morning handoff

## Scheduling

Use native Codex automations when the user asks to continue later, monitor or work overnight and a later wakeup is useful. Inspect matching automation records first. Prefer the current task's heartbeat over creating a new task or standalone cron job. Use the tool's schema; do not hand-write automation directives or modify scheduling files.

Check the tool result before claiming a wakeup was scheduled. On versions requiring a destination when no target ID is supplied, use the documented thread destination rather than inventing an ID. A rejected create call is not an existing automation; a successfully created one must not be duplicated on retry.

A continuation prompt should name the project, exact run directory, objective, entry file, model constraints, owned paths, remaining acceptance checks and stop condition. It should require current state inspection before dispatch. Make it stop or pause after completion; do not generate perpetual research from a bounded build request.

The scheduler controls wakeups. This plugin does not keep the host awake, overcome an offline host, replenish quota, or guarantee an unattended browser session. If continuation cannot be created, save the checkpoint and report that scheduling failed. Do not disguise a shell loop as a native heartbeat.

Keep notification preferences in native automation settings. In the continuation instructions, focus on actionable work and meaningful outcomes; do not manufacture periodic reports when nothing has changed.

## Resume

1. Read the authoritative run status and the latest handoff. Check deadline, stop instructions, model availability and changed project files.
2. Inspect any previously running worker or provider attempt. A stale lease permits bookkeeping recovery, not a second simultaneous writer. Confirm the old worker stopped or cannot still mutate the owned paths before redispatch.
3. Reconcile ambiguous external actions using read-only provider evidence. Never resend as a recovery strategy.
4. Recover expired leases without resetting attempt counts. Recheck dependencies and evidence hashes; finished work remains finished unless new evidence invalidates it.
5. Continue the next ready authorized task. If quota or runtime is unavailable, preserve the exact blocker and use the available scheduled continuation only within the user's requested window. Do not change the requested model silently.

## Closeout

Wait for or explicitly stop every started worker before claiming the assigned program finished. Reconcile each output into a final artifact or a named rejection/blocker. Run only checks justified by changed behavior or outstanding concerns. Validate all output links and evidence identities.

Keep MORNING-HANDOFF.md short and usable. Lead with the result. Link the final deliverables and explain what changed, what was verified, what remains uncertain and the next concrete action. Put exact commands and hashes in a linked evidence appendix if they make the summary hard to read.

Completion means all requested authorized work and required validation are done. Deadline, quota exhaustion, paused approval and missing runtime are different outcomes. The CLI's close check prevents obvious inconsistent state; a human-readable PASS written by an agent is not independent evidence.
