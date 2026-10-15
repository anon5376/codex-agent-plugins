"""Independent POSIX lifetime supervisor; stays alive if the controller is killed."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def terminate_group(pid):
    # The leader may already have exited while ordinary background descendants remain.
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(.06)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--parent',type=int,required=True)
    parser.add_argument('--timeout',type=float,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    stopped=False
    def stop(signum,frame):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    child=None
    code=1
    started=time.monotonic()
    receipt={'supervisor_pid':os.getpid(),'parent_pid':args.parent,'finished':False}
    def save():
        with args.receipt.open('w') as handle:
            os.chmod(args.receipt,0o600)
            json.dump(receipt,handle)
    try:
        # Never launch work if the original controller already disappeared.
        if os.getppid()!=args.parent:
            return 143
        child=subprocess.Popen(command,start_new_session=True)
        receipt['worker_pid']=child.pid
        save()
        while child.poll() is None:
            if stopped or os.getppid()!=args.parent:
                code=143
                break
            if time.monotonic()-started>=args.timeout:
                code=124
                break
            time.sleep(.02)
        else:
            code=child.returncode
    finally:
        if child is not None:
            terminate_group(child.pid)
            child.wait()
        receipt.update(finished=True,exit_code=code)
        save()
    return code


if __name__=='__main__':
    raise SystemExit(main())
