"""Reject a relabelled checkpoint or reference with changed provenance."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluation_policy import ROOT, policy_id, reference_identity, validate_export


class EvaluationIdentityTests(unittest.TestCase):
    def test_reference_is_not_a_checkpoint_iteration(self):
        identity = reference_identity()
        self.assertIsNone(identity['checkpoint_iteration'])
        self.assertFalse(identity['training_checkpoint_export_parity'])
        self.assertEqual(validate_export('rl_sar',ROOT/identity['source_path'],identity),identity)
        with self.assertRaises(ValueError):
            validate_export(23999,ROOT/identity['source_path'],identity)

    def test_changed_reference_hash_or_origin_is_rejected(self):
        identity = reference_identity()
        for field in ('export_sha256','commit','source_path','git_blob_sha1'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_export('rl_sar',ROOT/identity['source_path'],{**identity,field:'changed'})

    def test_existing_checkpoint_identity_and_forbidden_policy(self):
        folder = ROOT/'policies/local/recovery_23999/export'
        validate_export(23999,folder/'policy.pt',json.loads((folder/'manifest.json').read_text()))
        self.assertEqual(policy_id('23999'),23999)
        self.assertEqual(policy_id('rl_sar'),'rl_sar')
        with self.assertRaises(ValueError):
            policy_id('10000')


if __name__ == '__main__':
    unittest.main()
