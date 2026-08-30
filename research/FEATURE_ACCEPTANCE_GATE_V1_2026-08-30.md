# Feature Acceptance Gate v1 — 2026-08-30

## Problem

The existing offload lifecycle is strong at technical verification: self-tests, Hub integration, workspace inspection, semantic diff, validator-backed facts, packaging, and reciprocal dogfood. That still leaves one separate question insufficiently explicit:

> Did the newly added behavior actually fulfill the purpose the user requested?

A technically clean implementation can still be the wrong feature, an incomplete feature, or a feature whose acceptance criteria drifted after implementation.

## Decision

Add a **Feature Acceptance Gate** to substantive new-feature and behavior-changing releases. Do not add a separate reasoning program.

The split remains:

> **Programs confirm and compress deterministic facts; the AI decides what those facts mean and what to do next.**

The gate therefore has four parts:

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

If the canonical contract no longer matches `locked_sha256`, acceptance fails as `ACCEPTANCE_CONTRACT_CHANGED`. A passing implementation cannot silently relax its own acceptance criteria.

## Verification Runner v0.3.0 candidate

Candidate SHA-256:

`2df3fd1844e1697386fd6aba611570b3b77b6cf926c50e51b3badbd727b5a786`

Changes:

- adds `acceptance <target> --contract <contract.json>`;
- executes acceptance scenarios in isolated temporary work directories;
- supports args/stdin/env/precreated fixtures, return-code/stdout/stderr/JSON/file assertions;
- can incorporate explicitly named JSON evidence files;
- returns scenario/evidence/requirement facts rather than an intent verdict;
- returns `AI_ASSESS_INTENT` after fact acceptance passes;
- preserves the fact-confirmation rule: no functional contract => `INCONCLUSIVE`, not fabricated functionality PASS;
- rejects locked-contract drift.

Self-test: **8/8 PASS** locally.

## Artifact Builder / Release Manager v0.1.2 candidate

Candidate SHA-256:

`4a302190f38450cdf0f672c5c8c2b9961ce0d4fc265f4798c06218711b51ccfb`

When `--require-feature-acceptance` is used, final release is blocked unless all of the following hold:

- a locked Feature Acceptance Contract is present and unchanged;
- acceptance evidence refers to the same contract hash;
- acceptance facts are `PASS`;
- an `offload-feature-intent-assessment/1` record is present;
- the assessment is `SATISFIED` for the same contract hash;
- the assessment cites passing requirement IDs.

Missing contract, contract drift, failing/inconclusive acceptance, missing assessment, or unsatisfied intent => **BLOCK**.

Self-test: **8/8 PASS** locally.

## First dogfood targets

### Verification Runner itself

Purpose: confirm requested deterministic functionality/acceptance facts without taking over AI intent judgment.

Feature Acceptance Contract SHA-256:

`3bc51a091145251cb25b244b8ac794d4ada8e33f692fc0035267638af1bf592e`

Local acceptance: **PASS**.

### Artifact Builder itself

Purpose: make Feature Acceptance a release condition instead of an optional note.

Feature Acceptance Contract SHA-256:

`0f37cc80390d99bafdadde90140bcbb9bd9f32aa7b109268380e7fd99814d3ce`

Local acceptance: **PASS**. Intent-gated self-host release: **RELEASE**.

### Sandbox Launcher v0.1.1 retro-acceptance

Purpose: strong OS sandbox execution for native/opaque executables and Python `.pyz`, with network/host mutation blocked, timeout/resource limits, and no silent weak fallback.

Feature Acceptance Contract SHA-256:

`a91ee889346303143123fe03ee10013120e094def9394bb0f513b6c80525a307`

The acceptance contract combines a live exact-artifact self-test with the already recorded integrated security evidence (`SANDBOX_LAUNCHER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json`). This retro-acceptance does **not** override the separate current-active-core compatibility blocker recorded in `SANDBOX_LAUNCHER_LATEST_CORE_REVALIDATION_2026-08-30.json`.

## Distribution boundary

The new candidate `.pyz` files are rebuilt from source in CI and checked against the candidate hashes above. They are **candidate artifacts, not active artifacts**.

`dist/active/` continues to hold active identity metadata only. Exact active artifacts remain Library-first.

## Installer v0.5.0 candidate

`INSTALL_CHATGPT_FROM_REPO_V05.py` is a Library-to-runtime bridge for the proposed six-tool composition. It records the acceptance contract identities and expects an explicit local artifact directory containing exact bytes.

Its own regression self-test is **8/8 PASS** locally.

A complete six-tool active install/verify is **not claimed yet**, because the exact current active Worker Hub / Workspace Inspector / Smart Diff Library artifacts are not materialized in this chat runtime. That remains a blocking completion condition rather than a skipped check.

## Proposed lifecycle after this change

```text
user intent
  -> lock Feature Acceptance Contract
  -> implement
  -> Hub / Inspector / Smart Diff as applicable
  -> Verification Runner technical facts + Feature Acceptance facts
  -> AI intent assessment
  -> Artifact Builder acceptance-gated release
  -> fix + full clean rerun
  -> reciprocal dogfood
  -> COMPLETE / ACTIVE only when every applicable gate passes
```

## Local candidate checkpoint

- Verification Runner v0.3.0 self-test: **8/8 PASS**
- Artifact Builder v0.1.2 self-test: **8/8 PASS**
- Installer v0.5.0 candidate self-test: **8/8 PASS**
- Verification Runner self-acceptance: **PASS**
- Artifact Builder acceptance: **PASS**
- Artifact Builder functional verification: **PASS** with non-applicable/unprovided gates remaining explicit rather than fabricated
- Artifact Builder intent-gated release: **RELEASE**

Promotion remains conditional on repository CI and, separately, exact Library active-stack materialization for the full active six-tool lifecycle.
