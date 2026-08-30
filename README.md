# Chat Local Runtime

**Experimental research project**

Chat Local Runtime studies whether general-purpose chat AIs can turn the execution and storage environments already provided by the host chat product into a reusable software layer.

> Instead of repeatedly regenerating tools inside LLM context, the chat AI builds, verifies, stores, and reuses real executable files inside its available runtime.

This is not a claim that chat sandboxes are permanent operating systems. The project measures what is actually exposed, what survives, what can be reused, and where the product boundaries are.

## Core idea

A chat product may already expose enough local capability to support a small AI-owned software workspace:

```text
Chat AI
  -> local runtime / workspace
      -> reusable validators
      -> inspectors / diff tools
      -> benchmarks
      -> indexes / caches
      -> worker processes
      -> artifact builders
      -> packaged programs
  -> compact verified result back to the model
  -> downloadable artifact back to the user
```

The important distinction is **file-based capability vs. LLM-context capability**. A verified tool can exist as an actual script, executable, fixture, index, or package rather than being regenerated as natural-language instructions on every task.

## Preliminary ChatGPT runtime observations

Direct measurements in one ChatGPT execution environment on 2026-08-30 observed approximately:

- ~30 GiB available scratch storage during the probe
- 4 GiB effective memory ceiling
- ~4 sustained CPU cores of effective entitlement
- shared local filesystem across separate local tool calls
- local process namespace sharing
- loopback TCP and Unix-domain socket IPC
- detached-process survival across ordinary local tool calls in the tested session
- expensive fresh Python startup relative to warm persistent workers
- no general outbound internet access from the tested local execution path

These are **empirical observations, not guaranteed OpenAI product specifications**. Runtime/container replacement may invalidate them.

## Reusable program workspace

The initial experimental workspace separates:

- reusable source code
- stable runnable programs
- tests
- fixtures and goldens
- benchmarks
- generated artifacts
- caches and indexes
- runtime sockets/PIDs
- logs
- disposable scratch work

Candidate reusable components include:

1. **Worker Hub** — persistent local command/worker runtime
2. **Workspace Inspector** — file tree, metadata, hashes, dependencies, entry points
3. **Smart Diff / State Tracker** — detect meaningful changes without rereading everything
4. **Verification Runner** — regression, output hash, performance and correctness checks
5. **Artifact Builder** — clean, test, package, hash and prepare downloads
6. **Local Index/Search** — machine-side retrieval with compact model-visible results
7. **External Action Adapters** — validated bridges to user-authorized external systems

## Generated artifact handoff boundary

We empirically tested how large a generated artifact could be handed from the ChatGPT runtime back to the user through the chat download path.

Observed results:

| Generated artifact size | Result |
|---:|:---|
| 400,000,000 bytes | PASS |
| 445,000,000 bytes | PASS |
| 449,000,000 bytes | PASS |
| 449,500,000 bytes | FAIL |
| 450,000,000 bytes | FAIL |
| 500,000,000 bytes | FAIL |

Current empirical boundary:

> **449,000,000 bytes succeeds; 449,500,000 bytes fails.**

For practical packaging we currently use **400,000,000 bytes or less** as a conservative single-artifact target.

### Important interpretation

This is a **generated-file handoff benchmark**, not proof that a model can correctly author a 449 MB software project.

The size-boundary test deliberately used generated binary artifacts to isolate the transport/handoff layer. Program-generation capability must be benchmarked separately with real builds, tests, packaging, download and execution verification.

The measured handoff boundary is also distinct from documented upload limits. OpenAI currently documents a 512 MB per-file upload limit for ChatGPT uploads; that does not establish the generated-artifact download boundary measured here.

## Why this is worth measuring

Existing LLM tool-use/tool-making work commonly studies whether models can:

- generate executable tools
- pass unit tests
- create reusable skill libraries
- operate in sandboxes
- reuse code across tasks

Our initial prior-art search found related work such as **LLM Tool Maker (LATM)**, **CRAFT**, **Voyager**, **ReGAL**, **TroVE**, and newer executable-agent/tool-library approaches. These establish that reusable executable capability is not itself a new idea.

The less-explored question is narrower and product-oriented:

> **Can a general-purpose chat product's own built-in execution and storage surface be bootstrapped into a reusable local verification/software runtime, without requiring a separate agent framework?**

A second under-documented question is:

> **What are the actual runtime, persistence, build, package, and generated-artifact handoff limits of each chat product?**

In the initial search we did not find a well-known public benchmark focused on product-by-product MB-scale generated-artifact handoff boundaries. This is a preliminary search result, not a claim that no such work exists anywhere.

## Four limits that must be separated

Cross-product comparisons should distinguish:

1. **Local workspace capacity** — temporary compute/storage available to the assistant
2. **Upload limit** — what the user can send into the chat
3. **Generated-artifact handoff limit** — what the assistant can return as a real downloadable file
4. **Durable storage limit** — what can persist beyond the current execution environment through officially supported storage

Conflating these produces misleading claims.

## Next benchmark: real programs

The next stage will replace empty-size transfer artifacts with real software packages.

Suggested ladder:

- 10 MB
- 50 MB
- 100 MB
- 200+ MB where practical

For every package:

1. build inside the chat-local runtime
2. run automated tests
3. verify expected output
4. package the program
5. calculate artifact size and SHA-256
6. hand the artifact to the user
7. verify successful download
8. where possible, verify execution outside the chat runtime

Metrics:

- build success
- test success
- package integrity
- download success
- external execution success
- build time
- peak memory
- scratch-space consumption
- model-visible context required
- reuse benefit vs regenerating the tool

## Cross-product direction

The project intends to compare ChatGPT, Claude, and other chat products only where equivalent capabilities can be measured fairly.

Product documentation may expose different limits at the Chat UI, API, and file-storage layers. Each surface should therefore be measured independently rather than treated as one universal product limit.

## Safety boundary

This research uses capabilities already exposed by the host runtime. It does not require sandbox escape, hidden-service access, rate-limit bypass, or deliberate circumvention of product safeguards.

## Status

Early experimental research. Measurements are reproducible checkpoints, not permanent vendor specifications.

See [`research/INITIAL_FINDINGS_2026-08-30.md`](research/INITIAL_FINDINGS_2026-08-30.md) for the first measurement record.
