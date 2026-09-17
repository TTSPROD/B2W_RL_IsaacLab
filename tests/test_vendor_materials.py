import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('vendor_materials', Path(__file__).resolve().parents[1] / 'scripts/vendor_materials.py')
vendor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor)


class VendorTests(unittest.TestCase):
    def test_source_escape_rejected(self):
        for name in ('../../outside', '/absolute', 'a/b', 'a\\b', '..', 'C:'):
            with self.assertRaises(ValueError):
                vendor.safe_target(name, 'file.bin')

    def test_path_escape_rejected(self):
        for path in ('../outside', '/absolute', 'a/../../outside', 'C:/outside', 'a\\..\\outside'):
            with self.assertRaises(ValueError):
                vendor.safe_target('robot_lab', path)

    def test_git_blob_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'file'
            path.write_bytes(b'hello\n')
            size, blob, sha256 = vendor.hashes(path)
            self.assertEqual(size, 6)
            self.assertEqual(blob, 'ce013625030ba8dba906f756967f9e9ca394464a')
            self.assertEqual(sha256, '5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03')


if __name__ == '__main__':
    unittest.main()
