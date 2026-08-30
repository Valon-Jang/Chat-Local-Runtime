# Chat Local Runtime

**Experimental research project**

Chat Local Runtime studies whether a general-purpose chat AI can turn the execution and storage surfaces already exposed by the host product into a reusable file-based software layer.

> Instead of regenerating every utility inside LLM context, the chat AI can build, inspect, diff, verify, package, store, and reuse real executable files.

This project measures the boundary between model reasoning and machine-side reusable software. It does **not** treat chat sandboxes as permanent operating systems.

## Current tool stack

Five AI-first local tools have now been built and validated:

| Tool | Build | Purpose | Self-test |
|---|---|---|---:|
| Local Worker Hub | `0.1.1-public` | common deterministic offload / plugin execution | 7/7 PASS |
| Verification Runner | `0.1.1-public` | fingerprinting, static checks and controlled behavioral verification | 5/5 PASS |
| Workspace Inspector | `0.1.2-public` in `dist/` | metadata-first workspace preprocessing and targeted-content planning | 14/14 PASS |
| Smart Diff / State Tracker | `0.1.0-public` | semantic code/config/document change tracking | 15/15 PASS |
| Artifact Builder / Release Manager | `0.1.1` | deterministic `.pyz`/ZIP build, SHA/manifest, verification gating and release packaging | 16/16 PASS |

The original four executable public fallback builds remain under [`dist/`](dist/). Artifact Builder v0.1.1 is the exact verified generated artifact. Because the available GitHub writer is text/bounded-blob oriented, that executable is stored as five binary parts under `dist/artifactbuilder.pyz.part01` ... `part05`; installer v0.3 concatenates them byte-for-byte and checks the final SHA-256.

Artifact Builder v0.1.1 SHA-256:

```text
1677f84252d0e275f0448426ac6702318ad30589c462493aea533e1ddfe63c3a
```

> **Identity boundary:** the older four GitHub executables are public reference/fallback rebuilds and are not claimed to be byte-identical to newer ChatGPT Library artifacts. Artifact Builder v0.1.1 is an exact mirror of the verified generated artifact.

## Mandatory new / updated program validation lifecycle

A new offload program is **not complete merely because it builds or passes its own self-test**. Unless a step is technically inapplicable, use this order:

```text
new / modified candidate
        |
        v
1. Local Worker Hub first
   - run Hub health/self-test
   - invoke the candidate through the real Hub plugin contract when meaningful
   - validate stdin/JSON/exit-code/result behavior
        |
        v
2. Workspace Inspector
   - inspect source/workspace metadata first
   - identify key files, structure, anomalies, integration points and targeted reads
        |
        v
3. Smart Diff / State Tracker
   - compare against a trustworthy previous version/baseline when available
   - separate intentional changes from accidental collateral changes
        |
        v
4. Verification Runner
   - verify source and final executable artifact where applicable
   - functionality / safety / performance / compatibility gates
        |
        v
5. Artifact Builder / Release Manager
   - deterministic .pyz or ZIP
   - SHA-256 + manifest
   - normalize verifier evidence
   - BLOCK / RELEASE_WITH_WARNINGS / RELEASE
        |
        v
6. Defect loop
   - if a meaningful problem is found, fix it
   - add a permanent regression test when reproducible
   - rerun the affected sequence; do not promote the known-bad build
        |
        v
7. Reciprocal dogfood
   - run the new program against each pre-existing program where its role applies
   - rebuild / inspect / analyze / verify as appropriate
   - rerun every affected original program's own self-test
        |
        v
COMPLETE
```

### Exceptions

Skip a step only when it is technically inapplicable or adds no meaningful evidence—for example Smart Diff without a trustworthy baseline, executable packaging checks for a documentation-only change, or a tool whose role cannot operate on the target. A skip is recorded explicitly; it is not a silent shortcut.

This lifecycle was adopted after it caught a real Artifact Builder v0.1.0 integration defect: Local Worker Hub calls plugins as `request -` with JSON on stdin, while v0.1.0 rejected the positional `-`. v0.1.1 fixed the contract and added a permanent Hub stdin regression test.

Detailed evidence: [`research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json`](research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json)

## Storage model: Library-first, GitHub fallback/reference

### ChatGPT Library

Preferred for exact active artifacts when available:

- shortest cross-chat recovery path
- preserves the actual generated `.pyz`, ZIP and verification outputs
- avoids reconstructing a program from prose

### GitHub `Chat-Local-Runtime`

Used for:

- public documentation and version history
- reference/fallback executables
- exact mirrored artifact parts when available
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

## Install in a ChatGPT code runtime

The five-tool installer is:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V03.py install
```

Default root:

```text
/mnt/data/ai_program_lab
```

Verify an existing installation:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V03.py verify
```

Verify repository artifacts before installation:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V03.py source-verify
```

Installer v0.3 is offline, reconstructs `artifactbuilder.pyz` by concatenating the five checked-in parts, verifies its SHA-256, installs all five programs, and executes each tool's own self-test. It does not assume every program exposes an identical CLI contract; Artifact Builder, for example, has `self-test` but no `capabilities` verb.

Installed layout:

```text
ai_program_lab/
├── programs/
│   ├── workerhub.pyz
│   ├── verificationrunner.pyz
│   ├── workspaceinspector.pyz
│   ├── smartdiff.pyz
│   └── artifactbuilder.pyz
├── code/
├── tests/
├── fixtures/
├── benchmarks/
├── artifacts/
├── cache/
├── runtime/
├── logs/
└── scratch/
```

## Artifact Builder / Release Manager v0.1.1

Pipeline:

```text
source folder
  -> inspect
  -> choose pure .pyz or ZIP
  -> deterministic package
  -> SHA-256 + file manifest
  -> static checks
  -> Verification Runner adapter
  -> BLOCK / RELEASE_WITH_WARNINGS / RELEASE
  -> final release ZIP
```

Properties:

- Python projects and general folders
- runnable Python selects pure `.pyz`; general folders select ZIP
- source is read-only
- no network
- symlinks are not followed
- secret-looking files are excluded by default
- nested output directories are excluded to prevent recursive self-copy
- accepts existing verifier JSON or an external verifier command adapter
- Hub-compatible `request -` stdin JSON contract
- self-host build reproduced the exact v0.1.1 artifact SHA
- reciprocal dogfood rebuilt the four pre-existing public fallback tools and preserved self-tests: 7/7, 5/5, 14/14, 15/15 PASS

## Core architecture

```text
Chat AI
  -> local runtime / workspace
      -> Local Worker Hub
          -> Workspace Inspector
          -> Smart Diff / State Tracker
          -> Verification Runner
          -> Artifact Builder / Release Manager
          -> future verified tools
      -> tests / fixtures / benchmarks
      -> cache / indexes / artifacts
  -> compact verified result back to the model
```

The key distinction is **file-based capability vs. LLM-context capability**: a reusable capability can exist as an executable, script, fixture, index, cache, benchmark, or package instead of being regenerated every task.

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

Artifact Builder is complete at v0.1.1. Next priorities:

1. **Sandbox Launcher** — strong OS sandbox backend for behavior-testing native/opaque external executables.
2. **Local Index / Search Engine** — incremental code/document/config index and relationship lookup.
3. **Log / Trace Analyzer** — deterministic failure clustering and compact evidence extraction.
4. **Dependency / Impact Mapper** — dependency/config/reference graph and impacted-file/test candidates.

## Safety boundary

This research uses capabilities exposed by the host runtime. It does not depend on sandbox escape, hidden-service discovery, rate-limit bypass, or deliberate circumvention of platform safeguards.

## Research records

- [`research/INITIAL_FINDINGS_2026-08-30.md`](research/INITIAL_FINDINGS_2026-08-30.md)
- [`research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md`](research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md)
- [`research/PUBLIC_BUILD_VERIFICATION_2026-08-30.json`](research/PUBLIC_BUILD_VERIFICATION_2026-08-30.json)
- [`research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json`](research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json)
