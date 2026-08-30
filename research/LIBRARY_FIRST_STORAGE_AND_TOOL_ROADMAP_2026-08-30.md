# Library-first storage and offload tool roadmap — 2026-08-30

## Decision

Chat Local Runtime now uses a two-layer storage model:

1. **ChatGPT Library = active ChatGPT artifact store**
   - The exact `.pyz`, ZIP and verification artifacts generated during ChatGPT work should be reused from ChatGPT Library when they are available there.
   - This is the shortest path for another ChatGPT conversation to recover a previously generated artifact without rebuilding it from prose or source descriptions.

2. **GitHub `Valon-Jang/Chat-Local-Runtime` = public reference, fallback and reproducibility store**
   - GitHub remains valuable for public builds, SHA-256 records, research notes, installation logic, external recovery and version history.
   - The repository installer remains useful when the active ChatGPT artifact is unavailable or a clean runtime needs the public tool layer reconstructed.

This is not a claim that Library and GitHub provide identical persistence semantics. They solve different problems.

## Why Library became the default inside ChatGPT

The original repository-first approach was useful, but it introduced an extra handoff step: a new ChatGPT runtime still had to retrieve the repository content and install/copy the executables into the current runtime before use.

For ChatGPT-to-ChatGPT reuse, Library is a better active-artifact path because it is designed around reusing files produced in ChatGPT. The project therefore treats Library as the first place to recover the exact generated runtime artifacts, while GitHub remains the durable public reconstruction/reference path.

The practical goal is:

```text
new Chat
  -> recover existing artifact from ChatGPT Library when available
  -> self-test / verify
  -> use through Local Worker Hub

fallback
  -> GitHub Chat-Local-Runtime
  -> INSTALL_CHATGPT_FROM_REPO.py
  -> reconstructed public tool layer
```

## Why GitHub is still useful

The repository continues to provide things Library is not intended to replace:

- public, inspectable documentation
- explicit version history and commits
- public reference rebuilds
- SHA-256 records
- a repository-based installer
- reproducibility notes and benchmark records
- recovery from outside a ChatGPT-only workflow
- a stable place to explain the architecture and limitations

The existing installer is retained:

```text
installers/INSTALL_CHATGPT_FROM_REPO.py
```

No duplicate installer is needed for this storage-policy change.

## Important limitations

### 1. GitHub presence does not mean runtime installation

A `.pyz` existing in GitHub does not automatically make it available in a fresh ChatGPT execution runtime. Retrieval/install is still required.

### 2. Public rebuilds are not assumed to be byte-identical to active Library artifacts

The repository already documents that public builds may be reference rebuilds from recorded feature checkpoints. The active artifact in Library may contain a newer hotfix or packaging correction.

Therefore:

- compare version/capability/self-test before use
- do not assume filename equality means binary equality
- use Verification Runner before promotion when the artifact changed

### 3. Library is ChatGPT-specific

Library is convenient for ChatGPT cross-chat file reuse, but it is not a general external software registry or source-control system. GitHub remains the portable/public layer.

### 4. Runtime state is still ephemeral

Neither Library nor GitHub turns the ChatGPT code runtime itself into a permanent operating system. Programs are recovered into the current runtime and then executed there.

### 5. Native external-program verification still needs a strong sandbox

Verification Runner intentionally returns `BLOCKED_NEEDS_SANDBOX` for native/opaque binaries when a strong OS sandbox backend is unavailable. Storing the binary does not remove this execution-safety boundary.

## Current offload stack

The working stack is organized around four AI-first tools:

1. **Local Worker Hub** — one-shot execution and plugin routing
2. **Verification Runner** — functionality/safety/performance/compatibility quality gate
3. **Workspace Inspector** — metadata-first workspace preprocessing and targeted reading
4. **Smart Diff / State Tracker** — semantic change tracking and impact candidates

Recent maintenance tightened the common contract:

- Local Worker Hub added a common `self-test` path.
- Workspace Inspector fixed multi-input `inputN/...` round-trip handling and added a regression test that exercises the actual packaged `.pyz`.
- Verification Runner fixed recursive self-copy when verification output was located under the target tree.

## Next program roadmap

Priority is based on how much each tool strengthens the existing stack rather than on feature count.

### 1. Artifact Builder / Release Manager

Automate the repeated release path:

```text
source
  -> build `.pyz` / ZIP
  -> SHA-256 + manifest
  -> package consistency checks
  -> Verification Runner
  -> verified release package
```

Primary value: eliminate source/artifact drift and repeated manual packaging work.

### 2. Sandbox Launcher

Provide a strong OS-sandbox execution backend for Verification Runner, especially for native or opaque external executables.

Primary value: move more external-program verification from static/blocked status into controlled behavioral verification.

### 3. Local Index / Search Engine

Maintain an incremental local index over code, documents and configuration with compact relationship/search queries.

Primary value: avoid rescanning entire workspaces for repeated lookup questions.

### 4. Log / Trace Analyzer

Deterministically reduce large logs and traces into failure clusters, signatures, timelines and minimal evidence bundles.

Primary value: reduce model-visible log volume while improving reproducible debugging evidence.

### 5. Dependency / Impact Mapper

Build explicit dependency/config/reference maps and propose impacted files/tests after a change.

Primary value: strengthen Smart Diff impact ranking and Verification Runner test selection.

## Default development loop going forward

```text
Workspace Inspector
  -> understand current workspace

implement/update tool
  -> Local Worker Hub integration

Smart Diff
  -> confirm meaningful changes

Verification Runner
  -> functionality + safety + performance + compatibility gate

Artifact Builder (future)
  -> package verified release

ChatGPT Library
  -> active ChatGPT artifact reuse

GitHub
  -> public reference / fallback / reproducibility
```
