"""Prevent candidate/parent execution differences in the frozen screen loop."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CandidateEvaluatorTests(unittest.TestCase):
    def test_simulation_and_safety_loop_is_identical(self):
        nodes = []
        for name in ("eval_operating57_isaac.py", "eval_candidate_operating57_isaac.py"):
            tree = ast.parse((ROOT / "scripts" / name).read_text(encoding="utf-8"))
            matches = [node for node in ast.walk(tree) if isinstance(node, ast.With)
                       and "torch.inference_mode()" in ast.unparse(node.items[0].context_expr)]
            self.assertEqual(len(matches), 1)
            nodes.append(ast.dump(matches[0], include_attributes=False))
        self.assertEqual(nodes[0], nodes[1])

    def test_observation_assembly_is_identical(self):
        nodes = []
        for name in ("eval_operating57_isaac.py", "eval_candidate_operating57_isaac.py"):
            tree = ast.parse((ROOT / "scripts" / name).read_text(encoding="utf-8"))
            nodes.append([ast.dump(node, include_attributes=False) for node in ast.walk(tree)
                          if isinstance(node, ast.FunctionDef) and node.name == "observation"])
        self.assertTrue(nodes[0])
        self.assertEqual(nodes[0], nodes[1])
