"""Bounded local Codex orchestration. No SDK dependencies or model-manager calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import threading
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / 'skills'
DEFAULT_LIMITS = dict(max_parallel=2, max_attempts=12, max_observed_tokens=300000,
                      launch_reserve_tokens=50000, session_seconds=11700,
                      task_seconds=900, verification_seconds=180)
KEYS = ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_API_BASE',
        'AZURE_OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'CURSOR_API_KEY')


def clean_env():
    env = dict(os.environ)
    for key in KEYS:
        env.pop(key, None)
    env['GIT_TERMINAL_PROMPT'] = '0'
    return env


def checked(argv, cwd=None, timeout=30):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, env=clean_env(),
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{argv[0]} exited {result.returncode}: {(result.stderr or result.stdout)[-2000:]}')
    return result.stdout.strip() or result.stderr.strip()


def git(project, *args):
    return checked(['git', '-C', str(project), *args])


def valid_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        return False
    path = PurePosixPath(value.rstrip('/'))
    return (not path.is_absolute() and str(path) not in ('', '.')
            and all(p not in ('.', '..', '.git') for p in value.rstrip('/').split('/')))


def owns(path, prefixes):
    return any(path == p.rstrip('/') or path.startswith(p.rstrip('/') + '/') for p in prefixes)


def overlap(a, b):
    return any(owns(p, b) or owns(q, a) for p in a for q in b)


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get('version') != 1:
        raise ValueError('Expected plan version 1')
    if plan.get('model') != 'gpt-6.1-sol':
        raise ValueError('This event profile only permits gpt-6.1-sol; no substitution')
    if plan.get('reasoning_effort', 'low') not in ('low', 'medium', 'high'):
        raise ValueError('Invalid reasoning effort')
    limits = {**DEFAULT_LIMITS, **plan.get('limits', {})}
    if set(limits) != set(DEFAULT_LIMITS):
        raise ValueError('Unknown limit key')
    for key, value in limits.items():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'Invalid positive finite limit: {key}')
    for key in ('max_parallel', 'max_attempts', 'max_observed_tokens', 'launch_reserve_tokens'):
        if not isinstance(limits[key], int):
            raise ValueError(f'{key} must be an integer')
    if limits['max_parallel'] > 2:
        raise ValueError('At most two concurrent workers')
    tasks = plan.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise ValueError('A plan needs at least one task')
    ids = []
    for task in tasks:
        if not isinstance(task, dict) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', task.get('id', '')):
            raise ValueError('Task IDs must be short lowercase identifiers')
        ids.append(task['id'])
        if not isinstance(task.get('goal'), str) or not 1 <= len(task['goal']) <= 12000:
            raise ValueError('Task goal must contain 1..12000 characters')
        if not isinstance(task.get('write_paths'), list) or not all(valid_path(p) for p in task['write_paths']):
            raise ValueError('Write ownership must use explicit safe relative paths')
        for key in ('depends_on', 'skills'):
            if not isinstance(task.get(key, []), list) or not all(isinstance(s, str) for s in task.get(key, [])):
                raise ValueError(f'Invalid {key}')
        for name in task.get('skills', []):
            if not re.fullmatch(r'[a-z][a-z0-9-]+', name) or not (SKILLS / name / 'SKILL.md').is_file():
                raise ValueError(f'Unknown bundled skill: {name}')
        for key in ('prepare', 'verify'):
            commands = task.get(key, [])
            if not isinstance(commands, list) or (key == 'verify' and not commands):
                raise ValueError('Each task needs verification argv arrays')
            for command in commands:
                if (not isinstance(command, list) or not command
                        or not all(isinstance(x, str) and x and '\x00' not in x for x in command)):
                    raise ValueError('Commands are argv arrays, never shell strings')
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate task ID')
    known = set(ids)
    graph = {t['id']: t.get('depends_on', []) for t in tasks}
    if any(d not in known for deps in graph.values() for d in deps):
        raise ValueError('Unknown dependency')
    done = set()
    while len(done) < len(ids):
        ready = {id for id, deps in graph.items() if id not in done and set(deps) <= done}
        if not ready:
            raise ValueError('Cyclic dependencies')
        done.update(ready)
    return limits


def atomic_json(path, value):
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('x') as handle:
        os.chmod(temp, 0o600)
        json.dump(value, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


@contextmanager
def session_lock(directory):
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (directory / 'controller.lock').open('a') as handle:
        os.chmod(handle.name, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another controller owns this session') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def codex_command(binary, worktree, final_path, plan):
    args = [binary, 'exec', '--ignore-user-config', '--json', '--color', 'never',
            '--model', plan['model'], '--sandbox', 'workspace-write' if plan.get('_writes', True) else 'read-only',
            '--cd', str(worktree), '--output-last-message', str(final_path),
            '-c', 'model_provider="openai"', '-c', 'service_tier="default"',
            '-c', 'model_reasoning_effort=' + json.dumps(plan.get('reasoning_effort', 'low')),
            '-c', 'approval_policy="never"']
    for flag in ('fast_mode', 'ultrafast_mode', 'multi_agent', 'multi_agent_v2', 'plugins', 'apps', 'hooks'):
        args += ['--disable', flag]
    return args + ['-']


def doctor(binary='codex'):
    version = checked([binary, '--version'])
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (0, 162, 1):
        raise ValueError('Install Codex CLI 0.162.1 or newer')
    auth = checked([binary, 'login', 'status'])
    if 'chatgpt' not in auth.lower():
        raise ValueError('This profile requires your local ChatGPT Codex login, not API-key auth')
    help_text = checked([binary, 'exec', '--help'])
    for flag in ('--ignore-user-config', '--json', '--sandbox', '--output-last-message'):
        if flag not in help_text:
            raise ValueError(f'Installed CLI is missing {flag}')
    return {'version': version, 'auth': 'ChatGPT login', 'model_calls': 0}


def prompt_for(task, remaining_seconds, previous_error=''):
    parts = [
        'You are one bounded engineering worker. Implement only the task below in this Git worktree.',
        'Read applicable AGENTS.md. Do not spawn agents, switch model/provider/speed, commit, push, deploy, '
        'send messages, read credential files, or modify other worktrees. Do not add features outside the goal.',
        'Only change these owned paths: ' + json.dumps(task['write_paths']) + '.',
        f'Remaining session time is about {int(remaining_seconds)} seconds. Produce the smallest complete change.',
        'Use supplied skills when applicable. Run the declared checks. Final answer: changed files, '
        'exact check commands/results, remaining failures. Never claim a test passed without executing it.',
        'TASK\n' + task['goal'],
        'CHECKS\n' + json.dumps(task['verify']),
    ]
    if previous_error:
        parts.append('PREVIOUS ATTEMPT FAILURE\n' + previous_error[-2500:])
    for name in task.get('skills', []):
        parts.append('BUNDLED SKILL ' + name + '\n' + (SKILLS / name / 'SKILL.md').read_text())
    text = '\n\n'.join(parts)
    if len(text) > 32000:
        raise ValueError('Selected task context exceeds 32000 characters; reduce the skill selection')
    return text


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_process(argv, cwd, directory, label, timeout, stop, prompt=None):
    """Run a process group, bound lifetime, capture output; never execute via a shell."""
    stdout = directory / (label + '.stdout')
    stderr = directory / (label + '.stderr')
    started = time.monotonic()
    error = ''
    with stdout.open('wb') as out, stderr.open('wb') as err, tempfile.TemporaryFile() as incoming:
        os.chmod(stdout, 0o600); os.chmod(stderr, 0o600)
        if prompt is not None:
            incoming.write(prompt.encode())
            incoming.seek(0)
        supervised = [sys.executable, str(Path(__file__).with_name('watchdog.py')),
                      '--parent', str(os.getpid()), '--timeout', str(max(.001, timeout)),
                      '--receipt', str(directory / (label + '.process.json')), '--', *map(str, argv)]
        process = subprocess.Popen(supervised, cwd=cwd, env=clean_env(),
                                   stdin=incoming if prompt is not None else subprocess.DEVNULL,
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            while process.poll() is None:
                if stop.is_set() or time.monotonic() - started > timeout:
                    error = 'stopped' if stop.is_set() else 'timeout'
                    kill_group(process)
                    break
                if stdout.stat().st_size + stderr.stat().st_size > 8 * 1024 * 1024:
                    error = 'log size ceiling'
                    kill_group(process)
                    break
                time.sleep(.03)
        finally:
            kill_group(process)
    if process.returncode == 124:
        error = 'timeout'
    return {'argv': [str(x) for x in argv], 'exit_code': process.returncode,
            'error': error, 'stdout': str(stdout), 'stderr': str(stderr)}


def collect_usage(path):
    result = dict(input_tokens=0, cached_input_tokens=0, output_tokens=0)
    complete = 0
    malformed = False
    failed = False
    with Path(path).open(errors='replace') as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError('Non-object event')
                if item.get('type') in ('error', 'turn.failed'):
                    failed = True
                if item.get('type') == 'turn.completed':
                    usage = item['usage']
                    for key in result:
                        n = usage.get(key, 0 if key == 'cached_input_tokens' else None)
                        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
                            raise ValueError('Invalid usage')
                        result[key] += n
                    if usage.get('cached_input_tokens', 0) > usage['input_tokens']:
                        raise ValueError('Cached tokens exceed total input')
                    complete += 1
            except (ValueError, KeyError, TypeError):
                malformed = True
    return result, complete > 0 and not malformed and not failed


def changed_paths(worktree):
    names = git(worktree, 'diff', '--no-renames', '--name-only', '-z', 'HEAD').split('\x00')
    names += git(worktree, 'ls-files', '--others', '--exclude-standard', '-z').split('\x00')
    return sorted({x for x in names if x})


def worktree_add(project, path, revision):
    git(project, 'worktree', 'add', '--detach', str(path), revision)


def verify(task, worktree, output, limits, stop):
    receipts = []
    for i, argv in enumerate(task.get('prepare', []) + task['verify']):
        timeout = min(limits['verification_seconds'], limits.get('_deadline', float('inf')) - time.monotonic())
        if timeout <= 0 or stop.is_set():
            raise RuntimeError('session time ceiling or stop during verification')
        result = run_process(argv, worktree, output, 'check-' + str(i), timeout, stop)
        receipts.append(result)
        if result['exit_code'] != 0 or result['error']:
            raise RuntimeError('verification failed: ' + json.dumps(result))
    return receipts


def worker(task, plan, limits, project, state_dir, revision, attempt, stop, remaining, codex, prior_error):
    directory = state_dir / 'attempts' / (task['id'] + '-' + str(attempt))
    directory.mkdir(parents=True, mode=0o700)
    worktree = directory / 'worktree'
    usage = dict(input_tokens=0, cached_input_tokens=0, output_tokens=0)
    result = {'usage': usage, 'usage_known': True, 'worktree': str(worktree), 'checks': []}
    limits = {**limits, '_deadline': min(limits.get('_deadline', float('inf')),
                                       time.monotonic() + min(limits['task_seconds'], remaining))}
    try:
        worktree_add(project, worktree, revision)
        # Setup before model inference, so dependency failures do not spend model credits.
        for i, argv in enumerate(task.get('prepare', [])):
            prep = run_process(argv, worktree, directory, 'prepare-' + str(i),
                               min(limits['verification_seconds'], limits['_deadline'] - time.monotonic()), stop)
            if prep['exit_code'] or prep['error']:
                raise RuntimeError('prepare failed: ' + json.dumps(prep))
        config = {**plan, '_writes': bool(task['write_paths'])}
        args = codex_command(codex, worktree, directory / 'final.txt', config)
        request = prompt_for(task, remaining, prior_error)
        remaining = limits['_deadline'] - time.monotonic()
        if remaining <= 0 or stop.is_set():
            raise RuntimeError('task timeout before inference')
        result['usage_known'] = False
        process = run_process(args, worktree, directory, 'codex',
                              min(limits['task_seconds'], remaining), stop, request)
        usage, known = collect_usage(process['stdout'])
        result.update(usage=usage, usage_known=known, invocation=process)
        if process['exit_code'] or process['error']:
            raise RuntimeError('Codex ' + (process['error'] or 'exit ' + str(process['exit_code'])))
        if not known:
            raise RuntimeError('missing or invalid usage events; cannot safely continue dispatch')
        if git(worktree, 'rev-parse', 'HEAD') != revision:
            raise RuntimeError('worker changed Git HEAD; commits must be made by the coordinator')
        paths = changed_paths(worktree)
        if any(not owns(path, task['write_paths']) for path in paths):
            raise RuntimeError('write scope violation: ' + ', '.join(paths))
        result['checks'] = verify({**task, 'prepare': []}, worktree, directory, limits, stop)
        paths = changed_paths(worktree)
        if any(not owns(path, task['write_paths']) for path in paths):
            raise RuntimeError('verification wrote outside declared ownership')
        if paths:
            git(worktree, 'add', '--all')
            git(worktree, '-c', 'user.name=Hackathon Kit', '-c', 'user.email=hackathon@local.invalid',
                'commit', '-m', 'hackathon: ' + task['id'])
        result.update(commit=git(worktree, 'rev-parse', 'HEAD'), changed_paths=paths, error='')
    except Exception as exc:
        result['error'] = str(exc)
    return result


def integrate(task, result, project, state, state_dir, limits, stop, checkpoint=None):
    integration = Path(state['integration_path'])
    if changed_paths(integration):
        raise RuntimeError('Integration checkout has operator edits; refusing to overwrite them')
    directory = state_dir / 'checks' / (task['id'] + '-' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, mode=0o700)
    candidate = directory / 'worktree'
    current = git(integration, 'rev-parse', 'HEAD')
    worktree_add(project, candidate, current)
    if result['changed_paths']:
        git(candidate, '-c', 'user.name=Hackathon Kit', '-c', 'user.email=hackathon@local.invalid',
            'cherry-pick', result['commit'])
    result['integration_checks'] = verify(task, candidate, directory, limits, stop)
    if changed_paths(candidate):
        raise RuntimeError('Integration verification modified source; refusing an untested commit')
    revision = git(candidate, 'rev-parse', 'HEAD')
    if checkpoint is not None:
        checkpoint(revision)
    git(integration, 'merge', '--ff-only', revision)
    return revision


def run_session(plan, project, state_dir, *, live=False, codex='codex'):
    limits = validate_plan(plan)
    project, state_dir = Path(project).resolve(), Path(state_dir).resolve()
    if not live:
        return {'mode': 'dry-run', 'model_calls': 0, 'tasks': [t['id'] for t in plan['tasks']],
                'limits': limits, 'state_path': str(state_dir),
                'budget_note': 'Observed-token guard, not a provider dollar cap. In-flight usage can overshoot.'}
    if state_dir == project or project in state_dir.parents:
        raise ValueError('Keep session state outside the target repository')
    if git(project, 'rev-parse', '--show-toplevel') != str(project):
        raise ValueError('Project must be the Git repository root')
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    with session_lock(state_dir):
        state_path = state_dir / 'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state['plan_sha256'] != fingerprint or state['project'] != str(project):
                raise ValueError('Plan or project changed; use a new session directory')
            for row in state['tasks'].values():
                if row['status'] == 'running':
                    row.update(status='interrupted', usage_known=False,
                               error='Controller interrupted; usage may be incomplete')
                    state['uncertain_usage'] = True
        else:
            if changed_paths(project):
                raise ValueError('Commit or stash target-project changes before starting an isolated session')
            revision = git(project, 'rev-parse', 'HEAD')
            integration = state_dir / 'integration'
            branch = 'hackathon/' + uuid.uuid4().hex[:10]
            git(project, 'worktree', 'add', '-b', branch, str(integration), revision)
            state = dict(version=1, project=str(project), plan_sha256=fingerprint, base_revision=revision,
                         integration_path=str(integration), integration_branch=branch, started_at=time.time(),
                         elapsed_seconds=0, attempts=0, observed_tokens=0, uncertain_usage=False,
                         usage=dict(input_tokens=0, cached_input_tokens=0, output_tokens=0),
                         tasks={t['id']: dict(status='pending', attempts=0) for t in plan['tasks']})
        state['mode'] = 'live'
        state['stop_reason'] = ''
        stop = threading.Event()
        started = time.monotonic()
        prior_elapsed = max(state['elapsed_seconds'], time.time() - state['started_at'])
        limits['_deadline'] = time.monotonic() + limits['session_seconds'] - prior_elapsed
        running = {}
        by_id = {t['id']: t for t in plan['tasks']}

        def save():
            state['elapsed_seconds'] = prior_elapsed + time.monotonic() - started
            atomic_json(state_path, state)

        save()
        # An integration journal is written after metering but before advancing the branch.
        # Recover that transaction without spending another model call.
        for id, row in state['tasks'].items():
            if row['status'] != 'integrating':
                continue
            candidate = row.get('candidate_commit')
            head = git(Path(state['integration_path']), 'rev-parse', 'HEAD')
            accepted = candidate and subprocess.run(
                ['git', '-C', state['integration_path'], 'merge-base', '--is-ancestor', candidate, head],
                env=clean_env(), capture_output=True).returncode == 0
            if accepted:
                row.update(status='integrated', integrated_commit=candidate)
            elif state['elapsed_seconds'] >= limits['session_seconds']:
                row.update(status='failed', error='session expired before interrupted integration could finish')
            else:
                try:
                    def journal(revision, row=row):
                        row['candidate_commit'] = revision
                        save()
                    row['integrated_commit'] = integrate(by_id[id], row, project, state, state_dir, limits, stop, journal)
                    row['status'] = 'integrated'
                except Exception as exc:
                    row.update(status='failed', error='integration recovery failed: ' + str(exc))
            save()
        pool = ThreadPoolExecutor(max_workers=limits['max_parallel'])
        interrupted = False
        try:
            while True:
                elapsed = prior_elapsed + time.monotonic() - started
                if elapsed >= limits['session_seconds']:
                    state['stop_reason'] = 'session time ceiling'
                    stop.set()
                if state['observed_tokens'] >= limits['max_observed_tokens']:
                    state['stop_reason'] = 'observed-token budget exhausted'
                    stop.set()
                if state['uncertain_usage']:
                    state['stop_reason'] = 'unknown usage; reconcile before starting another session'
                    stop.set()
                reserved = len(running) * limits['launch_reserve_tokens']
                for id, task in by_id.items():
                    row = state['tasks'][id]
                    if stop.is_set() or row['status'] != 'pending' or len(running) >= limits['max_parallel']:
                        continue
                    if not all(state['tasks'][d]['status'] == 'integrated' for d in task.get('depends_on', [])):
                        continue
                    if any(overlap(task['write_paths'], by_id[r]['write_paths']) for r in running.values()):
                        continue
                    if state['attempts'] >= limits['max_attempts']:
                        state['stop_reason'] = 'attempt ceiling'
                        continue
                    if state['observed_tokens'] + reserved + limits['launch_reserve_tokens'] > limits['max_observed_tokens']:
                        state['stop_reason'] = 'observed-token budget / dispatch reservation'
                        continue
                    row['attempts'] += 1
                    state['attempts'] += 1
                    row['status'] = 'running'
                    # Persist reservation before any inference; interruption cannot erase an attempt.
                    save()
                    future = pool.submit(worker, task, plan, limits, project, state_dir,
                                         git(Path(state['integration_path']), 'rev-parse', 'HEAD'),
                                         row['attempts'], stop, limits['session_seconds'] - elapsed,
                                         codex, row.get('error', ''))
                    running[future] = id
                    reserved += limits['launch_reserve_tokens']
                if not running:
                    if not state['stop_reason'] and any(r['status'] != 'integrated' for r in state['tasks'].values()):
                        state['stop_reason'] = 'blocked or failed tasks; inspect receipts'
                    break
                for future in list(running):
                    if not future.done():
                        continue
                    id = running.pop(future)
                    result = future.result()
                    for key, count in result['usage'].items():
                        state['usage'][key] += count
                    state['observed_tokens'] = state['usage']['input_tokens'] + state['usage']['output_tokens']
                    if not result['usage_known']:
                        state['uncertain_usage'] = True
                    row = state['tasks'][id]
                    row.update(result, status='failed')
                    if 'timeout' in result['error']:
                        state['stop_reason'] = 'worker timeout; dispatch stopped'
                        stop.set()
                    if not result['error'] and not stop.is_set():
                        try:
                            row['status'] = 'integrating'
                            save()
                            def journal(revision):
                                row['candidate_commit'] = revision
                                save()
                            row['integrated_commit'] = integrate(by_id[id], row, project, state, state_dir, limits, stop, journal)
                            row['status'] = 'integrated'
                        except Exception as exc:
                            row['status'] = 'failed'
                            row['error'] = 'integration failed: ' + str(exc)
                    save()
                time.sleep(.02)
        except KeyboardInterrupt:
            interrupted = True
            state['stop_reason'] = 'operator interrupt'
            stop.set()
        finally:
            stop.set()
            pool.shutdown(wait=True, cancel_futures=True)
            # Preserve metering from futures not yet processed (including interrupt cleanup).
            for future, id in running.items():
                if future.done() and not future.cancelled():
                    result = future.result()
                    for key, count in result['usage'].items():
                        state['usage'][key] += count
                    state['tasks'][id].update(result, status='interrupted')
                    if not result['usage_known']:
                        state['uncertain_usage'] = True
                else:
                    state['tasks'][id]['status'] = 'interrupted'
                    state['uncertain_usage'] = True
            state['observed_tokens'] = state['usage']['input_tokens'] + state['usage']['output_tokens']
            if all(row['status'] == 'integrated' for row in state['tasks'].values()):
                state['stop_reason'] = ''
            save()
        return state
