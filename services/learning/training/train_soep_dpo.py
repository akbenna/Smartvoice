#!/usr/bin/env python3
"""
SOEP-stijl via DPO (Direct Preference Optimization)
===================================================

Traint het SOEP-LLM om de door de arts goedgekeurde SOEP te prefereren boven de
oorspronkelijk gegenereerde. Voorkeursparen komen uit
`tools/build_training_data.py` (--only dpo): {prompt, chosen, rejected}.

Gebruikt LoRA (PEFT) zodat het op één GPU past en de basisgewichten intact
blijven (eenvoudige rollback: verwijder de adapter).

Vereisten (GPU-machine):
    pip install "trl>=0.9" "transformers>=4.40" peft datasets accelerate torch

Gebruik:
    python -m services.learning.training.train_soep_dpo \
        --data /data/training/soep_dpo.jsonl \
        --base-model meta-llama/Llama-3.1-8B-Instruct \
        --output-dir /models/soep_dpo_adapter

Evalueer het resultaat tegen de meetlat (SOEP edit-distance) vóór productie.
Draait NIET in de standaard SmartVoice-omgeving.
"""

from __future__ import annotations

import argparse
import json
import sys


def _load_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SOEP DPO-training")
    ap.add_argument("--data", required=True, help="JSONL met {prompt,chosen,rejected}")
    ap.add_argument("--base-model", default="meta-llama/Llama-3.1-8B-Instruct")
    ap.add_argument("--output-dir", default="/models/soep_dpo_adapter")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--beta", type=float, default=0.1, help="DPO beta (KL-sterkte)")
    ap.add_argument("--min-examples", type=int, default=200)
    args = ap.parse_args(argv)

    data = _load_jsonl(args.data)
    if len(data) < args.min_examples:
        print(
            f"Te weinig voorkeursparen ({len(data)} < {args.min_examples}). "
            "Verzamel meer artscorrecties voordat je traint.",
            file=sys.stderr,
        )
        return 2

    try:
        from datasets import Dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import DPOConfig, DPOTrainer
    except Exception as e:
        print(f"Trainingsdependencies ontbreken: {e}\n"
              "Installeer: pip install trl transformers peft datasets accelerate torch",
              file=sys.stderr)
        return 1

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(args.base_model)

    peft_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    ds = Dataset.from_list(data)

    dpo_config = DPOConfig(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        beta=args.beta,
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        report_to=[],
    )

    trainer = DPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=ds,
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    print(f"Klaar. LoRA-adapter opgeslagen in {args.output_dir}")
    print("Converteer naar GGUF/Ollama en evalueer tegen de SOEP edit-distance vóór productie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
