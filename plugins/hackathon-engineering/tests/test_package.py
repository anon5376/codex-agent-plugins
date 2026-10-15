import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from runner import SKILLS,validate_plan,prompt_for


class PackageTests(unittest.TestCase):
    def test_six_discoverable_compact_skills(self):
        paths=list(SKILLS.glob('*/SKILL.md'))
        self.assertEqual(len(paths),6)
        for path in paths:
            text=path.read_text()
            front=text.split('---',2)[1]
            self.assertIn('name: '+path.parent.name,front)
            self.assertRegex(front,r'description: Use when ')
            self.assertLess(len(text.split()),330)
            self.assertTrue((path.parent/'agents/openai.yaml').exists())

    def test_example_is_instruction_only_and_valid(self):
        p=json.loads((ROOT/'examples/recon-plan.json').read_text())
        validate_plan(p)
        self.assertEqual(len(p['tasks']),7)
        for task in p['tasks']:
            self.assertLess(len(prompt_for(task,600)),32000)
        self.assertFalse((ROOT/'app').exists())

    def test_manifests_and_marketplace_match(self):
        portable=json.loads((ROOT/'plugin.json').read_text())
        codex=json.loads((ROOT/'.codex-plugin/plugin.json').read_text())
        self.assertEqual(portable['name'],codex['name'])
        self.assertEqual(portable['version'],codex['version'])
        self.assertEqual(codex['skills'],'./skills/')
        market=json.loads((ROOT.parents[1]/'.agents/plugins/marketplace.json').read_text())
        items=[p for p in market['plugins'] if p['name']==codex['name']]
        self.assertEqual(len(items),1)

    def test_cli_preview_makes_no_calls(self):
        r=subprocess.run([sys.executable,str(ROOT/'scripts/hackathon.py'),'run',
            '--plan',str(ROOT/'examples/recon-plan.json'),'--project','/tmp/not-used-project',
            '--state','/tmp/not-used-session'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['model_calls'],0)


if __name__=='__main__':unittest.main()
