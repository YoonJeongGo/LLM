import argparse
from pathlib import Path
from edu_tutor.models.evaluate import run_evaluation

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--adapter")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_evaluation(root, root / args.output, args.adapter)
