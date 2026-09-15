# Agent Bus Dashboard

Agent Bus Dashboard is a dependency-free local switchboard for an existing AgentBus or Agent Coordinator installation. It shows projects, attached agents, live status, current work, usage, tasks, and complete conversation history, with explicit controls for starting, stopping, opening, and messaging agents.

It does not install or start a broker. If no service is running, the dashboard reports that state.

## Install

```sh
codex plugin marketplace add anon5376/codex-agent-plugins
codex plugin add agent-bus-dashboard@codex-agent-plugins
```

Restart the ChatGPT desktop app, then ask:

> Open my local agent dashboard.

## Run directly

From this plugin directory:

```sh
python3 scripts/dashboard_server.py
```

Open <http://127.0.0.1:8788>, choose **Local setup**, and enter the directory containing your projects. Every direct child plus nested Git repositories becomes a project entry.

Configuration is stored with mode 0600 at `~/.agent-bus/dashboard.json`. CLI flags and `AGENT_DASHBOARD_*` environment variables override the file. The dashboard reads the live broker at `http://127.0.0.1:7717` by default and can also read an optional coordinator database and AgentBus history database.

## Requirements

- Python 3.9 or newer
- No third-party Python or frontend dependencies
- An existing AgentBus or Agent Coordinator installation for live data and MCP tools
- macOS only for the **Open session in Terminal** control; the rest of the dashboard is portable

The server binds to loopback and has no built-in sign-in. Do not bind it to a network interface without placing authentication and transport security in front of it.

## Verify

```sh
python3 scripts/dashboard_server.py --check
```

The check renders every configured source and runs role, CSRF, folder-state, configuration, and broker-loopback tests against throwaway state.

## Data boundaries

The dashboard reads configured services and databases in place. It does not migrate or rewrite them. Editing a registered agent role writes only that field back to `agents.json`; pins, hidden projects, and conversation archive/trash state live in the dashboard's own state file.
