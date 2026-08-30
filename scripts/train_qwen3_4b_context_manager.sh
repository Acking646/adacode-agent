#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${MODEL_PATH:-./models/Qwen3-4B}"
DATA_PATH="${DATA_PATH:-./data/sft/context_manager_sft.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-./checkpoints/qwen3-4b-context-manager}"
GPUS="${GPUS:-0,1}"
NPROC="${NPROC:-2}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-$GPUS}"

torchrun --nproc_per_node="$NPROC" -m training.train_manager \
  --model_name_or_path "$MODEL_PATH" \
  --data_path "$DATA_PATH" \
  --output_dir "$OUTPUT_DIR" \
  --max-length "${MAX_LENGTH:-4096}" \
  --epochs "${EPOCHS:-3}" \
  --lr "${LR:-1e-4}" \
  --per-device-train-batch-size "${PER_DEVICE_TRAIN_BATCH_SIZE:-1}" \
  --gradient-accumulation-steps "${GRADIENT_ACCUMULATION_STEPS:-8}" \
  --logging-steps "${LOGGING_STEPS:-5}" \
  --save-steps "${SAVE_STEPS:-100}" \
  --lora-r "${LORA_R:-16}" \
  --lora-alpha "${LORA_ALPHA:-32}" \
  --lora-dropout "${LORA_DROPOUT:-0.05}" \
  --bf16 \
  --gradient-checkpointing

