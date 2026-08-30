# Feature Acceptance Gate v1 — 2026-08-30

## Problem

The existing offload lifecycle is strong at technical verification: self-tests, Hub integration, workspace inspection, semantic diff, validator-backed facts, packaging, and reciprocal dogfood. That still leaves one separate question insufficiently explicit:

> Did the newly added behavior actually fulfill the purpose the user requested?

A technically clean implementation can still be the wrong feature, an incomplete feature, or a feature whose acceptance criteria drifted after implementation.

## Decision

Add a **Feature Acceptance Gate** to substantive new-feature and behavior-changing releases. Do not add a separate reasoning program.

The split remains:

> **Programs confirm and compress deterministic facts; the AI decides what those facts mean and what to do next.**

The gate has four parts:

1. **Locked Feature Acceptance Contract** before implementation.
2. **Verification Runner acceptance facts** produced from executable scenarios and referenced evidence.
3. **AI intent assessment** against the original purpose.
4. **Artifact Builder release gate** that blocks release unless the locked contract, facts, and intent assessment agree.

## Contract

Schema: `offload-feature-acceptance/1`

Core fields:

- `purpose`: why the feature exists.
- `requirements`: `MUST_WORK`, `MUST_NOT`, and failure-behavior requirements.
- `scenarios`: executable acceptance scenarios.
- `evidence_files`: deterministic evidence produced elsewhere when appropriate.
- `locked_sha256`: SHA-256 of the canonical contract excluding the lock field itself.

The contract SHA must also be pinned in the task/controller state **before implementation starts**. The file's own `locked_sha256` is tamper evidence, not a substitute for an external pre-implementation pin. The CI workflow independently asserts the three expected contract hashes before running implementation acceptance.

If the canonical contract no longer matches the pinned value, the implementation is not accepted. A passing implementation cannot silently relax its own acceptance criteria without changing the externally visible pin.

## Verification Runner v0.3.0 candidate

Repository-rebuilt candidate SHA-256:

`0d01fb6c834f117f4c2025b00764e755ec8ffa678b8fd7791df3f59dcd73aebc`

Changes:

- adds `acceptance <target> --contract <contract.json>`;
- executes acceptance scenarios in isolated temporary work directories;
- supports args/stdin/env/precreated fixtures, return-code/stdout/stderr/JSON/file assertions;
- can incorporate explicitly named JSON evidence files;
- returns scenario/evidence/requirement facts rather than an intent verdict;
- returns `AI_ASSESS_INTENT` after fact acceptance passes;
- preserves the fact-confirmation rule: no functional contract => `INCONCLUSIVE`, not fabricated functionality PASS;
- rejects locked-contract drift.

Self-test: **8/8 PASS** in GitHub Actions.

## Artifact Builder / Release Manager v0.1.2 candidate

Repository-rebuilt candidate SHA-256:

`cb86838cc7419d6d49ab9a3e29f8664af144fcdb5aa1cfad9e67b0eec94abc4d`

When `--require-feature-acceptance` is used, final release is blocked unless all of the following hold:

- a locked Feature Acceptance Contract is present and unchanged;
- acceptance evidence refers to the same contract hash;
- acceptance facts are `PASS`;
- an `offload-feature-intent-assessment/1` record is present;
- the assessment is `SATISFIED` for the same contract hash;
- the assessment cites passing requirement IDs.

Missing contract, contract drift, failing/inconclusive acceptance, missing assessment, or unsatisfied intent => **BLOCK**.

Self-test: **8/8 PASS** in GitHub Actions.

## First dogfood targets

### Verification Runner itself

Purpose: confirm requested deterministic functionality/acceptance facts without taking over AI intent judgment.

Feature Acceptance Contract SHA-256:

`3bc51a091145251cb25b244b8ac794d4ada8e33f692fc0035267638af1bf592e`

Acceptance: **PASS**.

### Artifact Builder itself

Purpose: make Feature Acceptance a release condition instead of an optional note.

Feature Acceptance Contract SHA-256:

`0f37cc80390d99bafdadde90140bcbb9bd9f32aa7b109268380e7fd99814d3ce`

Acceptance: **PASS**. Intent-gated self-host release: **RELEASE**.

### Sandbox Launcher v0.1.1 retro-acceptance

Purpose: strong OS sandbox execution for native/opaque executables and Python `.pyz`, with network/host mutation blocked, timeout/resource limits, and no silent weak fallback.

Feature Acceptance Contract SHA-256:

`a91ee889346303143123fe03ee10013120e094def9394bb0f513b6c80525a307`

The acceptance contract combines a live exact-artifact self-test with the already recorded integrated security evidence (`SANDBOX_LAUNCHER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json`). GitHub Actions executed the exact mirrored Sandbox artifact with sudo; self-test returned **13/13 PASS** and the recorded security evidence matched the contract requirements.

This retro-acceptance does **not** override the separate current-active-core compatibility blocker recorded in `SANDBOX_LAUNCHER_LATEST_CORE_REVALIDATION_2026-08-30.json`.

## Repository CI checkpoint

Pull request #1 candidate validation run `33318727368` completed **PASS** on Ubuntu 24.04 / Python 3.12.

The passing sequence included:

- deterministic rebuild of Verification Runner and Artifact Builder candidates;
- candidate self-tests;
- locked contract-hash checks;
- Verification Runner self-acceptance;
- Artifact Builder acceptance;
- Artifact Builder functional verification;
- Artifact Builder AI-intent-gated release;
- Sandbox Launcher retro feature acceptance;
- historical Worker Hub real plugin invocation of Verification Runner v0.3.0;
- reciprocal Artifact Builder dogfood over the existing GitHub fallback tools plus Sandbox Launcher.

## Distribution boundary

The new candidate `.pyz` files are rebuilt from source in CI and checked against the repository-rebuilt candidate hashes above. They are **candidate artifacts, not active artifacts**.

`dist/active/` remains metadata-only because exact current active generated artifacts are Library-first. This change does not fabricate or replace unavailable exact active Library binaries.

A complete six-tool active install/verify is **not claimed yet**, because the exact current active Worker Hub / Workspace Inspector / Smart Diff Library artifacts are not materialized in this chat runtime. That remains a blocking completion condition rather than a skipped check.

## Lifecycle after this change

```text
user intent
  -> write Feature Acceptance Contract
  -> pin contract SHA outside the implementation
  -> implement
  -> Hub / Inspector / Smart Diff as applicable
  -> Verification Runner technical facts + Feature Acceptance facts
  -> AI intent assessment
  -> Artifact Builder acceptance-gated release
  -> fix + full clean rerun
  -> reciprocal dogfood
  -> COMPLETE / ACTIVE only when every applicable gate passes
```

## Candidate status

- Verification Runner v0.3.0 self-test: **8/8 PASS**
- Artifact Builder v0.1.2 self-test: **8/8 PASS**
- Verification Runner self-acceptance: **PASS**
- Artifact Builder acceptance: **PASS**
- Artifact Builder functional verification: **PASS_WITH_INCONCLUSIVE_GATES**; unprovided performance validation remains explicit rather than fabricated
- Artifact Builder intent-gated release: **RELEASE**
- Sandbox Launcher retro feature acceptance: **PASS**
- Hub smoke integration: **PASS**
- Reciprocal Artifact Builder dogfood: **PASS**

The Feature Acceptance mechanism is repository-CI validated. Promotion of new candidate tool versions to the exact active Library stack remains a separate gate.
