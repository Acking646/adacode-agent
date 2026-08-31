#!/usr/bin/env bash
set -euo pipefail

DATASET_ID="${DATASET_ID:-SWE-bench/SWE-smith-trajectories}"
PROJECT_ROOT="${PROJECT_ROOT:-/nfs-data/sdd/tydong/projects/adacode-agent}"
OUT_DIR="${OUT_DIR:-$PROJECT_ROOT/data/open/SWE-smith-trajectories}"
HF_HOME="${HF_HOME:-$PROJECT_ROOT/.cache/huggingface}"
MAX_WORKERS="${MAX_WORKERS:-8}"
RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-30}"

export DATASET_ID OUT_DIR MAX_WORKERS HF_HOME
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}"

mkdir -p "$OUT_DIR" "$HF_HOME"

echo "Dataset: $DATASET_ID"
echo "Output:  $OUT_DIR"
echo "HF_HOME: $HF_HOME"

python - <<'PY'
import importlib.util
import sys

missing = [name for name in ["huggingface_hub", "datasets"] if importlib.util.find_spec(name) is None]
if missing:
    print("Missing dependencies:", ", ".join(missing))
    print("Install with: pip install -U huggingface_hub datasets hf_transfer")
    sys.exit(1)
PY

attempt=1
while [ "$attempt" -le "$RETRIES" ]; do
  echo "Download attempt $attempt/$RETRIES"
  if python - <<'PY'
import os
from huggingface_hub import snapshot_download

dataset_id = os.environ["DATASET_ID"]
out_dir = os.environ["OUT_DIR"]
max_workers = int(os.environ["MAX_WORKERS"])

snapshot_download(
    repo_id=dataset_id,
    repo_type="dataset",
    local_dir=out_dir,
    local_dir_use_symlinks=False,
    resume_download=True,
    max_workers=max_workers,
)
print("snapshot_download finished")
PY
  then
    break
  fi
  echo "Download failed; sleeping ${SLEEP_SECONDS}s before retry..."
  sleep "$SLEEP_SECONDS"
  attempt=$((attempt + 1))
done

if [ "$attempt" -gt "$RETRIES" ]; then
  echo "Download failed after $RETRIES attempts."
  exit 1
fi

echo "Writing dataset split summary..."
python - <<'PY'
import json
import os
from pathlib import Path
from datasets import get_dataset_config_names, get_dataset_split_names

dataset_id = os.environ["DATASET_ID"]
out_dir = Path(os.environ["OUT_DIR"])
summary = {"dataset_id": dataset_id, "configs": {}}

configs = get_dataset_config_names(dataset_id)
for cfg in configs:
    try:
        summary["configs"][cfg] = get_dataset_split_names(dataset_id, cfg)
    except Exception as exc:
        summary["configs"][cfg] = [f"ERROR: {exc}"]

(out_dir / "split_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
PY

echo "Done."
echo "Files are in: $OUT_DIR"
