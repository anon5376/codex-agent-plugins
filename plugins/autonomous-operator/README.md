# Autonomous Operator

Autonomous Operator turns a rough objective into a bounded mission prompt for an Astra XHigh → Sol High → Luna Max execution route, with Luna → Sol → Astra review. It makes outcomes, limits, worker ceilings, external-action authority, and optional GPT-6 Pro Web use explicit before work begins.

## Install

```sh
codex plugin marketplace add anon5376/codex-agent-plugins
codex plugin add autonomous-operator@codex-agent-plugins
```

Restart the ChatGPT desktop app, then ask:

> Use $autonomous-operator to prepare a mission for this project.

## Open the local form

From this plugin directory:

```sh
python3 scripts/server.py
```

Open the printed loopback URL. The default port is 8768. Saved missions live outside the installed plugin cache in `~/.local/share/autonomous-operator`; use `--port` or `--data-dir` to override either setting.

The form is deliberately save/copy only. It has no task-launch endpoint and does not start Codex, create an automation, contact anyone, or grant permission to perform external actions. Execution begins only when the resulting prompt is separately submitted.

## Requirements

- Python 3.9 or newer
- No Python or frontend dependencies
- A current Codex installation for the packaged skill

## Verify

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

An optional end-to-end browser smoke test is in `tests/browser_smoke.mjs`. It requires an existing Playwright installation; no browser dependency is bundled.

## Scope

The local form prepares and stores mission prompts. It does not establish an always-on host, a larger worker pool, a browser session, or connected accounts. The executing task must verify those capabilities when they matter.
