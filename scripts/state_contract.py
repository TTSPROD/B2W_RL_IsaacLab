"""Exact checkpoint/optimizer state comparison shared by historical recipes."""


def assert_exact_state(actual, expected, path="state"):
    import torch

    if isinstance(expected, torch.Tensor):
        if not isinstance(actual, torch.Tensor) or not torch.equal(actual.detach().cpu(), expected.cpu()):
            raise ValueError(f"Restored tensor differs: {path}")
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError(f"Restored keys differ: {path}")
        for key in expected:
            assert_exact_state(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(actual) != len(expected):
            raise ValueError(f"Restored sequence differs: {path}")
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_exact_state(a, e, f"{path}[{i}]")
    elif actual != expected:
        raise ValueError(f"Restored value differs: {path}")
