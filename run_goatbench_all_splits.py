#!/usr/bin/env python3
"""Run GOATBench evaluation for every episode split.

The original evaluator uses --split N to select one episode per scene:
    scene_data["episodes"] = scene_data["episodes"][split - 1 : split]

GOATBench val_unseen has 10 episodes per scene, so splits 1..10 cover all
episodes once.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run run_goatbench_evaluation.py for split 1..10."
    )
    parser.add_argument(
        "-cf",
        "--cfg_file",
        default="cfg/eval_goatbench.yaml",
        help="Evaluation config path.",
    )
    parser.add_argument(
        "--start_ratio",
        type=float,
        default=0.0,
        help="Forwarded to run_goatbench_evaluation.py.",
    )
    parser.add_argument(
        "--end_ratio",
        type=float,
        default=1.0,
        help="Forwarded to run_goatbench_evaluation.py.",
    )
    parser.add_argument(
        "--first_split",
        type=int,
        default=1,
        help="First split to run, inclusive.",
    )
    parser.add_argument(
        "--last_split",
        type=int,
        default=10,
        help="Last split to run, inclusive.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue with later splits if one split fails.",
    )
    args = parser.parse_args()

    if args.first_split < 1 or args.last_split < args.first_split:
        parser.error("Require 1 <= first_split <= last_split")

    eval_script = Path(__file__).with_name("run_goatbench_evaluation.py")
    if not eval_script.exists():
        raise FileNotFoundError(f"Cannot find {eval_script}")

    failed = []
    for split in range(args.first_split, args.last_split + 1):
        cmd = [
            sys.executable,
            str(eval_script),
            "-cf",
            args.cfg_file,
            "--start_ratio",
            str(args.start_ratio),
            "--end_ratio",
            str(args.end_ratio),
            "--split",
            str(split),
        ]
        print("=" * 80, flush=True)
        print(f"Running GOATBench split {split}/{args.last_split}", flush=True)
        print("Command:", " ".join(cmd), flush=True)
        print("=" * 80, flush=True)

        result = subprocess.run(cmd)
        if result.returncode != 0:
            failed.append((split, result.returncode))
            print(
                f"Split {split} failed with exit code {result.returncode}.",
                file=sys.stderr,
                flush=True,
            )
            if not args.keep_going:
                break

    if failed:
        print("Failed splits:", failed, file=sys.stderr)
        return failed[0][1]

    print("All requested GOATBench splits finished.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
