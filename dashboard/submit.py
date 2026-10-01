"""Command-line submission for local dashboard recipes."""
import argparse
import json
from client import submit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("kind", choices=("tests", "evaluate", "compare", "train"))
parser.add_argument("--policy", default="24650")
parser.add_argument("--updates", type=int, default=100)
parser.add_argument("--num-envs", type=int, default=4096)
args = parser.parse_args()
print(json.dumps(submit({"kind": args.kind, "policy": args.policy,
                        "updates": args.updates, "num_envs": args.num_envs}), indent=2))
