#!/usr/bin/env python3
"""
Local hidden-state/logit probe for Qwen-style causal language models.

Engine-only rule:
- Requires an existing local model directory.
- Uses local_files_only=True.
- Does not download weights or snapshots.
- Default output is a compact JSON summary, not a giant tensor dump.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _import_runtime() -> tuple[Any, Any, Any]:
    try:
        import numpy as np
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependencies. Install only in the local model/probe environment: "
            "pip install torch transformers numpy"
        ) from exc
    return np, torch, (AutoTokenizer, AutoModelForCausalLM)


def _require_local_model_path(model_path: str) -> Path:
    path = Path(model_path).expanduser().resolve()
    if not path.exists():
        raise SystemExit(
            f"Model path does not exist: {path}\n"
            "This probe intentionally does not download models. Put the model on disk first, then pass --model-path."
        )
    if not path.is_dir():
        raise SystemExit(f"Model path is not a directory: {path}")
    return path


def _top_tokens(logits: Any, tokenizer: Any, torch: Any, k: int = 10) -> list[dict[str, Any]]:
    probs = torch.softmax(logits, dim=-1)
    values, indices = torch.topk(probs, k=k)
    rows: list[dict[str, Any]] = []
    for prob, token_id in zip(values.tolist(), indices.tolist()):
        rows.append(
            {
                "token_id": int(token_id),
                "token": tokenizer.decode([int(token_id)]),
                "probability": float(prob),
            }
        )
    return rows


def run_probe(
    *,
    model_path: Path,
    prompt: str,
    max_new_tokens: int,
    dump_last_token_hidden: str | None,
    include_attentions: bool,
) -> dict[str, Any]:
    np, torch, hf = _import_runtime()
    AutoTokenizer, AutoModelForCausalLM = hf

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        trust_remote_code=True,
        local_files_only=True,
        output_hidden_states=True,
        output_attentions=include_attentions,
    )
    model.eval()

    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True, output_attentions=include_attentions)
        last_token_logits = outputs.logits[0, -1, :]
        generated_ids = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)

    hidden_states = list(outputs.hidden_states or [])
    hidden_summary = [
        {
            "layer_index": i,
            "shape": list(t.shape),
            "mean": float(t.mean().item()),
            "std": float(t.std().item()),
            "last_token_norm": float(torch.linalg.vector_norm(t[0, -1, :]).item()),
        }
        for i, t in enumerate(hidden_states)
    ]

    dump_path = None
    if dump_last_token_hidden:
        target = Path(dump_last_token_hidden).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"layer_{i:03d}": t[0, -1, :].detach().cpu().numpy() for i, t in enumerate(hidden_states)}
        np.savez_compressed(target, **arrays)
        dump_path = str(target)

    attention_shapes = None
    if include_attentions and outputs.attentions is not None:
        attention_shapes = [list(t.shape) for t in outputs.attentions]

    generated_text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)
    return {
        "model_path": str(model_path),
        "prompt_chars": len(prompt),
        "input_tokens": int(inputs["input_ids"].shape[-1]),
        "generated_text": generated_text,
        "top_next_tokens": _top_tokens(last_token_logits, tokenizer, torch, k=10),
        "hidden_layers": len(hidden_summary),
        "hidden_summary": hidden_summary,
        "attention_shapes": attention_shapes,
        "dump_last_token_hidden": dump_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local Qwen hidden states and next-token logits.")
    parser.add_argument("--model-path", required=True, help="Existing local model directory. No download is performed.")
    parser.add_argument("--prompt", default="2+2=")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument(
        "--dump-last-token-hidden",
        default=None,
        help="Optional .npz output path containing last-token hidden vectors for each layer.",
    )
    parser.add_argument(
        "--attentions",
        action="store_true",
        help="Also request attention tensors. This can be very large and slow.",
    )
    parser.add_argument("--out", default=None, help="Optional JSON output file path.")
    args = parser.parse_args()

    result = run_probe(
        model_path=_require_local_model_path(args.model_path),
        prompt=args.prompt,
        max_new_tokens=args.max_new_tokens,
        dump_last_token_hidden=args.dump_last_token_hidden,
        include_attentions=args.attentions,
    )

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
