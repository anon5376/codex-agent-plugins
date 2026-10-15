---
name: hackathon-frontend
description: Use when building or polishing a web demo interface, connecting asynchronous model output, or preparing a short judged presentation.
---

# Make the demo usable

Give the main user action and its result the strongest visual hierarchy. Use one coherent type/spacing/color system and actual product language. Make supporting receipts secondary. Reuse existing components; do not spend the build window inventing a design system.

Implement explicit idle, loading, empty, success, mismatch, timeout and error states as applicable. Show actual progress events only. Disable duplicate submissions, allow reset/retry and ensure an old success does not remain valid after input or configuration changes. Label fixtures and recorded output where they appear.

Use ordinary controls with visible labels, keyboard focus and sensible tab order. Convey status with text or symbols as well as color. Check the primary flow at phone and desktop widths. Keep numbers, units and selected-case details legible. Respect reduced-motion preferences.

Polish after the real flow works: alignment, spacing, readable copy, stable panels and restrained transitions. Every visible control must work or explain its unavailable state. Avoid decorative chat layouts, fake reasoning streams and pointless 3D.

Rehearse a 60-90-second path with an unseen input. Show the transformation, an inspectable result and one meaningful failure. If inference stalls, use a clearly labeled recorded session and demonstrate the checks live.
