#!/usr/bin/env python3
"""
Minimal OpenAI-compatible Qwen endpoint probe.

Engine-only rule:
- Does not download model weights.
- Does not store API keys.
- Does not send company data unless the caller explicitly puts it in the prompt.

Environment variables:
- QWEN_API_BASE: e.g. http://127.0.0.1:8000/v1
- QWEN_API_KEY: optional
- QWEN_MODEL: model name exposed by the server
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: pip install requests") from exc


def _parse_extra_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--extra-json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("--extra-json must decode to a JSON object")
    return data


def _build_url(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def call_chat_completion(
    *,
    api_base: str,
    model: str,
    prompt: str,
    system: str | None,
    api_key: str | None,
    timeout: float,
    max_tokens: int,
    temperature: float,
    extra: dict[str, Any],
) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    payload.update(extra)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    started = time.perf_counter()
    response = requests.post(_build_url(api_base), headers=headers, json=payload, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    try:
        body = response.json()
    except ValueError:
        body = {"raw_text": response.text[:4000]}

    return {
        "ok": response.ok,
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "api_base": api_base,
        "model": model,
        "response": body,
    }


def _content_preview(body: dict[str, Any]) -> str | None:
    try:
        choices = body.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content[:1000]
        return json.dumps(content, ensure_ascii=False)[:1000]
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe an OpenAI-compatible Qwen endpoint.")
    parser.add_argument("--api-base", default=os.getenv("QWEN_API_BASE", "http://127.0.0.1:8000/v1"))
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", "qwen"))
    parser.add_argument("--api-key", default=os.getenv("QWEN_API_KEY"))
    parser.add_argument("--prompt", default="Say OK only.")
    parser.add_argument("--system", default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--extra-json",
        default=None,
        help="JSON object merged into the request payload, e.g. '{\"reasoning_effort\":\"high\"}'.",
    )
    parser.add_argument("--raw", action="store_true", help="Print full raw response JSON.")
    args = parser.parse_args()

    result = call_chat_completion(
        api_base=args.api_base,
        model=args.model,
        prompt=args.prompt,
        system=args.system,
        api_key=args.api_key,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        extra=_parse_extra_json(args.extra_json),
    )

    response_body = result.get("response") if isinstance(result.get("response"), dict) else {}
    compact = {
        "ok": result["ok"],
        "status_code": result["status_code"],
        "elapsed_ms": result["elapsed_ms"],
        "api_base": result["api_base"],
        "model": result["model"],
        "content_preview": _content_preview(response_body),
        "usage": response_body.get("usage") if isinstance(response_body, dict) else None,
    }

    print(json.dumps(result if args.raw else compact, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
