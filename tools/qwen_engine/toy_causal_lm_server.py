#!/usr/bin/env python3
"""
Toy OpenAI-compatible causal LM server.

This is a deliberately primitive engine for Human Codex/Qwen adapter tests.
It does not download weights, call external APIs, or store secrets. It only
proves that the client can talk to an OpenAI-compatible endpoint and survive
very basic model-like behavior.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import uuid
from collections import Counter, defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_CORPUS = """
AI predicts the next token. A model reads context and chooses a likely next symbol.
A client sends JSON to a server. The server returns text, streaming chunks, or a tool call.
Human Codex should separate transport, recovery, and tool safety from model intelligence.
When no server is listening, the connection is refused. When a toy server is listening,
the wire can be tested before Qwen exists.
"""


def text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, dict):
                out.append(str(item.get("text") or item.get("content") or ""))
            else:
                out.append(str(item))
        return "\n".join(x for x in out if x)
    return str(content)


def messages_to_prompt(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    lines = []
    for m in messages:
        if isinstance(m, dict):
            lines.append(f"{m.get('role', 'unknown')}: {text_from_content(m.get('content'))}")
    return "\n".join(lines).strip()


class CharNGramLM:
    """Tiny character n-gram predictor with backoff."""

    def __init__(self, corpus: str, n: int = 4, seed: int = 7) -> None:
        self.n = max(2, n)
        self.seed = seed
        self.table: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        self.global_counts: Counter[str] = Counter(corpus)
        chars = list(corpus)
        for i in range(max(0, len(chars) - self.n + 1)):
            ctx = tuple(chars[i : i + self.n - 1])
            nxt = chars[i + self.n - 1]
            self.table[ctx][nxt] += 1

    def _candidates(self, context: list[str]) -> tuple[int, list[dict[str, Any]]]:
        for order in range(self.n - 1, 0, -1):
            if len(context) < order:
                continue
            suffix = tuple(context[-order:])
            merged: Counter[str] = Counter()
            for key, counts in self.table.items():
                if key[-order:] == suffix:
                    merged.update(counts)
            if merged:
                return order, self._rows(merged)
        return 0, self._rows(self.global_counts)

    @staticmethod
    def _rows(counts: Counter[str]) -> list[dict[str, Any]]:
        total = max(sum(counts.values()), 1)
        rows = []
        for token, count in counts.most_common(12):
            p = count / total
            rows.append({"token": token, "count": count, "probability": p, "logprob": math.log(max(p, 1e-12))})
        return rows

    def _pick(self, rows: list[dict[str, Any]], temperature: float, rng: random.Random) -> dict[str, Any]:
        if not rows:
            return {"token": " ", "probability": 1.0, "logprob": 0.0}
        if temperature <= 0:
            return max(rows, key=lambda r: (r["probability"], r["count"], r["token"]))
        weights = [max(r["probability"], 1e-12) ** (1.0 / max(temperature, 1e-6)) for r in rows]
        x = rng.random() * sum(weights)
        acc = 0.0
        for row, weight in zip(rows, weights):
            acc += weight
            if acc >= x:
                return row
        return rows[-1]

    def generate(self, prompt: str, max_tokens: int, temperature: float = 0.0) -> dict[str, Any]:
        context = list(prompt + "\nassistant: ")
        out: list[str] = []
        trace: list[dict[str, Any]] = []
        rng = random.Random(self.seed + len(prompt) + max_tokens)
        for step in range(max(1, min(max_tokens, 512))):
            order, rows = self._candidates(context + out)
            chosen = self._pick(rows, temperature, rng)
            out.append(chosen["token"])
            trace.append({
                "step": step,
                "context_tail": "".join((context + out)[-(self.n + 8):]),
                "matched_ngram_order": order,
                "selected": {k: chosen[k] for k in ("token", "probability", "logprob") if k in chosen},
                "top_candidates": rows[:5],
            })
            text = "".join(out)
            if len(out) >= 8 and chosen["token"] == "\n":
                break
            if len(out) >= 16 and text.endswith((".", "!", "?")):
                break
        content = "".join(out).strip() or "OK"
        return {
            "content": content,
            "trace": trace,
            "prompt_tokens": len(prompt),
            "completion_tokens": len(out),
        }


class Server(ThreadingHTTPServer):
    def __init__(self, addr: tuple[str, int], model: str, engine: CharNGramLM, delay_ms: int) -> None:
        super().__init__(addr, Handler)
        self.model = model
        self.engine = engine
        self.delay_ms = max(0, delay_ms)


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} - {fmt % args}")

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(n) if n else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/v1/models":
            self._send_json(HTTPStatus.OK, {
                "object": "list",
                "data": [{"id": self.server.model, "object": "model", "created": int(time.time()), "owned_by": "local-toy-engine"}],
            })
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"message": f"unknown path: {self.path}", "type": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": {"message": f"unknown path: {self.path}", "type": "not_found"}})
            return
        try:
            payload = self._read_json()
        except Exception as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc), "type": "invalid_request_error"}})
            return

        mode = str(payload.get("toy_mode") or payload.get("mode") or "primitive")
        if mode == "crash_500":
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": {"message": "intentional toy crash_500", "type": "server_error"}})
            return

        delay_ms = int(payload.get("toy_delay_ms") or self.server.delay_ms)
        if delay_ms > 0 and not payload.get("stream"):
            time.sleep(delay_ms / 1000.0)

        prompt = messages_to_prompt(payload.get("messages"))
        max_tokens = int(payload.get("max_tokens") or payload.get("max_completion_tokens") or 64)
        temperature = float(payload.get("temperature") or 0.0)

        if mode == "ok":
            result = {"content": "OK", "trace": [], "prompt_tokens": len(prompt), "completion_tokens": 1}
        elif mode == "echo":
            result = {"content": f"OK — toy server received: {prompt[-300:]}", "trace": [], "prompt_tokens": len(prompt), "completion_tokens": min(len(prompt), 300)}
        elif mode == "tool_call":
            self._send_tool_call(payload, prompt)
            return
        else:
            result = self.server.engine.generate(prompt, max_tokens=max_tokens, temperature=temperature)

        if payload.get("stream"):
            self._send_stream(str(result["content"]), str(payload.get("model") or self.server.model), delay_ms)
            return

        body = {
            "id": "chatcmpl-toy-" + uuid.uuid4().hex[:12],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": str(payload.get("model") or self.server.model),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": result["content"]}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["prompt_tokens"] + result["completion_tokens"],
            },
            "x_toy_trace": {
                "mode": mode,
                "engine": "char-ngram",
                "ngram_n": self.server.engine.n,
                "prompt_tail": prompt[-500:],
                "steps": result["trace"][:40],
            },
        }
        self._send_json(HTTPStatus.OK, body)

    def _send_stream(self, text: str, model: str, delay_ms: int) -> None:
        cid = "chatcmpl-toy-" + uuid.uuid4().hex[:12]
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.end_headers()

        def emit(obj: dict[str, Any]) -> None:
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

        emit({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
        for ch in text:
            emit({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": None}]})
        emit({"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
        self.wfile.write(b"data: [DONE]\n\n")

    def _send_tool_call(self, payload: dict[str, Any], prompt: str) -> None:
        self._send_json(HTTPStatus.OK, {
            "id": "chatcmpl-toy-" + uuid.uuid4().hex[:12],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": str(payload.get("model") or self.server.model),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_toy_" + uuid.uuid4().hex[:8],
                        "type": "function",
                        "function": {
                            "name": "toy_echo",
                            "arguments": json.dumps({"received_prompt_tail": prompt[-200:]}, ensure_ascii=False),
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": len(prompt), "completion_tokens": 1, "total_tokens": len(prompt) + 1},
            "x_toy_trace": {"mode": "tool_call", "engine": "synthetic-tool-call"},
        })


def load_corpus(path: str | None) -> str:
    if not path:
        return DEFAULT_CORPUS
    return Path(path).expanduser().resolve().read_text(encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="Run a primitive OpenAI-compatible toy LM server.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--model", default="toy-causal-lm")
    p.add_argument("--n", type=int, default=4)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--corpus-file", default=None)
    p.add_argument("--delay-ms", type=int, default=0)
    args = p.parse_args()

    server = Server((args.host, args.port), args.model, CharNGramLM(load_corpus(args.corpus_file), n=args.n, seed=args.seed), args.delay_ms)
    print(f"Toy OpenAI-compatible server listening on http://{args.host}:{args.port}", flush=True)
    print("Endpoint: POST /v1/chat/completions | GET /v1/models", flush=True)
    print("Modes: primitive, ok, echo, tool_call, crash_500; add stream=true for SSE", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping toy server.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
