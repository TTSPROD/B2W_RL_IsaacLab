import importlib.util
from pathlib import Path
import unittest
AVAILABLE = importlib.util.find_spec("torch") is not None
if AVAILABLE:
    import torch
    spec = importlib.util.spec_from_file_location("yaw_sampling", Path(__file__).resolve().parents[1] / "scripts/yaw_command_sampling.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)


@unittest.skipUnless(AVAILABLE, "requires project torch runtime")
class YawSamplingTests(unittest.TestCase):
    def test_zero_fraction_preserves_commands_masks_and_rng(self):
        c = torch.randn(20, 3)
        h = torch.ones(20, dtype=torch.bool)
        standing = torch.arange(20) % 5 == 0
        original = c.clone()
        rng = torch.Generator().manual_seed(42)
        before = rng.get_state().clone()
        global_before = torch.get_rng_state().clone()
        m.apply_yaw_mix(c, h, standing, torch.arange(20), 0., rng)
        self.assertTrue(torch.equal(c, original))
        self.assertTrue(h.all())
        self.assertTrue(torch.equal(before, rng.get_state()))
        self.assertTrue(torch.equal(global_before, torch.get_rng_state()))

    def test_full_fraction_preserves_standing_and_unselected_ids(self):
        c = torch.ones(100, 3)
        h = torch.ones(100, dtype=torch.bool)
        standing = torch.arange(100) % 2 == 0
        m.apply_yaw_mix(c, h, standing, list(range(50)), 1., torch.Generator().manual_seed(1))
        selected = (torch.arange(100) < 50) & ~standing
        self.assertTrue((c[~selected] == 1).all())
        self.assertTrue(h[~selected].all())
        self.assertTrue((c[selected, :2] == 0).all())
        self.assertTrue((~h[selected]).all())
        self.assertTrue(((c[selected, 2].abs() >= .2) & (c[selected, 2].abs() <= .5)).all())
        self.assertTrue((c[selected, 2] > 0).any() and (c[selected, 2] < 0).any())

    def test_distribution_and_independent_rng(self):
        n = 100000
        c = torch.ones(n, 3)
        h = torch.ones(n, dtype=torch.bool)
        standing = torch.arange(n) % 50 == 0
        before = torch.get_rng_state().clone()
        m.apply_yaw_mix(c, h, standing, torch.arange(n), .25, torch.Generator().manual_seed(12))
        rate = float((~h).sum()) / int((~standing).sum())
        self.assertAlmostEqual(rate, .25, delta=.006)
        self.assertAlmostEqual(float((c[~h, 2] > 0).float().mean()), .5, delta=.02)
        self.assertTrue(torch.equal(before, torch.get_rng_state()))
        with self.assertRaises(ValueError):
            m.apply_yaw_mix(c, h, standing, [], float("nan"), torch.Generator())


if __name__ == "__main__":
    unittest.main()
