#!/usr/bin/env bash
set -euo pipefail

DATASET_ID="${DATASET_ID:-SWE-bench/SWE-bench_Verified}"
PROJECT_ROOT="${PROJECT_ROOT:-/nfs-data/sdd/tydong/projects/adacode-agent}"
OUT_DIR="${OUT_DIR:-$PROJECT_ROOT/data/open/SWE-bench_Verified}"
HF_HOME="${HF_HOME:-$PROJECT_ROOT/.cache/huggingface}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-30}"
MAX_WORKERS="${MAX_WORKERS:-1}"
HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-120}"
HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-600}"

export DATASET_ID OUT_DIR HF_HOME HF_ENDPOINT MAX_WORKERS
export HF_HUB_ETAG_TIMEOUT HF_HUB_DOWNLOAD_TIMEOUT
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}"

mkdir -p "$OUT_DIR" "$HF_HOME"

echo "Dataset: $DATASET_ID"
echo "Output:  $OUT_DIR"
echo "HF_HOME: $HF_HOME"
echo "HF_ENDPOINT: $HF_ENDPOINT"
echo "http_proxy: ${http_proxy:-${HTTP_PROXY:-}}"
echo "https_proxy: ${https_proxy:-${HTTPS_PROXY:-}}"

python - <<'PY'
import importlib.util
import sys

missing = [name for name in ["huggingface_hub", "datasets"] if importlib.util.find_spec(name) is None]
if missing:
    print("Missing dependencies:", ", ".join(missing))
    print("Install with: pip install -U huggingface_hub datasets pyarrow")
    sys.exit(1)
PY

attempt=1
while [ "$attempt" -le "$RETRIES" ]; do
  echo "Download attempt $attempt/$RETRIES"
  if python - <<'PY'
import os
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id=os.environ["DATASET_ID"],
    repo_type="dataset",
    local_dir=os.environ["OUT_DIR"],
    max_workers=int(os.environ["MAX_WORKERS"]),
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

python - <<'PY'
import json
import os
from pathlib import Path
from datasets import load_dataset

dataset_id = os.environ["DATASET_ID"]
out_dir = Path(os.environ["OUT_DIR"])
ds = load_dataset(dataset_id, split="test")
summary = {
    "dataset_id": dataset_id,
    "split": "test",
    "rows": len(ds),
    "columns": ds.column_names,
    "first_instance_id": ds[0].get("instance_id") if len(ds) else None,
}
(out_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
ds.to_json(str(out_dir / "test.jsonl"), force_ascii=False)
print(json.dumps(summary, indent=2))
PY

echo "Done."
echo "Files are in: $OUT_DIR"

