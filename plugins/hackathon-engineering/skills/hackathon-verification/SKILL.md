---
name: hackathon-verification
description: Use when preparing to declare work complete, integrate a worker patch, deploy a demo, or present generated output as correct.
---

# Verify what will ship

Name the claim first, then run the check that could disprove it. Read the exit code and relevant output. A worker's summary, an old green run or a mocked success response is not evidence for the current revision.

Verify behavior at the changed boundary: valid input, important edge case and the main failure path. Run existing required checks for the affected code, including build/type checks when integration depends on them. Avoid low-value tests of cosmetic edits or tests that duplicate implementation details.

Recheck after integration. Two individually passing branches can fail together. Check the exported artifact with the same runtime and vectors when export is part of the product. For a web flow, exercise the production/local build from input to visible result, including timeout, reset and stale results.

Record the revision, exact commands, results and any checks not run. Mark completion only when acceptance criteria have evidence. Report unrelated baseline failures accurately without claiming they were caused or fixed by this change.

If live inference was not tested, say so. Label recorded inference while running verification live. State the checked input domain; agreement on a finite fixture is not universal correctness. Never change tests or fixtures solely to conceal a failure.
