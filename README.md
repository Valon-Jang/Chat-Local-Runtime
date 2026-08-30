# Chat Local Runtime

**Experimental research project**

Chat Local Runtime studies whether general-purpose chat AIs can turn execution and storage environments already exposed by the host chat product into a reusable file-based software layer.

> Instead of regenerating every utility inside LLM context, the chat AI can build, verify, store, and reuse real executable files inside its available runtime.

This project measures the boundary between model reasoning and machine-side reusable software. It does **not** treat chat sandboxes as permanent operating systems.

## Current status

A ChatGPT runtime was used to build and validate four AI-first local tools as real `.pyz` files:

| Tool | Public build | Purpose | Public self-test |
|---|---|---|---:|
| Local Worker Hub | `0.1.1-public` | one-shot deterministic local offload / plugin execution | 7/7 PASS |
| Verification Runner | `0.1.1-public` | program fingerprinting, static checks and controlled behavioral verification | 5/5 PASS |
| Workspace Inspector | `0.1.2-public` | metadata-first workspace preprocessing and targeted-content planning | 14/14 PASS |
| Smart Diff / State Tracker | `0.1.0-public` | semantic file/config/code/document change tracking | 15/15 PASS |

The executable public builds are under [`dist/`](dist/). A ChatGPT-oriented installer is under [`installers/`](installers/).

> **Public-build note:** the original private scratch artifacts were not durable across runtime replacement. The files in this repository are public reference rebuilds from the recorded feature/validation checkpoint, followed by fresh public self-tests. They are not claimed to be byte-identical copies of the original scratch binaries or of newer active artifacts recovered through ChatGPT Library.

## Storage model: Library-first inside ChatGPT, GitHub as reference/fallback

The project now separates **active ChatGPT artifact reuse** from **public reproducibility**.

### ChatGPT Library — active artifact store

For ChatGPT-to-ChatGPT reuse, the preferred path is to recover the exact generated `.pyz`, ZIP, and verification artifacts from ChatGPT Library when they are available there.

Why:

- shorter cross-chat recovery path inside ChatGPT
- less need to reconstruct a program from prose or source descriptions
- preserves the actual generated artifact instead of assuming a public rebuild is identical
- convenient for small AI-first runtime tools whose executable shells are only tens of kilobytes

### GitHub — public reference, fallback and reconstruction store

This repository remains useful for:

- public, inspectable documentation
- version history and commits
- public reference rebuilds
- SHA-256 records
- the repository-based ChatGPT installer
- external recovery and reproducibility
- benchmark and research records

The important limitation is that **a file existing in GitHub does not mean it is already installed in a fresh ChatGPT runtime**. A retrieval/install step is still required. Likewise, a public rebuild in this repository is not assumed to be byte-identical to the latest active artifact in Library.

The two stores therefore have different jobs:

```text
ChatGPT Library
  -> active ChatGPT artifact reuse

GitHub Chat-Local-Runtime
  -> public reference / fallback / reconstruction / research history
```

Detailed rationale and limitations: [`research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md`](research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md)

## Install in a ChatGPT code runtime

Download/unpack this repository into a compatible ChatGPT code runtime, then run:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO.py install
```

Default installation root:

```text
/mnt/data/ai_program_lab
```

Verify an existing installation:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO.py verify
```

The installer requires no network access. It verifies SHA-256, installs all four real `.pyz` files, and executes every tool's self-test.

It creates:

```text
ai_program_lab/
├── code/
├── programs/
│   ├── workerhub.pyz
│   ├── verificationrunner.pyz
│   ├── workspaceinspector.pyz
│   └── smartdiff.pyz
├── tests/
├── fixtures/
├── benchmarks/
├── artifacts/
├── cache/
├── runtime/
├── logs/
└── scratch/
```

This is runtime-local scratch. If the host replaces the container/runtime, rerunning the installer restores the file-based tool layer; it does not make the host sandbox itself durable.

## Core architecture

```text
Chat AI
  -> local runtime / workspace
      -> Local Worker Hub
          -> Verification Runner
          -> Workspace Inspector
          -> Smart Diff / State Tracker
          -> future verified plugins/tools
      -> tests / fixtures / benchmarks
      -> cache / indexes / artifacts
  -> compact verified result back to the model
  -> downloadable program/artifact back to the user
```

The key distinction is **file-based capability vs. LLM-context capability**. A reusable capability can exist as an actual script, executable, fixture, index, cache, benchmark, or package instead of being regenerated as prose/code on every task.

## Preliminary ChatGPT runtime observations

Direct measurements in one ChatGPT execution environment on 2026-08-30 observed approximately:

- ~30 GiB available scratch storage during the probe
- 4 GiB effective memory ceiling
- ~4 sustained CPU cores of effective entitlement
- shared local filesystem across separate local tool calls
- local process namespace sharing
- loopback TCP and Unix-domain socket IPC
- detached-process survival across ordinary local tool calls in the tested session
- relatively expensive fresh Python startup compared with warm reuse
- no general outbound internet access from the tested local execution path

These are **empirical observations, not guaranteed OpenAI product specifications**.

## Generated artifact handoff boundary

We separately tested the maximum generated file that could be handed from the tested ChatGPT runtime to the user through the chat download path.

| Generated artifact size | User-verified result |
|---:|:---|
| 100,000,000 bytes | PASS |
| 400,000,000 bytes | PASS |
| 445,000,000 bytes | PASS |
| 449,000,000 bytes | PASS |
| 449,500,000 bytes | FAIL |
| 450,000,000 bytes | FAIL |
| 475,000,000 bytes | FAIL |
| 490,000,000 bytes | FAIL |
| 500,000,000 bytes | FAIL |
| 512,000,000 bytes | FAIL |
| 520,000,000 bytes | FAIL |

Empirical boundary from that run:

```text
449,000,000 bytes <= successful boundary < 449,500,000 bytes
```

Practical packaging rule for this measured environment: keep a single downloadable package at **400,000,000 bytes or less** for margin.

This is a **generated-file handoff benchmark**, not proof that a model can correctly author a 449 MB software project.

## Why this is worth measuring

Adjacent LLM research already demonstrates tool creation, executable skills, verification, and reusable code libraries. This project does not claim those ideas are new.

The narrower research questions are:

> **Can a general-purpose chat product's own built-in execution/storage surface be bootstrapped into a reusable local software and verification runtime without requiring a separate agent framework?**

and:

> **What are the actual runtime, persistence, build, package, and generated-artifact handoff limits of each chat product?**

Four limits should be measured separately:

1. local workspace capacity
2. user upload limit
3. generated-artifact handoff limit
4. durable storage limit

## Next tool roadmap

The next programs are prioritized by how much they strengthen the existing stack.

1. **Artifact Builder / Release Manager**
   - automate `source -> .pyz/ZIP -> SHA-256/manifest -> Verification Runner -> verified release package`
   - primary goal: eliminate source/artifact drift and repeated manual packaging

2. **Sandbox Launcher**
   - provide a strong OS sandbox backend for Verification Runner
   - primary goal: safely behavior-test native/opaque external executables instead of stopping at `BLOCKED_NEEDS_SANDBOX`

3. **Local Index / Search Engine**
   - incremental code/document/config index and relationship lookup
   - primary goal: answer repeated workspace lookup questions without rescanning everything

4. **Log / Trace Analyzer**
   - deterministic clustering and compression of large logs/traces into failure signatures and minimal evidence
   - primary goal: reduce model-visible log volume while improving reproducibility

5. **Dependency / Impact Mapper**
   - dependency/config/reference graph plus impacted-file and test candidates
   - primary goal: strengthen Smart Diff impact ranking and Verification Runner test selection

## Next benchmark experiments

- Build real 10 MB / 50 MB / 100 MB / 200+ MB program packages.
- Measure build success, tests, integrity, download success, external execution, build time, memory and scratch use.
- Measure reuse benefit versus regenerating the same utility.
- Compare equivalent ChatGPT, Claude and other chat-product runtime surfaces where fair testing is possible.
- Extend the tool layer only with verified, bounded components.

## Safety boundary

This research uses capabilities exposed by the host runtime. It does not depend on sandbox escape, hidden-service discovery, rate-limit bypass, or deliberate circumvention of platform safeguards.

## Research records

- [`research/INITIAL_FINDINGS_2026-08-30.md`](research/INITIAL_FINDINGS_2026-08-30.md)
- [`research/PUBLIC_BUILD_VERIFICATION_2026-08-30.json`](research/PUBLIC_BUILD_VERIFICATION_2026-08-30.json)
- [`research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md`](research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md)
