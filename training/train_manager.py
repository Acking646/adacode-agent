from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA SFT for Qwen3-4B context manager.")
    parser.add_argument("--model", "--model_name_or_path", dest="model", default="models/Qwen3-4B")
    parser.add_argument("--data", "--data_path", dest="data", default="data/sft/context_manager_sft.jsonl")
    parser.add_argument("--eval-data", "--eval_data_path", dest="eval_data", default=None)
    parser.add_argument("--output", "--output_dir", dest="output", default="checkpoints/qwen3-4b-context-manager")
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--logging-steps", type=int, default=5)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--gradient-checkpointing", action="store_true")
    args = parser.parse_args()

    try:
        from datasets import load_dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
        import torch
    except ImportError as exc:
        raise SystemExit(
            "Missing training dependencies. Install optional packages first:\n"
            "pip install transformers datasets peft accelerate torch\n"
            f"Original import error: {type(exc).__name__}: {exc}"
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_dataset = load_dataset("json", data_files=str(Path(args.data)), split="train")
    eval_dataset = None
    if args.eval_data:
        eval_dataset = load_dataset("json", data_files=str(Path(args.eval_data)), split="train")

    def format_sample(sample):
        input_text = json.dumps(sample["input"], ensure_ascii=False, indent=2)
        output_text = json.dumps(sample["output"], ensure_ascii=False, indent=2)
        prompt = (
            "You are a context manager for a coding agent. Return only valid JSON.\n"
            f"Instruction: {sample['instruction']}\n"
            f"Input:\n{input_text}\n"
            "Output:"
        )
        target = output_text + tokenizer.eos_token
        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        target_ids = tokenizer(target, add_special_tokens=False)["input_ids"]
        if len(target_ids) >= args.max_length:
            input_ids = target_ids[: args.max_length]
            labels = input_ids.copy()
        else:
            prompt_budget = args.max_length - len(target_ids)
            prompt_ids = prompt_ids[-prompt_budget:]
            input_ids = prompt_ids + target_ids
            labels = [-100] * len(prompt_ids) + target_ids
        return {"input_ids": input_ids, "attention_mask": [1] * len(input_ids), "labels": labels}

    def collate(features):
        max_len = max(len(item["input_ids"]) for item in features)
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for item in features:
            pad = max_len - len(item["input_ids"])
            batch["input_ids"].append(item["input_ids"] + [tokenizer.pad_token_id] * pad)
            batch["attention_mask"].append(item["attention_mask"] + [0] * pad)
            batch["labels"].append(item["labels"] + [-100] * pad)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}

    tokenized_train = train_dataset.map(format_sample, remove_columns=train_dataset.column_names)
    tokenized_eval = None
    if eval_dataset is not None:
        tokenized_eval = eval_dataset.map(format_sample, remove_columns=eval_dataset.column_names)
    model = AutoModelForCausalLM.from_pretrained(args.model, trust_remote_code=True, torch_dtype="auto")
    if args.gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False
    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    training_kwargs = {
        "output_dir": args.output,
        "num_train_epochs": args.epochs,
        "learning_rate": args.lr,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "logging_steps": args.logging_steps,
        "save_steps": args.save_steps,
        "save_strategy": "steps",
        "warmup_ratio": args.warmup_ratio,
        "weight_decay": args.weight_decay,
        "bf16": args.bf16,
        "fp16": args.fp16,
        "gradient_checkpointing": args.gradient_checkpointing,
        "remove_unused_columns": False,
        "report_to": [],
    }
    if tokenized_eval is not None:
        signature = inspect.signature(TrainingArguments.__init__).parameters
        if "eval_strategy" in signature:
            training_kwargs["eval_strategy"] = "steps"
        else:
            training_kwargs["evaluation_strategy"] = "steps"
        training_kwargs["eval_steps"] = args.logging_steps
    training_args = TrainingArguments(**training_kwargs)
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_eval,
        data_collator=collate,
    )
    trainer.train()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"Saved context manager adapter to {args.output}")


if __name__ == "__main__":
    main()
