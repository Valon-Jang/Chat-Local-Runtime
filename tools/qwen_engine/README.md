# Qwen Engine Library — engine-only

This folder is an engine-only staging area for connecting Qwen/open-weight LLM runtimes to Human Codex without vendoring large model weights or cloning full upstream repositories.

## What is included

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
