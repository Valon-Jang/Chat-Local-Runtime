# Qwen Engine Library — engine-only

This folder is an engine-only staging area for connecting Qwen/open-weight LLM runtimes to Human Codex without vendoring large model weights or cloning full upstream repositories.

## What is included

- `toy_causal_lm_server.py` — primitive OpenAI-compatible toy server for transport, streaming, tool-call, failure, and next-token trace tests without any real model.
- `swarm_micro_reasoning/` — dependency-free message-passing micro-reasoning kernel for Reference-1, 2x2 grid, and 2x2x2 cube recognition/propagation tests under a 10 MB budget.
- `qwen_openai_probe.py` — minimal OpenAI-compatible endpoint probe for an internal or local Qwen server.
- `qwen_local_probe.py` — local Transformers probe that can inspect hidden states/logits when a model already exists on disk.
- `llama_cpp_server.ps1` — Windows wrapper for running an already-downloaded GGUF model through llama.cpp.
- `engine_manifest.json` — source and boundary manifest for future acquisition.

## What is intentionally not included

- No model weights.
- No `.gguf`, `.safetensors`, `.bin`, or Hugging Face snapshot folders.
- No vendored `llama.cpp`, `transformers`, `vllm`, or `sglang` source trees.
- No API keys, endpoint secrets, tokens, cookies, or company data.

## Intended modes

### 0. Primitive toy causal LM server

Use this before Qwen exists. It goes back to the basic idea of next-token prediction with a tiny character n-gram model and returns OpenAI-compatible responses.

```powershell
python tools/qwen_engine/toy_causal_lm_server.py --host 127.0.0.1 --port 8000
python tools/qwen_engine/qwen_openai_probe.py --api-base http://127.0.0.1:8000/v1 --model toy-causal-lm --prompt "짧게 보기만해"
```

Useful toy modes:

```json
{"toy_mode":"primitive"}
{"toy_mode":"ok"}
{"toy_mode":"echo"}
{"toy_mode":"tool_call"}
{"toy_mode":"crash_500"}
{"stream":true}
```

### 0.5. Swarm micro-reasoning kernel

Use this to test system-intelligence before real Qwen workers are attached. It is not an LLM; it runs local node/edge message passing, evidence extraction, risk labeling, prompt-injection-as-data detection, and one final readout packet.

```powershell
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --self-test --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --benchmark --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --topology grid_2x2 single_error --trace --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --topology cube_2x2x2 conflict --pretty
```

Growth order is fixed: `Reference-1 -> 2x2 -> 2x2x2 -> 3x3 -> 3x3x3`; do not skip ahead to larger topologies before the prior gate passes.

### 1. Internal Qwen / OpenAI-compatible API

Use this when the company already exposes Qwen through an OpenAI-compatible endpoint.

```powershell
$env:QWEN_API_BASE="http://127.0.0.1:8000/v1"
$env:QWEN_MODEL="qwen"
python tools/qwen_engine/qwen_openai_probe.py --prompt "Say OK only."
```

Optional API key:

```powershell
$env:QWEN_API_KEY="..."
python tools/qwen_engine/qwen_openai_probe.py --prompt "Say OK only."
```

### 2. Local Transformers probe

Use this only when a local model directory already exists. The script uses `local_files_only=True` by default and fails closed if the model is not present.

```powershell
python tools/qwen_engine/qwen_local_probe.py --model-path D:\Models\Qwen3-0.6B --prompt "2+2="
```

With last-token hidden vector dump:

```powershell
python tools/qwen_engine/qwen_local_probe.py --model-path D:\Models\Qwen3-0.6B --prompt "2+2=" --dump-last-token-hidden out\qwen_hidden_last_token.npz
```

### 3. GGUF runtime through llama.cpp

Use this when the model is already downloaded as a GGUF file.

```powershell
$env:LLAMA_EXE="C:\llama.cpp\llama-server.exe"
$env:MODEL_GGUF="D:\Models\Qwen3-0.6B-Q8_0.gguf"
powershell -ExecutionPolicy Bypass -File tools/qwen_engine/llama_cpp_server.ps1
```

## Boundary rule

This folder is a connector/engine layer, not a model mirror. Heavy files stay outside the repository and should be referenced by local path, internal artifact store, or official upstream URL.

## Human Codex integration direction

```text
Human Codex
  -> model provider adapter
  -> Qwen OpenAI-compatible endpoint OR local runtime
  -> trace logger
  -> tool/result compression
  -> model re-judgement
```

The first production target should be the OpenAI-compatible endpoint path. The local hidden-state probe is for research/debugging, not normal user work.
