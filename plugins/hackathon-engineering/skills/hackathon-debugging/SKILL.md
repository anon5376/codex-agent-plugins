---
name: hackathon-debugging
description: Use when a test fails, an integration times out, an output is wrong, or a bug reappears after a speculative fix.
---

# Diagnose before patching

Reproduce the reported symptom with the smallest real input. Capture the expected result, actual result, failing command and error. Establish whether failure is in input validation, model access, interpretation, state, transport or rendering before editing.

Trace one failing input across the relevant boundary. Read the first causal error; later errors may be consequences. Compare with a nearby working case and inspect the recent diff. Form one falsifiable hypothesis, then run one discriminating check. Change one cause at a time.

For logic bugs, add a regression case that fails for the original symptom. Apply the smallest correction and run the failing case, then the affected checks. For configuration or environment faults, verify the real command/configuration rather than inventing a unit test of a string.

After two failed hypotheses or ten minutes without a reliable fix, report evidence and select a narrower fallback. Preserve logs and partial work; never suppress an exception, relax assertions, remove validation or hard-code success to obtain a green demo.

End with the cause, actual fix, fresh evidence and remaining uncertainty. Distinguish a reproduced fix from a workaround and from an untested assumption.
