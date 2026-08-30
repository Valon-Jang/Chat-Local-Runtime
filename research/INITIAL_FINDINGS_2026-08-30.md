# Initial Findings — 2026-08-30

Status: Experimental measurement and implementation checkpoint

## Research target

This project investigates whether execution/storage already exposed inside a general-purpose chat product can be used as a reusable software and verification runtime.

The central distinction is:

- **LLM-context capability** — instructions/code repeatedly generated inside model context
- **file-based capability** — actual scripts, executables, fixtures, caches, indexes, benchmarks and packages stored and reused by the runtime

## ChatGPT local runtime profile observed

One tested ChatGPT execution environment exposed approximately:

- Debian 13.3 x86_64 sandbox
- ~30 GiB available scratch storage at measurement time
- 4 GiB effective cgroup memory ceiling
- ~4 CPUs of sustained aggregate entitlement
- no usable GPU
- shared `/mnt/data` filesystem between local execution paths
- local process namespace sharing
- loopback TCP and Unix-domain socket support
- detached-process reuse across ordinary tool calls in the tested session
- no general external internet egress from the tested local path

These values are measurements of one runtime instance, not vendor guarantees.

## File-based tool layer implemented

The experiment progressed beyond a proposed architecture: four reusable programs now exist as real `.pyz` artifacts.

### Local Worker Hub `0.1.1-public`

AI-first one-shot local offload engine. Standard-library only. It provides compact JSON operations for inspect/hash/search, bounded allowlisted commands and external plugin invocation. Hub-owned network access is disabled by design.

Public rebuild self-test: **7/7 PASS**.

### Verification Runner `0.1.1-public`

AI-first program verifier. It fingerprints targets, performs bounded static inspection, executes supported Python self-tests, and refuses to directly execute opaque/native binaries without a strong OS sandbox.

Public rebuild self-test: **5/5 PASS**.

### Workspace Inspector `0.1.2-public`

Metadata-first workspace preprocessor for AI use. It produces compact structure, important-file ranking, exact duplicate information, anomaly/read-plan signals and targeted-content access while blocking sensitive-file content.

Public rebuild self-test: **14/14 PASS**.

### Smart Diff / State Tracker `0.1.0-public`

Semantic change tracker for code/config/document workspaces. It detects additions/removals, exact renames and bulk restructuring; Python signature/body/import changes; JSON value changes with secret redaction; Markdown structure/content changes; and impact candidates.

Public rebuild self-test: **15/15 PASS**.

### Integrated ChatGPT installer

`installers/INSTALL_CHATGPT_FROM_REPO.py` recreates the standard `/mnt/data/ai_program_lab` workspace from an unpacked repository, verifies the SHA-256 of all four executable artifacts, installs them under `programs/`, and runs every self-test.

A fresh installation and a separate verify pass both returned overall **PASS**.

The public verification output is recorded in `PUBLIC_BUILD_VERIFICATION_2026-08-30.json`.

### Reconstruction boundary

The original private scratch binaries from earlier development were not durable and were no longer present after runtime replacement. The repository artifacts are therefore explicitly labeled `-public`: they are reference rebuilds from the recorded behavior/specification checkpoint and were freshly validated. They are not represented as byte-identical historical artifacts.

## Program-lab workspace

The standard runtime-local workspace is:

```text
ai_program_lab/
├── code/
├── programs/
├── tests/
├── fixtures/
├── benchmarks/
├── artifacts/
├── cache/
├── runtime/
├── logs/
└── scratch/
```

The sandbox is not durable storage; a fresh runtime can recreate this contract by rerunning the installer.

## Generated artifact handoff experiment

Sparse binaries of exact byte size were generated inside the local runtime and exposed through the normal downloadable-artifact path. The user manually attempted each download.

| Exact generated size | User-verified result |
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

Empirical boundary:

```text
449,000,000 bytes <= successful boundary < 449,500,000 bytes
```

Practical single-artifact target: **<= 400,000,000 bytes**.

This measures transport/handoff capacity, not software-authoring quality.

## Interpretation boundary

Supported by current evidence:

- the tested ChatGPT runtime can host reusable executable files
- multiple AI-first tools can be built, self-tested and reinstalled as real files
- an installer can recreate the runtime-local tool layer without network access once the repository artifacts are available locally
- a 449,000,000-byte generated artifact was successfully downloaded in the measured run
- a 449,500,000-byte generated artifact failed in the same experiment

Not yet supported:

- that ChatGPT can correctly author a 449 MB real application
- that the runtime or handoff limits are stable across sessions/accounts/clients/product versions
- that equivalent limits apply to other chat products
- that the public rebuild is byte-identical to the earlier private scratch artifacts

## Prior-art positioning

Adjacent work on LLM tool making and reusable executable capability includes LATM/LLM Tool Maker, CRAFT, Voyager, ReGAL, TroVE and other agent/tool-library systems. Therefore the project does not claim that LLM-created reusable tools are novel.

The narrower research direction is:

> Can the execution/storage surface already present in a general-purpose chat product become a reusable local software/verification runtime, and what are its measurable capacity and handoff boundaries?

A related benchmark question is:

> How large a real program can each chat product build, verify, package and successfully hand to the user?

## Next benchmark

Replace sparse transfer-test binaries with actual software packages and measure:

- build success
- automated test success
- functional correctness
- SHA-256/package integrity
- package size
- build time
- scratch-space use
- peak memory
- download success
- external execution success where testable
- model-visible context required
- reuse benefit versus regeneration

## Safety / product boundary

Use only capabilities exposed by the host product/runtime. This work does not depend on sandbox escape, hidden-service discovery, rate-limit bypass, or deliberate circumvention of platform safeguards.
