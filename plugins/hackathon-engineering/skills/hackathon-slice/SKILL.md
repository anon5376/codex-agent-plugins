---
name: hackathon-slice
description: Use when starting a time-limited software feature, choosing MVP scope, or recovering a hackathon build that is behind schedule.
---

# Ship one vertical slice

Read the existing brief and repository first. Write a three-line implementation note: user action, visible result, acceptance check. Reuse an approved brief; resolve routine reversible choices and continue. Ask only when missing information changes the intended outcome or external authority.

Build the shortest path from one real input through real processing to a usable result. Connect UI and engine early. Use labeled fixtures while a dependency is unavailable; replace or retain them as explicitly recorded/demo modes. Choose an existing library over building infrastructure that does not demonstrate the product.

Target an end-to-end flow by minute 60, a narrow complete version by 90 and a deployed/testable version by 150. Check progress against working behavior, not files written. Freeze features at minute 195.

Cut optional accounts, databases, abstractions, animation and integrations when the core flow is unfinished. Keep one fallback that reuses the working core. Preserve the ability to reset, inspect failures and export a real result when the brief requires it.

Hand off the working path, check evidence, known limits and the next concrete blocking issue. Never substitute a polished screenshot for functioning behavior.
