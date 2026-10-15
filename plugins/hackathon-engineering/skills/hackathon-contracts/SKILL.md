---
name: hackathon-contracts
description: Use when multiple workers share data types, integrating an API or model response, or implementing executable business rules.
---

# Build against clear contracts

Inspect callers and consumers before changing a shared interface. Assign one owner to shared types, package manifests and lockfiles. Define required fields, units, allowed ranges, error variants and a minimal representative fixture. Consumers should start against that same fixture.

Validate at the input boundary and again before execution. A schema-valid model response can still be wrong. Reject unknown or invalid actions with a specific error. Keep secrets server-side. Do not execute generated shell or arbitrary JavaScript as a shortcut to interpreting a bounded program.

Implement the smallest behavior required by the current task. Add a meaningful test for a boundary, invariant or previously failing case before the implementation when risk warrants it. Avoid tests that merely restate internal code.

Separate the reference implementation from the learned interpreter. Compute comparisons from actual outputs. Export the same implementation exercised by the application; do not generate an untested second version. Invalidate prior results when configuration, input or implementation changes.

Record incompatible interface changes in one short note and update all callers before integration. Stop concurrent edits to the contract rather than hoping Git will resolve semantic disagreements.
