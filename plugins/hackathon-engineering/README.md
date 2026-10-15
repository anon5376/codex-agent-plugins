# Hackathon Engineering

A small Codex-only development kit for two builders and a 210-minute event. The dispatcher is ordinary Python; only coding workers use a model. There is no paid manager agent and no application implementation in this package.

## Prepare before the event

Requires macOS/Linux, Python 3.11+, Git, and Node.js for the Codex installation. CLI flags were checked with Codex **0.162.1**. Tests use a local fake worker and do not call a model.

```sh
npm install -g @openai/codex@0.162.1
codex login
git clone --branch feat/hackathon-engineering https://github.com/anon5376/codex-agent-plugins.git
cd codex-agent-plugins
python3 plugins/hackathon-engineering/scripts/hackathon.py doctor
```

Optional: install the skills in interactive Codex from this branch:

```sh
codex plugin marketplace add anon5376/codex-agent-plugins --ref feat/hackathon-engineering
codex plugin add hackathon-engineering@codex-agent-plugins
```

Restart Codex if the skills do not appear. The standalone runner needs no plugin installation: it reads only the selected bundled skill bodies itself. Its worker invocations disable unrelated plugins, hooks, nested agents, fast/ultrafast mode and custom user configuration; repository instructions and sandbox rules still apply.

## Event-day start

Create an empty committed repository **during the event**. Set the project and state paths explicitly; state must stay outside the project. Use an absolute path to the kit script when launching from another directory.

```sh
mkdir recon
cd recon
git init
git commit --allow-empty -m "Start hackathon build"
```

From the kit checkout, preview the instruction-only RECON task plan. Adjust paths to your machine:

```sh
python3 plugins/hackathon-engineering/scripts/hackathon.py run \
  --plan plugins/hackathon-engineering/examples/recon-plan.json \
  --project /absolute/path/recon \
  --state /absolute/path/recon-session
```

This is a **dry run**: no inference, worktrees or session files. The example is a starting plan, not a promise that an unseen application will build without changes. Verify the first scaffold and its npm scripts early; dependencies are installed separately in each worktree.

To execute the reviewed plan, repeat that command with `--live`. The runner first checks the local ChatGPT Codex login. API-key environment overrides are removed from worker and check subprocesses. The kit neither reads nor copies authentication files. Configure the application API credentials separately on the final integrated checkout; do not put them into the plan or repository.

## What happens

- Each task runs in a detached Git worktree. Overlapping ownership is serialized; dependencies must be integrated first.
- The worker has an explicit file scope and a small prompt containing only its selected skills. Out-of-scope changes, CLI errors, missing usage or failed verification reject the result.
- A successful worker commit is replayed into a fresh candidate worktree and checked again. Only then does the separate integration branch advance. Your original checkout and branch are untouched.
- The state directory retains private logs, metering, failed attempts and worktrees. Do not commit or publish it. File ownership is an integration check, not a per-file security sandbox; only use trusted repositories and verification commands.
- Model output is never trusted as a completion signal. The declared commands must exit successfully. Deterministic checks still do not prove visual quality, live API access or production correctness.

The printed `integration_path` is the assembled application to inspect and run. After a failed task, inspect its logs/worktree, diagnose the failure, then explicitly retry once if appropriate:

```sh
python3 plugins/hackathon-engineering/scripts/hackathon.py status --state /absolute/path/recon-session
python3 plugins/hackathon-engineering/scripts/hackathon.py retry --state /absolute/path/recon-session --task engine
```

Repeat the original `run ... --live` to resume. Successful tasks are not rerun. A modified plan requires a new session; preserve the old usage when deciding the new budget. Ctrl-C stops worker process groups and retains receipts. A fully metered interrupted task can be explicitly requeued with `retry`. An interrupted call with unknown usage blocks further automatic dispatch; check its logs and actual account balance before deciding on a new session and adjusted budget. Do not erase this uncertainty by blindly restarting with an empty state.

An independent watchdog supervises each model/check command and checks the controller's lifetime. It also cleans up ordinary background descendants in the command's process group. This is lifetime containment for trusted development commands, not a security boundary against programs that deliberately detach into new sessions. Integration transactions are journaled after usage accounting and before the integration branch advances, so a controller restart can finish that transaction without repeating model inference.

## Spending and time controls

| Default | Value |
| --- | --- |
| Model / effort / service | `gpt-6.1-sol` / `low` / `default` |
| Concurrent workers | 2 maximum |
| Total worker attempts | 12 |
| Attempts per task | 1 initially; one explicit retry |
| Session clock | 195 minutes from first live start, including pauses |
| Worker attempt ceiling, including setup and its checks | 15 minutes |
| Per setup/check command timeout | 3 minutes, also bounded by session deadline |
| Observed input + output token ceiling | 300,000 |
| Reservation before dispatch | 50,000 per in-flight worker |

**These are local dispatch controls, not an exact dollar cap.** Usage is reported after a turn. An in-flight call can exceed its reservation before the runner learns its cost. Cached input is tracked as a subset of input; reasoning output is not counted twice. The full input count makes this a conservative token guard, not a price estimate. Check actual Codex balance separately; event Codex credits and API credits are different allowances. The runner makes no API requests itself.

Use a small live smoke task on your own machine before depending on the kit. This preparation validated the CLI/configuration and offline process behavior; no live model-inference call was run. Account availability, venue network and actual burn rate remain event-day checks.

## Bundled skills

| Skill | Purpose |
| --- | --- |
| `hackathon-coordination` | Ownership, bounded delegation, retries and budget decisions |
| `hackathon-slice` | One working vertical slice and explicit cut points |
| `hackathon-contracts` | Shared schemas, units, bounds and model-output validation |
| `hackathon-debugging` | Reproduction, causal diagnosis and minimal correction |
| `hackathon-verification` | Fresh check evidence, integration and truthful claims |
| `hackathon-frontend` | Clear asynchronous states, usable controls and demo polish |

Each is roughly 200 words. They are focused project workflows, not a claim of being globally ranked "best". Only selected bodies enter each worker prompt.

## Verification

```sh
python3 -m unittest discover -s plugins/hackathon-engineering/tests -p 'test_*.py'
```

The test worker is deliberately fake: it exercises real subprocesses, Git operations and the coordinator's failure paths without spending credits. It does not establish model quality or hackathon placement.

## Event boundary and sources

This is a reusable development tool. The RECON example contains task instructions only. Do not present this pre-event kit as code built during the competition. Published event rules require Codex CLI/App and restrict prebuilt entries; they do not explicitly approve this wrapper. Confirm the tooling interpretation with the host before relying on it.

- [Official event rules](https://luma.com/OpenAIDevDay2026CommunityHackathonTokyo)
- [Official Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Official Codex CLI options](https://learn.chatgpt.com/docs/cli/reference)
- [Official skill format and discovery](https://learn.chatgpt.com/docs/build-skills)

No automatic deployment, messaging or public release of project output is included. MIT; see the repository license.
