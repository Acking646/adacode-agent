from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA SFT for Qwen3-0.6B context manager.")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B")
    parser.add_argument("--data", default="data/sft/context_manager_sft.jsonl")
    parser.add_argument("--output", default="checkpoints/qwen3-0.6b-context-manager")
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    try:
        from datasets import load_dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    except ImportError as exc:
        raise SystemExit(
            "Missing training dependencies. Install optional packages first:\n"
            "pip install transformers datasets peft accelerate torch"
        ) from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dataset = load_dataset("json", data_files=str(Path(args.data)), split="train")

    def format_sample(sample):
        prompt = (
            "You are a context manager for a coding agent. Return only valid JSON.\n"
            f"Instruction: {sample['instruction']}\n"
            f"Input: {sample['input']}\n"
            "Output:"
        )
        answer = str(sample["output"])
        text = prompt + answer + tokenizer.eos_token
        tokenized = tokenizer(text, truncation=True, max_length=args.max_length, padding=False)
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized

    tokenized = dataset.map(format_sample, remove_columns=dataset.column_names)
    model = AutoModelForCausalLM.from_pretrained(args.model, trust_remote_code=True)
    lora = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM")
    model = get_peft_model(model, lora)

    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        logging_steps=5,
        save_strategy="epoch",
        report_to=[],
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=tokenized)
    trainer.train()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"Saved context manager adapter to {args.output}")


if __name__ == "__main__":
    main()

