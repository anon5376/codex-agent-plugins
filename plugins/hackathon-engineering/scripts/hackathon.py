#!/usr/bin/env python3
"""CLI entry point. Dry-run is the default; --live is explicit."""
import argparse
import json
from pathlib import Path
import sys

from runner import doctor, run_session, session_lock, atomic_json, validate_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    d = sub.add_parser('doctor', help='Check installed Codex and login without model calls')
    d.add_argument('--codex', default='codex')
    r = sub.add_parser('run', help='Validate/preview a plan; add --live to execute')
    r.add_argument('--plan', type=Path, required=True)
    r.add_argument('--project', type=Path, required=True)
    r.add_argument('--state', type=Path, required=True, help='Session directory outside the target repository')
    r.add_argument('--codex', default='codex')
    r.add_argument('--live', action='store_true')
    s = sub.add_parser('status', help='Show persisted progress, limits and integration location')
    s.add_argument('--state', type=Path, required=True)
    retry = sub.add_parser('retry', help='Explicitly requeue one failed task (maximum two attempts per task)')
    retry.add_argument('--state', type=Path, required=True)
    retry.add_argument('--task', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            result = doctor(args.codex)
        elif args.command == 'status':
            result = json.loads((args.state / 'state.json').read_text())
        elif args.command == 'retry':
            with session_lock(args.state):
                path = args.state / 'state.json'
                result = json.loads(path.read_text())
                task = result['tasks'].get(args.task)
                if not task or task['status'] not in ('failed','interrupted') or task['attempts'] >= 2:
                    raise ValueError('Only failed/interrupted tasks with fewer than two attempts can be requeued')
                if result['uncertain_usage']:
                    raise ValueError('Usage is uncertain; reconcile before a new live session')
                task['status'] = 'pending'
                atomic_json(path, result)
        else:
            plan = json.loads(args.plan.read_text())
            validate_plan(plan)
            if args.live:
                doctor(args.codex)
            result = run_session(plan, args.project, args.state, live=args.live, codex=args.codex)
        # A compact status is printable; raw model/tool logs stay in private local files.
        if 'tasks' in result and isinstance(result['tasks'], dict):
            display = {k: result[k] for k in ('mode', 'attempts', 'observed_tokens', 'usage',
                                              'elapsed_seconds', 'integration_path', 'integration_branch',
                                              'stop_reason') if k in result}
            display['tasks'] = {id: {'status': t['status'], 'attempts': t['attempts'],
                                     'error': t.get('error', '')[:180]} for id,t in result['tasks'].items()}
        else:
            display = result
        print(json.dumps(display, indent=2))
        if args.command == 'run' and result.get('mode') == 'live' and any(t['status'] != 'integrated' for t in result['tasks'].values()):
            return 2
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        print('hackathon: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
