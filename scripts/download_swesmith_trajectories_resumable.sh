#!/usr/bin/env bash
set -euo pipefail

DATASET_ID="${DATASET_ID:-SWE-bench/SWE-smith-trajectories}"
PROJECT_ROOT="${PROJECT_ROOT:-/nfs-data/sdd/tydong/projects/adacode-agent}"
OUT_DIR="${OUT_DIR:-$PROJECT_ROOT/data/open/SWE-smith-trajectories}"
HF_HOME="${HF_HOME:-$PROJECT_ROOT/.cache/huggingface}"
HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
MAX_WORKERS="${MAX_WORKERS:-8}"
RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-30}"
HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-120}"
HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-600}"

export DATASET_ID OUT_DIR MAX_WORKERS HF_HOME HF_ENDPOINT
export HF_HUB_ETAG_TIMEOUT HF_HUB_DOWNLOAD_TIMEOUT
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}"

mkdir -p "$OUT_DIR" "$HF_HOME"

echo "Dataset: $DATASET_ID"
echo "Output:  $OUT_DIR"
echo "HF_HOME: $HF_HOME"
echo "HF_ENDPOINT: $HF_ENDPOINT"
echo "HF_HUB_ETAG_TIMEOUT: $HF_HUB_ETAG_TIMEOUT"
echo "HF_HUB_DOWNLOAD_TIMEOUT: $HF_HUB_DOWNLOAD_TIMEOUT"
echo "http_proxy: ${http_proxy:-${HTTP_PROXY:-}}"
echo "https_proxy: ${https_proxy:-${HTTPS_PROXY:-}}"

python - <<'PY'
import importlib.util
import sys

missing = [name for name in ["huggingface_hub", "datasets"] if importlib.util.find_spec(name) is None]
if missing:
    print("Missing dependencies:", ", ".join(missing))
    print("Install with: pip install -U huggingface_hub datasets hf_transfer")
    sys.exit(1)
PY

if [ -z "${SKIP_DNS_CHECK:-}" ] && [ -z "${http_proxy:-${HTTP_PROXY:-}}" ] && [ -z "${https_proxy:-${HTTPS_PROXY:-}}" ]; then
python - <<'PY'
import os
import socket
from urllib.parse import urlparse

endpoint = os.environ["HF_ENDPOINT"]
host = urlparse(endpoint).hostname
try:
    socket.getaddrinfo(host, 443)
except socket.gaierror as exc:
    raise SystemExit(
        f"Cannot resolve {host}: {exc}\n"
        "This is a DNS/network issue. Try setting a reachable mirror, for example:\n"
        "  HF_ENDPOINT=https://hf-mirror.com bash scripts/download_swesmith_trajectories_resumable.sh\n"
        "or configure the server proxy/DNS first."
    )
print(f"DNS check passed for {host}")
PY
else
  echo "Skipping direct DNS check because proxy is configured or SKIP_DNS_CHECK is set."
fi

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
