#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${DATA_ROOT:-./data/open}"
mkdir -p "$DATA_ROOT"
export DATA_ROOT

python - <<'PY'
import os
from pathlib import Path
from datasets import load_dataset

root = Path(os.environ["DATA_ROOT"])
root.mkdir(parents=True, exist_ok=True)

datasets = {
    "swe_bench_verified": ("SWE-bench/SWE-bench_Verified", "test"),
    "swe_bench_lite": ("SWE-bench/SWE-bench_Lite", "test"),
    "swe_smith_py_sample": ("SWE-bench/SWE-smith-py", "train[:200]"),
    "swe_smith_traj_sample": ("SWE-bench/SWE-smith-trajectories", "xml[:200]"),
}

for name, (repo, split) in datasets.items():
    print(f"Loading {repo} split={split}")
    ds = load_dataset(repo, split=split)
    out = root / f"{name}.jsonl"
    ds.to_json(str(out), force_ascii=False)
    print(f"Wrote {len(ds)} rows -> {out}")
PY
