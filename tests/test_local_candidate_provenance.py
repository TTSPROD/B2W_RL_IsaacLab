import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_project import verify_local_candidate


class LocalCandidateProvenanceTests(unittest.TestCase):
    def fixture(self, directory):
        (directory/'export').mkdir()
        files={'model_123.pt':b'checkpoint','env.yaml':b'env','agent.yaml':b'agent','export/policy.pt':b'export'}
        manifest={'export_validation':{'status':'passed','checkpoint_iteration':123,
                    'checkpoint_sha256':hashlib.sha256(files['model_123.pt']).hexdigest(),
                    'export_sha256':hashlib.sha256(files['export/policy.pt']).hexdigest()}}
        files['export/manifest.json']=json.dumps(manifest).encode()
        for name,value in files.items(): (directory/name).write_bytes(value)
        (directory/'provenance.json').write_text(json.dumps({'checkpoint_iteration':123,
            'files_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in files.items()}}))

    def test_accepts_complete_provenance_and_rejects_changed_or_extra_weights(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder); self.fixture(d)
            self.assertEqual(len(verify_local_candidate(d)),2)
            (d/'other.pt').write_bytes(b'unknown')
            with self.assertRaisesRegex(ValueError,'Unregistered'): verify_local_candidate(d)
            (d/'other.pt').unlink()
            (d/'model_123.pt').write_bytes(b'mutated')
            with self.assertRaisesRegex(ValueError,'Changed'): verify_local_candidate(d)

    def test_rejects_parent_mismatch_even_with_valid_file_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder); self.fixture(d)
            p=d/'export/manifest.json'; m=json.loads(p.read_text())
            m['export_validation']['checkpoint_sha256']='0'*64; p.write_text(json.dumps(m))
            f=d/'provenance.json'; v=json.loads(f.read_text())
            v['files_sha256']['export/manifest.json']=hashlib.sha256(p.read_bytes()).hexdigest(); f.write_text(json.dumps(v))
            with self.assertRaisesRegex(ValueError,'parent mismatch'): verify_local_candidate(d)


if __name__=='__main__': unittest.main()
