import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'runner.py'
spec = importlib.util.spec_from_file_location('hack_runner', SCRIPT)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.project / 'README.md').write_text('test repository\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.state = self.root / 'state'
        self.fake = self.root / 'codex'
        self.fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, re, sys, time
if '--version' in sys.argv:
 print('codex-cli 0.162.1'); sys.exit(0)
if 'login' in sys.argv:
 print('Logged in using ChatGPT',file=sys.stderr); sys.exit(0)
if '--help' in sys.argv:
 print('--ignore-user-config --json --sandbox --output-last-message'); sys.exit(0)
if 'features' in sys.argv:
 print('multi_agent stable false'); sys.exit(0)
p=sys.stdin.read()
mode=re.search(r'FAKE_MODE=(\\w+)',p).group(1)
if mode=='hang': time.sleep(20)
if mode=='invalid': print('not json',flush=True); sys.exit(0)
write=re.search(r'WRITE=([a-zA-Z0-9_./-]+)',p)
if write:
 path=pathlib.Path(write.group(1)); path.parent.mkdir(parents=True,exist_ok=True); path.write_text('hello\\n')
if mode=='keycheck':
 assert not any(os.environ.get(k) for k in ['OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'])
print(json.dumps({'type':'thread.started','thread_id':'fake-thread'}),flush=True)
if mode!='missing':
 print(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':20,'output_tokens':30}}),flush=True)
if mode=='posthang':time.sleep(20)
if mode=='fail': sys.exit(1)
''')
        self.fake.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.project), *args], stderr=subprocess.DEVNULL, text=True)

    def task(self, id='a', mode='success', path='src/a.txt', deps=None, verify=None):
        return {'id': id, 'goal': f'FAKE_MODE={mode} WRITE={path}',
                'write_paths': [path], 'depends_on': deps or [], 'skills': [], 'prepare': [],
                'verify': verify or [[sys.executable, '-c', f"from pathlib import Path; assert Path('{path}').read_text() == 'hello\\n'"]]}

    def plan(self, tasks=None, **limits):
        result = {'version': 1, 'model': 'gpt-6.1-sol', 'reasoning_effort': 'low',
                  'limits': {'max_parallel': 2, 'max_attempts': 12, 'max_observed_tokens': 10000,
                             'launch_reserve_tokens': 1000, 'session_seconds': 120, 'task_seconds': 10,
                             'verification_seconds': 10}, 'tasks': tasks or [self.task()]}
        result['limits'].update(limits)
        return result

    def run_plan(self, plan=None, **kwargs):
        return runner.run_session(plan or self.plan(), self.project, self.state, codex=str(self.fake), **kwargs)

    def test_rejects_cycles(self):
        p=self.plan([self.task('a',deps=['b']),self.task('b',path='src/b.txt',deps=['a'])])
        with self.assertRaises(ValueError): runner.validate_plan(p)

    def test_doctor_accepts_login_status_on_stderr_without_model_calls(self):
        r=runner.doctor(str(self.fake))
        self.assertEqual(r['auth'],'ChatGPT login')
        self.assertEqual(r['model_calls'],0)

    def test_integration_check_failure_preserves_integration_revision(self):
        command=[sys.executable,'-c',"from pathlib import Path; assert '/checks/' not in str(Path.cwd())"]
        r=self.run_plan(self.plan([self.task(verify=[command])]),live=True)
        self.assertEqual(r['tasks']['a']['status'],'failed')
        head=subprocess.check_output(['git','-C',r['integration_path'],'rev-parse','HEAD'],text=True).strip()
        self.assertEqual(head,self.base)

    def test_exclusive_controller_lock(self):
        with runner.session_lock(self.state):
            with self.assertRaises(ValueError):
                self.run_plan(live=True)

    def test_resume_after_interrupted_attempt_blocks_inference(self):
        r=self.run_plan(live=True)
        r['tasks']['a']['status']='running'
        (self.state/'state.json').write_text(json.dumps(r))
        r=self.run_plan(live=True)
        self.assertTrue(r['uncertain_usage'])
        self.assertEqual(r['attempts'],1)

    def test_rejects_dirty_original_project(self):
        (self.project/'README.md').write_text('unsaved changes')
        with self.assertRaises(ValueError):self.run_plan(live=True)

    def test_does_not_integrate_readonly_check_from_stale_snapshot(self):
        calls=[]
        original=runner.verify
        def recording_verify(task,worktree,*args):
            calls.append(str(worktree))
            return original(task,worktree,*args)
        runner.verify=recording_verify
        try:
            task=self.task();task.update(write_paths=[],goal='FAKE_MODE=success',verify=[[sys.executable,'-c','pass']])
            self.run_plan(self.plan([task]),live=True)
        finally:runner.verify=original
        self.assertTrue(any('/checks/' in s for s in calls))

    def test_rejects_path_escape(self):
        p=self.plan();p['tasks'][0]['write_paths']=['../outside']
        with self.assertRaises(ValueError): runner.validate_plan(p)

    def test_rejects_invalid_or_unbounded_limits(self):
        for value in [0, 3, True]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError): runner.validate_plan(self.plan(max_parallel=value))

    def test_rejects_unknown_model(self):
        p=self.plan();p['model']='invented-model'
        with self.assertRaises(ValueError):runner.validate_plan(p)

    def test_rejects_shell_verification(self):
        p=self.plan();p['tasks'][0]['verify']=['npm test']
        with self.assertRaises(ValueError):runner.validate_plan(p)

    def test_rejects_unknown_skills(self):
        p=self.plan();p['tasks'][0]['skills']=['does-not-exist']
        with self.assertRaises(ValueError):runner.validate_plan(p)

    def test_dry_run_has_no_inference_or_git_side_effects(self):
        result=self.run_plan(live=False)
        self.assertEqual(result['mode'],'dry-run')
        self.assertFalse(self.state.exists())
        self.assertEqual(self.git('rev-parse','HEAD').strip(),self.base)

    def test_integrates_changes_without_touching_original(self):
        result=self.run_plan(live=True)
        self.assertEqual(result['tasks']['a']['status'],'integrated')
        self.assertEqual(result['usage']['input_tokens'],100)
        self.assertEqual(result['usage']['cached_input_tokens'],20)
        self.assertEqual(result['usage']['output_tokens'],30)
        self.assertEqual(result['observed_tokens'],130)
        self.assertFalse((self.project/'src/a.txt').exists())
        self.assertEqual(self.git('rev-parse','HEAD').strip(),self.base)
        self.assertEqual((Path(result['integration_path'])/'src/a.txt').read_text(),'hello\n')

    def test_dependencies_see_integrated_parent(self):
        tasks=[self.task(),self.task('b',path='src/b.txt',deps=['a'],verify=[[sys.executable,'-c',"from pathlib import Path; assert Path('src/a.txt').exists(); assert Path('src/b.txt').exists()"]])]
        r=self.run_plan(self.plan(tasks),live=True)
        self.assertEqual(r['tasks']['b']['status'],'integrated')

    def test_resume_does_not_repeat_successful_tasks(self):
        self.run_plan(live=True)
        r=self.run_plan(live=True)
        self.assertEqual(r['attempts'],1)
        self.assertEqual(r['observed_tokens'],130)

    def test_recovers_integration_committed_before_controller_checkpoint(self):
        r=self.run_plan(live=True)
        r['tasks']['a']['status']='integrating'
        r['tasks']['a']['candidate_commit']=r['tasks']['a']['integrated_commit']
        (self.state/'state.json').write_text(json.dumps(r))
        r=self.run_plan(live=True)
        self.assertEqual(r['tasks']['a']['status'],'integrated')
        self.assertEqual(r['attempts'],1)
        self.assertEqual(r['observed_tokens'],130)

    def test_missing_usage_blocks_further_dispatch(self):
        p=self.plan([self.task(mode='missing'),self.task('b',path='src/b.txt',deps=['a'])])
        r=self.run_plan(p,live=True)
        self.assertEqual(r['tasks']['a']['status'],'failed')
        self.assertEqual(r['attempts'],1)
        self.assertIn('usage',r['stop_reason'])

    def test_scope_violation_rejects_patch(self):
        p=self.plan();p['tasks'][0]['write_paths']=['other.txt']
        r=self.run_plan(p,live=True)
        self.assertEqual(r['tasks']['a']['status'],'failed')
        self.assertFalse((Path(r['integration_path'])/'src/a.txt').exists())

    def test_failing_verification_does_not_integrate(self):
        p=self.plan([self.task(verify=[[sys.executable,'-c','raise SystemExit(1)']])])
        r=self.run_plan(p,live=True)
        self.assertEqual(r['tasks']['a']['status'],'failed')
        self.assertFalse((Path(r['integration_path'])/'src/a.txt').exists())

    def test_task_timeout_stops_worker(self):
        r=self.run_plan(self.plan([self.task(mode='hang')],task_seconds=.2),live=True)
        self.assertEqual(r['tasks']['a']['status'],'failed')
        self.assertIn('timeout',r['tasks']['a']['error'])

    def test_timeout_with_known_usage_stops_further_dispatch(self):
        p=self.plan([self.task(mode='posthang'),self.task('b',path='src/b.txt')],max_parallel=1,task_seconds=.2)
        r=self.run_plan(p,live=True)
        self.assertEqual(r['attempts'],1)
        self.assertIn('timeout',r['stop_reason'])

    def test_task_time_ceiling_includes_setup(self):
        p=self.plan(task_seconds=.15)
        p['tasks'][0]['prepare']=[[sys.executable,'-c','import time;time.sleep(.3)']]
        r=self.run_plan(p,live=True)
        self.assertEqual(r['tasks']['a']['status'],'failed')
        self.assertFalse((Path(r['integration_path'])/'src/a.txt').exists())

    def test_interrupted_metered_task_can_be_requeued(self):
        r=self.run_plan(live=True)
        r['tasks']['a']['status']='interrupted'
        (self.state/'state.json').write_text(json.dumps(r))
        script=SCRIPT.parent/'hackathon.py'
        p=subprocess.run([sys.executable,str(script),'retry','--state',str(self.state),'--task','a'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        saved=json.loads((self.state/'state.json').read_text())
        self.assertEqual(saved['tasks']['a']['status'],'pending')
        self.assertEqual(saved['observed_tokens'],130)

    @staticmethod
    def alive(pid):
        p=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True)
        return bool(p.stdout.strip()) and not p.stdout.strip().startswith('Z')

    def test_background_descendant_is_cleaned_after_success(self):
        output=self.root/'process';output.mkdir()
        pidfile=self.root/'child.pid'
        code="import subprocess,sys,pathlib;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']);pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
        runner.run_process([sys.executable,'-c',code,str(pidfile)],self.project,output,'check',3,threading.Event())
        pid=int(pidfile.read_text())
        alive=self.alive(pid)
        if alive:os.kill(pid,9)
        self.assertFalse(alive,'background descendant survived finished leader')

    def test_controller_death_does_not_remove_worker_timeout(self):
        output=self.root/'orphan';output.mkdir()
        pidfile=self.root/'orphan.pid'
        worker_code="import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(20)"
        driver="import sys,threading;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import runner;runner.run_process([sys.executable,'-c',sys.argv[5],sys.argv[4]],Path(sys.argv[2]),Path(sys.argv[3]),'model',.4,threading.Event())"
        controller=subprocess.Popen([sys.executable,'-c',driver,str(SCRIPT.parent),str(self.project),str(output),str(pidfile),worker_code])
        deadline=time.monotonic()+3
        while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(pidfile.exists())
        pid=int(pidfile.read_text())
        controller.kill();controller.wait()
        deadline=time.monotonic()+2
        while self.alive(pid) and time.monotonic()<deadline:time.sleep(.03)
        alive=self.alive(pid)
        if alive:os.kill(pid,9)
        self.assertFalse(alive,'worker survived controller death and its time ceiling')

    def test_watchdog_enforces_deadline_without_controller_polling(self):
        receipt=self.root/'watchdog.json'
        watchdog=SCRIPT.parent/'watchdog.py'
        p=subprocess.run([sys.executable,str(watchdog),'--parent',str(os.getpid()),'--timeout','.15',
                          '--receipt',str(receipt),'--',sys.executable,'-c','import time;time.sleep(20)'],timeout=3)
        self.assertEqual(p.returncode,124)
        saved=json.loads(receipt.read_text())
        self.assertTrue(saved['finished'])
        self.assertEqual(saved['exit_code'],124)

    def test_dispatch_reservation_prevents_launch(self):
        r=self.run_plan(self.plan(max_observed_tokens=500),live=True)
        self.assertEqual(r['attempts'],0)
        self.assertIn('budget',r['stop_reason'])

    def test_reservation_accounts_for_concurrent_workers(self):
        p=self.plan([self.task(),self.task('b',path='src/b.txt')],max_observed_tokens=1100)
        r=self.run_plan(p,live=True)
        self.assertEqual(r['attempts'],1)

    def test_attempt_ceiling_survives_resume(self):
        p=self.plan([self.task(mode='fail')],max_attempts=1)
        self.run_plan(p,live=True)
        r=self.run_plan(p,live=True)
        self.assertEqual(r['attempts'],1)

    def test_api_credentials_are_not_forwarded(self):
        old={k:os.environ.get(k) for k in ['OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL']}
        try:
            os.environ.update({k:'test-only-not-a-real-key' for k in old})
            r=self.run_plan(self.plan([self.task(mode='keycheck')]),live=True)
            self.assertEqual(r['tasks']['a']['status'],'integrated')
        finally:
            for k,v in old.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v

    def test_changed_plan_is_rejected_on_resume(self):
        self.run_plan(live=True)
        p=self.plan();p['tasks'][0]['goal']+=' changed'
        with self.assertRaises(ValueError):self.run_plan(p,live=True)

    def test_cli_invocation_disables_fast_and_nested_agents(self):
        args=runner.codex_command('codex',Path('/tmp/work'),Path('/tmp/final'),self.plan())
        self.assertIn('--ignore-user-config',args)
        for flag in ['fast_mode','ultrafast_mode','multi_agent']:
            self.assertIn(flag,args)
        self.assertIn('service_tier="default"',args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)


if __name__=='__main__':unittest.main()
