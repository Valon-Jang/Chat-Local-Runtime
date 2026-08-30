# Initial Findings — 2026-08-30

Status: Experimental measurement checkpoint

## 1. Research target

This project investigates whether the execution/storage surface already exposed inside a general-purpose chat product can be used as a reusable software and verification runtime.

The key distinction is between:

- **LLM-context tools** — instructions or code repeatedly regenerated inside model context
- **file-based tools** — actual scripts, executables, fixtures, caches, indexes, benchmarks, and packages stored in the runtime and reused

The current work focuses first on ChatGPT, then on comparable chat products where equivalent execution/file capabilities exist.

## 2. ChatGPT local runtime profile observed

The tested local execution environment exposed:

- Debian 13.3 x86_64 sandbox
- ~30 GiB available scratch storage at measurement time
- 4 GiB effective cgroup memory ceiling
- 5 logical CPUs visible with ~4 CPUs of sustained aggregate entitlement
- no usable GPU
- shared `/mnt/data` filesystem between local execution paths
- local process namespace sharing
- loopback TCP and Unix-domain socket support
- local detached-process reuse across ordinary tool calls in the tested session
- no general external internet egress from the tested local path

Fresh Python process startup was relatively expensive, making persistent local workers attractive for repeated short tasks.

These values are observations of one runtime instance and must not be presented as guaranteed platform specifications.

## 3. Program-lab workspace

A reusable development/test workspace was created at the time of the experiment with this logical contract:

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

The workspace smoke test verified basic directory existence plus write/read/delete behavior.

Because the runtime is not guaranteed durable, the workspace must be recreated if the execution environment is replaced. Durable source should be exported to persistent storage when required.

## 4. Generated artifact download experiment

### Goal

Measure the largest generated file that the current ChatGPT chat surface could hand back to the user through the normal downloadable-artifact path.

This isolates **artifact handoff capacity**. It does not measure software-authoring quality.

### Method

Generated sparse binary files of known exact byte size inside the local runtime and surfaced them as downloadable chat artifacts. The user manually attempted each download and reported success/failure.

### Observations

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

Empirical boundary from this run:

```text
449,000,000 bytes <= successful boundary < 449,500,000 bytes
```

### Practical rule

Use **<= 400,000,000 bytes** for a conservative single downloadable package in this environment.

If a real build exceeds that target, split the package or separate executable/source/resources/dependencies rather than targeting the measured edge.

## 5. Interpretation boundary

The following claims are supported:

- The tested ChatGPT runtime could generate and expose large local files.
- A 449,000,000-byte generated artifact was successfully downloaded by the user.
- A 449,500,000-byte generated artifact failed in the same experiment.
- The measured generated-artifact handoff boundary differs from the commonly documented 512 MB ChatGPT upload ceiling.

The following claims are **not** supported yet:

- ChatGPT can correctly author a 449 MB real software project.
- The 449–449.5 MB boundary is permanent across sessions, clients, accounts, or future product versions.
- The boundary reflects a documented OpenAI guarantee.
- Equivalent limits apply to Claude or any other chat product.

## 6. Prior-art positioning

Initial searching found strong adjacent prior art on executable tool creation and reuse, including LLM Tool Maker (LATM), CRAFT, Voyager, ReGAL, TroVE, and agent/tool-library systems.

Therefore this project should **not** claim that "LLMs can create and reuse tools" is novel.

The narrower research direction is:

> Can a general-purpose chat product's own built-in execution/storage environment become a reusable local software/verification runtime, and what are its measurable capacity and handoff boundaries?

A related benchmark question is:

> How large a real program can each chat product build, verify, package, and successfully hand to the user?

The initial search did not identify a well-known benchmark dedicated to MB-scale generated-artifact handoff thresholds across chat products. This remains a provisional prior-art observation.

## 7. External product notes

Product limits must be compared carefully because chat UI, API, uploaded-file, generated-file, and persistent-storage surfaces can have different limits.

For example, Anthropic documentation has described file creation/editing limits for Claude Chat that are distinct from its API Files limits. Such documented limits should not be mixed with our ChatGPT empirical runtime measurement without equivalent tests.

## 8. Next experiment

Replace sparse transfer-test binaries with actual software packages.

Candidate ladder:

- 10 MB real program
- 50 MB real program
- 100 MB real program
- 200+ MB real program if justified

For each package measure:

- build success
- automated test success
- functional correctness
- output/package SHA-256
- package size
- local build time
- scratch-space use
- peak memory
- download success
- execution after download where testable
- model-visible context required

This will separate **transport capacity** from **real program construction capability**.

## 9. Runtime architecture direction

Candidate software layer:

```text
Chat model
   |
   v
Worker Hub
   |-- Workspace Inspector
   |-- Verification Runner
   |-- Smart Diff / State Tracker
   |-- Artifact Builder
   |-- Local Index/Search
   |-- reusable deterministic tools
   `-- validated external-action adapters
```

The long-term hypothesis is that repeated deterministic work can move into verified file-based programs while the model retains judgment, exception handling, and final decision responsibility.

## 10. Safety / product-boundary rule

Use only capabilities exposed by the host product/runtime. This research does not depend on sandbox escape, hidden-service discovery, rate-limit bypass, or deliberate circumvention of platform safeguards.
