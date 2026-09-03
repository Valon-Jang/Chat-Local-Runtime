<#
Run an already-downloaded GGUF model with llama.cpp.

Engine-only rule:
- This wrapper does not download llama.cpp.
- This wrapper does not download model weights.
- MODEL_GGUF must point to an existing local .gguf file.
- LLAMA_EXE must point to an existing llama-server executable.
#>

param(
    [string]$LlamaExe = $env:LLAMA_EXE,
    [string]$ModelGguf = $env:MODEL_GGUF,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [int]$ContextSize = 32768,
    [int]$Threads = 0,
    [int]$GpuLayers = 0
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($LlamaExe)) {
    throw "LLAMA_EXE is required. Example: `$env:LLAMA_EXE='C:\llama.cpp\llama-server.exe'"
}

if ([string]::IsNullOrWhiteSpace($ModelGguf)) {
    throw "MODEL_GGUF is required. Example: `$env:MODEL_GGUF='D:\Models\Qwen3-0.6B-Q8_0.gguf'"
}

if (-not (Test-Path -LiteralPath $LlamaExe)) {
    throw "llama-server executable not found: $LlamaExe"
}

if (-not (Test-Path -LiteralPath $ModelGguf)) {
    throw "GGUF model not found: $ModelGguf"
}

$argsList = @(
    "--model", $ModelGguf,
    "--host", $HostName,
    "--port", $Port,
    "--ctx-size", $ContextSize
)

if ($Threads -gt 0) {
    $argsList += @("--threads", $Threads)
}

if ($GpuLayers -gt 0) {
    $argsList += @("--n-gpu-layers", $GpuLayers)
}

Write-Host "Starting llama.cpp server"
Write-Host "  exe:   $LlamaExe"
Write-Host "  model: $ModelGguf"
Write-Host "  url:   http://$HostName`:$Port"
Write-Host "  note:  This is an engine wrapper only; no model files are stored in the repository."

& $LlamaExe @argsList
