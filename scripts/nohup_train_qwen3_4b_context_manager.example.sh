#!/usr/bin/env bash
set -euo pipefail

nohup bash -c '
CUDA_VISIBLE_DEVICES=0,1 \
MODEL_PATH=/nfs-data/YOUR_USER/models/Qwen3-4B \
DATA_PATH=/nfs-data/YOUR_USER/projects/adacode-agent/data/sft/context_manager_sft.jsonl \
OUTPUT_DIR=/nfs-data/YOUR_USER/models/Qwen3-4B-ContextManager-LoRA \
NPROC=2 \
EPOCHS=3 \
MAX_LENGTH=4096 \
PER_DEVICE_TRAIN_BATCH_SIZE=1 \
GRADIENT_ACCUMULATION_STEPS=8 \
bash scripts/train_qwen3_4b_context_manager.sh
' > train_qwen3_4b_context_manager.log 2>&1 &

echo "Training started. Log: train_qwen3_4b_context_manager.log"

