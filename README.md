# Chat Local Runtime

**Experimental research project**

Chat Local Runtime studies whether a general-purpose chat AI can turn the execution and storage surfaces already exposed by the host product into a reusable file-based software layer.

> Instead of regenerating every utility inside LLM context, the chat AI can build, inspect, diff, verify, package, store, and reuse real executable files.

This project measures the boundary between model reasoning and machine-side reusable software. It does **not** treat chat sandboxes as permanent operating systems.

## Current tool stack

Five AI-first local tools have now been built and validated:

| Tool | Build | Purpose | Self-test |
|---|---|---|---:|
| Local Worker Hub | `0.1.1` | deterministic execution foundation / plugin routing | PASS |
| Verification Runner | `0.2.0` | contract- and validator-backed fact confirmation | 8/8 PASS |
| Workspace Inspector | `0.1.3` | metadata-first preprocessing and canonical targeted reading | 15/15 PASS |
| Smart Diff / State Tracker | `0.1.1` | structural / artifact / non-git semantic comparison | 17/17 PASS |
| Artifact Builder / Release Manager | `0.1.1` | deterministic build, SHA/manifest, verification gating and packaging | 16/16 PASS |

The exact current four-tool core is mirrored under [`dist/active/`](dist/active/). Artifact Builder v0.1.1 remains reconstructed from its verified binary parts already checked into `dist/`.

The older `dist/*.pyz` builds and installer V03 are intentionally retained as historical public fallback artifacts instead of being silently overwritten.

## Design principle

> **Programs confirm and compress deterministic facts so the AI can decide the next action.**

Small local utilities are not treated as substitute reasoning engines. They should reduce repeated execution/context work and return compact, auditable evidence.

## What changed in the active core

### Verification Runner v0.2.0 — fact confirmation first

- explicit executable functionality contracts: args, stdin, return code, stdout/stderr conditions and expected JSON keys
- **no functional contract => `INCONCLUSIVE`**, not fabricated functionality PASS
- runtime discovery and structured facts for installed `ruff`, `bandit`, `mypy`, `pytest`, and `coverage`
- missing validators stay explicitly unavailable; the runner does not auto-install them
- repeated verification can report newly failing, resolved, and changed facts relative to a prior result
- static pattern indicators remain advisory evidence rather than substitutes for real validator output

In one tested ChatGPT code runtime on 2026-08-30, `pytest` and `coverage` were available while `ruff`, `bandit`, and `mypy` were not. This is an empirical runtime observation, not a product-wide guarantee.

### Workspace Inspector v0.1.3 — canonical paths for every input count

All relative content references now use:

```text
inputN/...
```

This applies even when there is only one input root. A path returned by `inspect` can therefore be passed unchanged to `targeted-content`. The self-test permanently reproduces the previously missed single-input round-trip failure.

### Smart Diff v0.1.1 — focus where plain git diff is weak

- JSON structural key/value changes
- TOML structural changes
- heuristic YAML structural changes
- ZIP / PYZ internal member changes
- XLSX internal package/member changes
- non-git file-tree comparisons
- auditable `importance_basis` with signals and point contributions instead of an unexplained score

### Local Worker Hub v0.1.1 — deliberately unchanged

The Hub remains the common execution foundation. A detached async API such as `submit -> status -> result` remains a plausible future experiment, but it is **not promoted yet**. Its value depends heavily on workload frequency and runtime CPU entitlement, so it needs A/B evidence before increasing system complexity.

Detailed redesign record: [`research/FACT_CONFIRMATION_REDESIGN_2026-08-30.md`](research/FACT_CONFIRMATION_REDESIGN_2026-08-30.md)

## Storage model: Library-first, GitHub reference/fallback

### ChatGPT Library

Preferred for exact active artifacts when available:

- shortest cross-chat recovery path
- preserves the actual generated `.pyz`, ZIP and verification outputs
- avoids reconstructing a program from prose

### GitHub `Chat-Local-Runtime`

Used for:

- public documentation and version history
- exact mirrored active artifacts when available
- historical fallback builds
- SHA-256 records
- installer/reconstruction logic
- benchmark and research evidence

A file existing in GitHub does **not** mean it is already installed in a fresh ChatGPT runtime. A retrieval/install step is still required.

```text
ChatGPT Library
  -> preferred exact active artifact reuse

GitHub Chat-Local-Runtime
  -> public reference / fallback / reconstruction / research history
```

## Current installer — v0.4.0-public

Use:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py install
```

Default root:

```text
/mnt/data/ai_program_lab
```

Verify an existing installation:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py verify
```

Verify repository artifacts before installation:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py source-verify
```

Run installer regression tests:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py self-test
```

Installer v0.4 properties:

- current four core artifacts are read from versioned `dist/active/` paths
- strict `offload-ai/1` contract enforcement for the four current core tools
- Artifact Builder v0.1.1 is explicitly marked as predating that shared contract; its hash/version/self-test are enforced without inventing a declaration
- source SHA gate and staging SHA gate
- backup-time manifest records the actual previous installation hashes
- failed install restores and verifies against that backup manifest, **not** the new installer's expected hashes
- first-install failure with no previous files reports a distinct `NO_PREVIOUS_INSTALL_REMOVED` state
- latest 3 backups retained by default
- stable machine-readable `next_action`

Installer self-test: **8/8 PASS**.

Legacy V03 remains available for historical fallback reproduction:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V03.py install
```

## Mandatory new / updated program validation lifecycle

A program is not complete merely because it builds or passes its own self-test.

```text
candidate
  -> Local Worker Hub integration where meaningful
  -> Workspace Inspector
  -> Smart Diff when a trustworthy comparison exists
  -> Verification Runner with explicit contract / real validator facts
  -> Artifact Builder / Release Manager
  -> reproduce any discovered defect in a permanent regression test
  -> reciprocal dogfood against affected existing tools
  -> COMPLETE
```

A technically inapplicable step can be skipped, but the skip is explicit rather than silently converted into PASS.

## Artifact Builder / Release Manager v0.1.1

Artifact Builder automates:

```text
source folder
  -> deterministic .pyz or ZIP
  -> SHA-256 + file manifest
  -> verification evidence
  -> BLOCK / RELEASE_WITH_WARNINGS / RELEASE
  -> final release package
```

Artifact Builder v0.1.1 SHA-256:

```text
1677f84252d0e275f0448426ac6702318ad30589c462493aea533e1ddfe63c3a
```

It is stored as binary parts `dist/artifactbuilder.pyz.part01` ... `part05`; the installer reconstructs the exact bytes and checks the final SHA-256.

## Core architecture

```text
Chat AI
  -> local runtime / workspace
      -> Local Worker Hub
          -> Workspace Inspector       # what is here?
          -> Smart Diff / State Tracker# what actually changed?
          -> Verification Runner       # what facts are confirmed?
          -> Artifact Builder          # what exact artifact is releasable?
      -> compact structured evidence
  -> AI judgment / next action
```

The key distinction is **file-based capability vs. LLM-context capability**. Deterministic work belongs in reusable files/tools when that reduces repeated context and execution effort; reasoning and final judgment stay with the AI.

## Preliminary runtime observations

One tested ChatGPT execution environment on 2026-08-30 showed approximately:

- ~30 GiB available scratch storage during the probe
- 4 GiB effective memory ceiling
- ~4 sustained CPU cores of effective entitlement
- shared local filesystem across local tool calls
- loopback TCP and Unix-domain socket IPC
- detached-process survival across ordinary local tool calls in that session
- relatively expensive fresh Python startup vs warm reuse
- no general outbound internet access from the tested local execution path

These are empirical observations, **not guaranteed OpenAI product specifications**.

## Generated artifact handoff boundary

User-verified generated-file handoff in that run:

```text
449,000,000 bytes <= successful boundary < 449,500,000 bytes
```

Practical rule used in this research: keep a single downloadable package at **400,000,000 bytes or less** for margin. This is a file-handoff benchmark, not proof that a model can correctly author a 449 MB software project.

## Next tool roadmap

1. **Sandbox Launcher** — strong OS sandbox backend for behavior-testing native/opaque external executables.
2. **Local Index / Search Engine** — incremental code/document/config index and relationship lookup.
3. **Log / Trace Analyzer** — deterministic failure clustering and compact evidence extraction.
4. **Dependency / Impact Mapper** — dependency/config/reference graph and impacted-file/test candidates.
5. **Worker Hub async job experiment** — only if A/B testing shows `submit/status/result` materially reduces blocking work in the target runtime.

## Safety boundary

This research uses capabilities exposed by the host runtime. It does not depend on sandbox escape, hidden-service discovery, rate-limit bypass, or deliberate circumvention of platform safeguards.

## Research records

- [`research/INITIAL_FINDINGS_2026-08-30.md`](research/INITIAL_FINDINGS_2026-08-30.md)
- [`research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md`](research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md)
- [`research/PUBLIC_BUILD_VERIFICATION_2026-08-30.json`](research/PUBLIC_BUILD_VERIFICATION_2026-08-30.json)
- [`research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json`](research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json)
- [`research/FACT_CONFIRMATION_REDESIGN_2026-08-30.md`](research/FACT_CONFIRMATION_REDESIGN_2026-08-30.md)
