import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import train_b2w_desktop
from b2w_rough_runtime import ANCHOR_SHA256


def app_args(parser):
    parser.add_argument('--device',default='cuda:0')


class UnifiedU1Tests(unittest.TestCase):
    def arguments(self):
        return ['--unified_u1','--rough_transfer','--rough_tilt_termination',
                '--reference_init','anchor.pt','--num_envs','64','--max_iterations','2',
                '--critic_warmup_updates','1','--rough_stage','0','--pure_yaw_fraction','.25',
                '--reference_update_probe']

    def parse(self,args,parent=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);anchor=root/'anchor.pt';anchor.touch()
            resume=root/'model_1.pt'
            if parent is not None:
                resume.touch();(root/'manifest.json').write_text(json.dumps(parent),encoding='utf-8')
                args=[str(resume) if value=='resume.pt' else str(anchor) if value=='anchor.pt' else value for value in args]
            else:
                args=[str(anchor) if value=='anchor.pt' else value for value in args]
            with patch.object(sys,'argv',['train_b2w_desktop.py',*args]), \
                 patch.object(train_b2w_desktop,'PROJECT_ROOT',root), \
                 patch.object(train_b2w_desktop,'sha256',return_value=ANCHOR_SHA256), \
                 contextlib.redirect_stderr(io.StringIO()):
                return train_b2w_desktop.parse_args(SimpleNamespace(add_app_launcher_args=app_args))

    def test_u1_requires_exact_blind_rough_recipe(self):
        parsed=self.parse(self.arguments());self.assertTrue(parsed.unified_u1)
        for remove in ('--rough_transfer','--rough_tilt_termination'):
            values=self.arguments();values.remove(remove)
            with self.assertRaises(SystemExit):self.parse(values)
        for extra in ('--rough_route_commands','--rough_precision_tracking','--rough_wheel_corridor','--rough_wide_corridor'):
            with self.assertRaises(SystemExit):self.parse(self.arguments()+[extra])

    def test_resume_cannot_enter_or_leave_u1(self):
        base=dict(reference_transfer={},rough_transfer=True,num_envs=64,ending_runner_iteration=1,
                  rough_stage=0,rough_tilt_termination=True,rough_route_commands=False,
                  rough_precision_tracking=False,rough_wheel_corridor=False,rough_wide_corridor=False)
        args=self.arguments()+['--resume','resume.pt']
        with self.assertRaises(SystemExit):self.parse(args,dict(base,unified_u1=False))
        parsed=self.parse(args,dict(base,unified_u1=True));self.assertTrue(parsed.unified_u1)

    def test_u11_requires_u1_and_is_resume_invariant(self):
        with self.assertRaises(SystemExit):
            self.parse([value for value in self.arguments() if value!='--unified_u1']+['--unified_u11'])
        parsed=self.parse(self.arguments()+['--unified_u11']);self.assertTrue(parsed.unified_u11)
        base=dict(reference_transfer={},rough_transfer=True,num_envs=64,ending_runner_iteration=1,
                  rough_stage=0,rough_tilt_termination=True,rough_route_commands=False,
                  rough_precision_tracking=False,rough_wheel_corridor=False,rough_wide_corridor=False,
                  unified_u1=True)
        args=self.arguments()+['--unified_u11','--resume','resume.pt']
        with self.assertRaises(SystemExit):self.parse(args,dict(base,unified_u11=False))
        self.assertTrue(self.parse(args,dict(base,unified_u11=True)).unified_u11)

    def test_u12_requires_u11_and_is_resume_invariant(self):
        with self.assertRaises(SystemExit):self.parse(self.arguments()+['--unified_u12'])
        parsed=self.parse(self.arguments()+['--unified_u11','--unified_u12'])
        self.assertTrue(parsed.unified_u12)
        base=dict(reference_transfer={},rough_transfer=True,num_envs=64,ending_runner_iteration=1,
                  rough_stage=0,rough_tilt_termination=True,rough_route_commands=False,
                  rough_precision_tracking=False,rough_wheel_corridor=False,rough_wide_corridor=False,
                  unified_u1=True,unified_u11=True)
        args=self.arguments()+['--unified_u11','--unified_u12','--resume','resume.pt']
        with self.assertRaises(SystemExit):self.parse(args,dict(base,unified_u12=False))
        self.assertTrue(self.parse(args,dict(base,unified_u12=True)).unified_u12)


if __name__=='__main__':unittest.main()
