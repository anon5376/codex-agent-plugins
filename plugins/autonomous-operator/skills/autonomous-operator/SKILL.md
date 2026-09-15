---
name: autonomous-operator
description: "Prepare or execute a scoped autonomous mission using Astra XHigh coordination, Sol High management, Luna Max workers and optional GPT-6 Pro ordinary Web chats. Use for the Operator mission form or an ongoing multidisciplinary work mission."
---

# Autonomous Operator

Use the user's mission as the controlling scope. This plugin supplies a local submission form and operating instructions; it does not guarantee worker capacity, uninterrupted uptime, scientific correctness or external access. A saved prompt is not a started or completed mission.

## Open the local form

The server is `scripts/server.py` at the plugin root, two directories above this skill folder. Read the plugin README for the command. Use an existing matching server when it responds correctly; otherwise start it on loopback with persistent data outside the installed cache. Show the returned URL. The user chose save/copy only: this server has no task-launch capability. Opening, editing, previewing and saving do not start a mission or authorize an automation. The operating instructions below apply when the user separately submits a mission for execution.

## Establish the mission

Read its objective, project, outcomes, constraints, context references, requested models, operating limit and external-action scope. Inspect project instructions and the smallest decisive existing artifacts. Preserve unrelated tracked, untracked, ignored and concurrently owned work. Project acceptance and publication authorities continue to apply; a form cannot promote evidence status or invent authority.

Keep a compact mission record in an authorized output location: objective, current plan, owned paths, open questions, decisions, task owners and artifacts. Coordinate in the current task. Create a formal goal only when the user explicitly asks. Summarize useful progress without flooding the user with worker chatter.

## Exact hierarchy

- Lead: `gpt-6-astra` at `xhigh`, normally one. Additional Astra specialists receive separate hard questions; one lead owns the integrated plan.
- Manager: `gpt-5.6-sol` at `high`. Sol defines executable briefs, dispatches work, reviews evidence and integrates results.
- Workers: `gpt-5.6-luna` at `max`. Size the pool by independent ready work, requested ceiling, actual capacity and budget. A requested ceiling is not evidence of a running pool.

Read [worker contracts](references/worker-contracts.md) when dispatching. Set both model and effort explicitly, verify available runtime metadata, and mark unavailable verification honestly. Do not substitute models or change global concurrency settings silently. If nested delegation is unavailable, a supported root-broker arrangement may preserve Sol's logical ownership while respecting actual execution limits. Do not launch extra processes to evade runtime or account limits.

Review runs in reverse: Luna → Sol → Astra. Luna produces the artifact and executes its checks; Sol reviews the artifact and evidence, requests concrete corrections and integrates worker results; Astra reviews the integrated outcome against the mission and resolves consequential uncertainty. Rejected work returns to the responsible lower layer and then passes through the affected review layers again. Reuse unchanged valid checks. These reviews do not replace the project's recorded acceptance or publication authority.

## Make useful progress

Investigate, plan, assign, produce, check, integrate, then reprioritize. Sol handles routine implementation and narrow retries; Astra handles strategy changes. An artifact is a checkpoint. Choose the next useful task within the mission while permitted work remains. Do not invent busywork or declare completion while started work is unaccounted for.

Separate evidence, assumptions, proposed mechanisms, simulation output and measured results. Before quantitative implementation, define equations, units, boundaries, parameters and uncertainty; use analytic checks and sensitivity where relevant. For code, make the smallest sufficient change and execute checks of the changed behavior. Inspect actual visual renders. Review effort follows consequence and uncertainty.

Send coordinators concise evidence summaries and retrieve supporting detail on demand. Reuse inspected sources, avoid duplicate assignments and searches, and wait on progress events rather than repeated status turns. Retry with a changed approach or evidence of a transient failure, within an explicit allowance. A silent worker or provider is not automatically failed.

## Optional capabilities

When Pro is enabled, read [Pro Web](references/pro-web.md). Sol may use it within the submitted allowance and scope while others pursue independent work. It is ordinary ChatGPT Web, not a Codex worker.

For contact, email setup, calendar or meeting work, publication and other external changes, read [action authority](references/action-authority.md). Existing scope and actual connector requirements govern execution.

## Interruption and limits

Checkpoint artifacts and meaningful failures. Before replacing an interrupted worker, confirm it cannot still write to its paths. Preserve failed attempts, evidence and unfinished tasks. Reconcile uncertain external outcomes before retrying.

Time/token fields are requested operating limits, not independently enforced spending guarantees. Measure usage when available; otherwise disclose the limitation. User stop instructions prevent new dispatch. Deadline, quota exhaustion, missing access and completed work are distinct states.

Use native scheduling only when the user requested ongoing/later execution and continuation is needed. Update a matching heartbeat rather than duplicating it. Do not hand-write scheduler files or promise work on an unavailable host. At a pause or milestone, lead with usable results, executed checks, unresolved decisions and the next action. A CLI exit is not accepted research or successful development.
