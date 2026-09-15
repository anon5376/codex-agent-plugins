# Codex Agent Plugins

[![CI](https://github.com/anon5376/codex-agent-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/anon5376/codex-agent-plugins/actions/workflows/ci.yml)

Three local-first plugins for planning, sustained execution, and multi-agent operations. They are packaged as portable Agent Plugins with Codex compatibility manifests and distributed from one GitHub marketplace.

| Plugin | What it does | Runtime |
| --- | --- | --- |
| [Autonomous Operator](plugins/autonomous-operator) | Builds bounded mission prompts for an Astra → Sol → Luna execution and reverse-review loop. | Python 3.9+, standard library |
| [Overnight Work](plugins/overnight-work) | Runs or resumes sustained work with a durable task ledger, evidence checks, and a morning handoff. | Python 3.9+, standard library |
| [Agent Bus Dashboard](plugins/agent-bus-dashboard) | Operates existing local AgentBus and Agent Coordinator services from a loopback dashboard and MCP launchers. | Python 3.9+, existing AgentBus/Coordinator install |

## Install

Add the marketplace once:

```sh
codex plugin marketplace add anon5376/codex-agent-plugins
```

Then install any plugin:

```sh
codex plugin add autonomous-operator@codex-agent-plugins
codex plugin add overnight-work@codex-agent-plugins
codex plugin add agent-bus-dashboard@codex-agent-plugins
```

Restart the ChatGPT desktop app after installation so newly installed skills are discovered.

## Design principles

- Local state stays local. No plugin ships a hosted account, telemetry service, or remote control plane.
- Authority stays explicit. Preparing a message, deployment, or mission does not authorize sending, publishing, or execution.
- Receipts are evidence, not magic. A hash identifies bytes; it does not prove the content is correct.
- Recovery is a feature. Long-running work should be resumable from durable state rather than hidden chat context.

These are early public releases. If a workflow is rough, open an issue with a reproducible case and remove private data first.

## License

[MIT](LICENSE)
