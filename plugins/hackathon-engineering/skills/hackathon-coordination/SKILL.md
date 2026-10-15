---
name: hackathon-coordination
description: Use when coordinating parallel coding tasks, retrying failed workers, or spending a limited hackathon model budget.
---

# Coordinate bounded work

Make a small task DAG with one owner per file, explicit dependencies, a completion check and a stop condition. Use at most two coding workers at once. Keep contracts, dependency manifests and lockfiles under a single owner. Serialize overlapping paths; independent tasks may run in separate worktrees.

Use a deterministic dispatcher for routing. Give each worker the goal, owned paths, relevant contract and only the skills it needs. Reference files instead of copying whole histories. Require a result containing changed files, actual checks and remaining failures. Read the diff before accepting a claim.

Keep Codex credits and API credits separately accounted. Treat observed tokens as delayed telemetry, never an exact remaining-dollar balance. Preserve reservations and attempts across interruption. Stop new work on unknown usage; do not compensate by changing model, provider or speed. Retry only after diagnosing the first failure, at most once.

At 150 minutes prioritize deployment readiness and failures. At 195 minutes freeze features and rehearse. If a slice cannot be integrated within ten minutes, reduce it to a working fallback with explicit limitations. Keep irreversible or external actions within the user's authorization.
