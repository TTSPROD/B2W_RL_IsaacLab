"""Rough launcher refuses wrong parents, unbounded runs and reward overrides."""
import contextlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_b2w
from b2w_rough_runtime import ANCHOR_SHA256


def app_args(parser):
    parser.add_argument('--device', default='cuda:0')


class RoughR0Tests(unittest.TestCase):
    def parse(self, arguments, digest=ANCHOR_SHA256):
        with patch.object(sys, 'argv', ['train_b2w.py', *arguments]), \
             patch.object(Path, 'is_file', return_value=True), \
             patch.object(train_b2w, 'sha256', return_value=digest), \
             contextlib.redirect_stderr(io.StringIO()):
            return train_b2w.parse_args(SimpleNamespace(add_app_launcher_args=app_args))

    def rough(self):
        return ['--rough_r0', '--reference_init', 'fake-anchor.pt', '--num_envs', '64',
                '--max_iterations', '2', '--critic_warmup_updates', '1',
                '--pure_yaw_fraction', '.25', '--reference_update_probe']

    def test_flat_defaults_remain_available(self):
        args = self.parse([])
        self.assertFalse(args.rough_r0)
        self.assertEqual(args.max_iterations, 5000)
        self.assertIsNone(args.reference_init)

    def test_bounded_actor_transfer_is_accepted(self):
        args = self.parse(self.rough())
        self.assertTrue(args.rough_r0)
        self.assertEqual(args.reference_drift_limit, .25)

    def test_wrong_anchor_and_weakened_guards_rejected(self):
        with self.assertRaises(SystemExit):
            self.parse(self.rough(), digest='0'*64)
        for override in [['--max_iterations','51'], ['--num_envs','8192'],
                         ['--reference_drift_limit','.5'], ['--pure_yaw_fraction','0'],
                         ['--undesired_contact_weight','-3'], ['--flat_upright_resets']]:
            with self.subTest(override=override), self.assertRaises(SystemExit):
                self.parse(self.rough()+override)


if __name__ == '__main__':
    unittest.main()
