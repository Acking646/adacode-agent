#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/nfs-data/sdd/tydong/projects/adacode-agent}"
MODEL_PATH="${MODEL_PATH:-$PROJECT_ROOT/models/Qwen3-4B}"
ADAPTER_PATH="${ADAPTER_PATH:-$PROJECT_ROOT/checkpoints/qwen3-4b-context-manager}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

export CUDA_VISIBLE_DEVICES

vllm serve "$MODEL_PATH" \
  --enable-lora \
  --lora-modules "cm=$ADAPTER_PATH" \
  --served-model-name qwen3-4b-cm-sft \
  --host "$HOST" \
  --port "$PORT"
