"""Collision geometry invariants, independent of Isaac/Kit and policy reward."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from b2w_rough_terrain import build_tile, mesh_hash, geometry_fixtures, FAMILIES, NOISE


class RoughTerrainTests(unittest.TestCase):
    def test_all_registered_levels_have_horizontal_spawn(self):
        records = geometry_fixtures()
        self.assertEqual(len(records), 15)
        self.assertEqual({(r['family'], r['level']) for r in records},
                         {(f, level) for f in FAMILIES for level in range(3)})

    def test_noise_is_signed_quantized_and_reproducible(self):
        for level in range(3):
            a, _ = build_tile('random', level, 71)
            b, _ = build_tile('random', level, 71)
            c, _ = build_tile('random', level, 72)
            self.assertEqual(mesh_hash(a), mesh_hash(b))
            self.assertNotEqual(mesh_hash(a), mesh_hash(c))
            z = a.vertices[:, 2]
            self.assertAlmostEqual(z.min(), -NOISE[level])
            self.assertAlmostEqual(z.max(), NOISE[level])
            np.testing.assert_allclose(z/.005, np.rint(z/.005), atol=1e-10)

    def test_every_surface_triangle_faces_up_and_stays_inside_tile(self):
        for family in FAMILIES:
            mesh, _ = build_tile(family, 2, 72)
            self.assertTrue(np.isfinite(mesh.vertices).all())
            self.assertGreater(float(mesh.area_faces.min()), 0.)
            self.assertTrue((mesh.vertices[:, :2] >= 0).all())
            self.assertTrue((mesh.vertices[:, :2] <= 12.+1e-9).all())
            if family != 'blocks':
                self.assertTrue((mesh.face_normals[:, 2] > 0).all())

    def test_slope_labels_have_opposite_signed_grades(self):
        up, _ = build_tile('slope_up', 1, 72)
        down, _ = build_tile('slope_down', 1, 72)
        np.testing.assert_allclose(up.vertices[:, 2], -down.vertices[:, 2])
        self.assertGreater(up.vertices[up.vertices[:, 0] > 11, 2].mean(), 0)

    def test_unknown_geometry_rejected(self):
        for family, level, size in [('stairs',0,(12.,12.)), ('random',3,(12.,12.)), ('flat',0,(8.,8.))]:
            with self.assertRaises(ValueError):
                build_tile(family, level, 72, size)


if __name__ == '__main__':
    unittest.main()
