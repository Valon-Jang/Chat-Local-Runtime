# Chat Local Runtime

**Experimental research project**

Chat Local Runtime studies whether a general-purpose chat AI can turn execution and storage surfaces already exposed by the host product into a reusable file-based software layer.

> **Programs confirm and compress deterministic facts so the AI can decide the next action.**

The project does **not** treat chat sandboxes as permanent operating systems, and small local tools are not intended to replace model reasoning.

## Current active stack

| Tool | Version | Role | Self-test |
|---|---:|---|---:|
| Local Worker Hub | `0.1.1` | deterministic execution foundation / plugin routing | PASS |
| Verification Runner | `0.2.0` | contract- and validator-backed fact confirmation | 8/8 PASS |
| Workspace Inspector | `0.1.3` | metadata-first preprocessing and canonical targeted reading | 15/15 PASS |
| Smart Diff / State Tracker | `0.1.1` | structural / artifact / non-git semantic comparison | 17/17 PASS |
| Artifact Builder / Release Manager | `0.1.1` | deterministic build, SHA/manifest, verification gating and packaging | 16/16 PASS |

Exact current core hashes are recorded in [`dist/active/ACTIVE_MANIFEST.json`](dist/active/ACTIVE_MANIFEST.json) and [`dist/active/SHA256SUMS.txt`](dist/active/SHA256SUMS.txt).

### Important distribution note

The exact current `.pyz` files are **not embedded under `dist/active/`**. During this session, direct binary upload through the available GitHub connector was read back as truncated 7,500-byte files, so publishing those files as valid active binaries would be false.

Therefore the storage model is deliberately split:

```text
ChatGPT Library
  -> exact active generated artifacts

GitHub Chat-Local-Runtime
  -> public docs / expected hashes / installer / historical fallback / research history
```

Older `dist/*.pyz` public fallback builds and installer V03 remain untouched for reproducibility.

## Verification Runner v0.2.0 — fact confirmation first

The runner now produces evidence rather than pretending to own the final judgment.

- explicit executable functionality contracts: args, stdin, return code, stdout/stderr conditions, expected JSON keys
- **no functionality contract => `INCONCLUSIVE`**, not fabricated PASS
- discovery and normalized output for installed `ruff`, `bandit`, `mypy`, `pytest`, and `coverage`
- missing validators remain explicitly unavailable; the runner never auto-installs them
- repeated verification can report newly failing, resolved, and changed facts relative to a prior result
- static pattern indicators remain advisory evidence rather than substitutes for actual validators

In one tested ChatGPT runtime on 2026-08-30, `pytest` and `coverage` were available while `ruff`, `bandit`, and `mypy` were not. This is an empirical environment observation, not a platform-wide guarantee.

## Workspace Inspector v0.1.3

Canonical relative content references always use:

```text
inputN/...
```

This rule now applies even for a single input root. A path returned by `inspect` can be passed unchanged into `targeted-content`. The previously missed single-input failure is now a permanent regression test.

## Smart Diff v0.1.1

Smart Diff is focused where a normal `git diff` is weak or unavailable:

- JSON structural key/value changes
- TOML structural changes
- heuristic YAML structural changes
- ZIP / PYZ internal member changes
- XLSX internal package/member changes
- non-git file-tree comparisons
- auditable `importance_basis` with the signals and point contributions behind the score

## Local Worker Hub v0.1.1

The Hub stays unchanged for now. A detached async API such as:

```text
submit -> status -> result
```

remains a candidate experiment, but it is **not promoted without workload-dependent A/B evidence**. Its value can vary sharply with runtime CPU entitlement and how often long-running jobs actually occur.

## Current installer — v0.4.1-public

The current installer is a **Library-to-runtime bridge**. It does not pretend GitHub can fetch ChatGPT Library internally and does not depend on a hidden Library API.

First select/extract the active Library bundle into a local directory, then run:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py install \
  --artifact-dir /path/to/extracted/library-bundle
```

Verify the selected active artifacts before installation:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py source-verify \
  --artifact-dir /path/to/extracted/library-bundle
```

Verify an existing installed layer:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py verify
```

Run installer regression tests:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V04.py self-test
```

Installer v0.4.1 properties:

- exact SHA-256 gate for all four active core files
- strict `offload-ai/1` contract enforcement
- staging hash gate before replacement
- backup-time manifest records actual previous hashes
- rollback is verified against the backup-time manifest, **not the new expected hashes**
- no previous installation => distinct `NO_PREVIOUS_INSTALL_REMOVED`
- latest 3 backups retained by default
- missing `--artifact-dir` => `SELECT_LIBRARY_ARTIFACT_BUNDLE`
- stable machine-readable `next_action`

Installer self-test: **8/8 PASS**.

Historical V03 remains available for the older repository-embedded public fallback build:

```bash
python installers/INSTALL_CHATGPT_FROM_REPO_V03.py install
```

## Artifact Builder / Release Manager v0.1.1

Artifact Builder automates:

```text
source
  -> deterministic .pyz / ZIP
  -> SHA-256 + file manifest
  -> verification evidence
  -> BLOCK / RELEASE_WITH_WARNINGS / RELEASE
  -> final release package
```

Verified SHA-256:

```text
1677f84252d0e275f0448426ac6702318ad30589c462493aea533e1ddfe63c3a
```

Its historical exact binary is stored as `dist/artifactbuilder.pyz.part01` ... `part05` and can be reconstructed with final SHA verification.

## Validation lifecycle

A new or updated program is not considered complete just because it builds or passes its own self-test.

```text
candidate
  -> Worker Hub integration where meaningful
  -> Workspace Inspector
  -> Smart Diff when a trustworthy comparison exists
  -> Verification Runner with explicit contract / available real validators
  -> Artifact Builder / Release Manager
  -> reproduce discovered defects in permanent regression tests
  -> reciprocal dogfood against affected existing tools
  -> COMPLETE
```

A technically inapplicable step can be skipped, but the skip is explicit rather than silently converted into PASS.

## Architecture

```text
Chat AI
  -> local runtime / workspace
      -> Local Worker Hub
          -> Workspace Inspector        # what is here?
          -> Smart Diff / State Tracker # what actually changed?
          -> Verification Runner        # what facts are confirmed?
          -> Artifact Builder           # what exact artifact is releasable?
      -> compact structured evidence
  -> AI judgment / next action
```

## Preliminary runtime observations

One tested ChatGPT execution environment on 2026-08-30 showed approximately:

- ~30 GiB available scratch storage during the probe
- 4 GiB effective memory ceiling
- ~4 sustained CPU cores of effective entitlement
- shared local filesystem across local tool calls
- loopback TCP and Unix-domain socket IPC
- detached-process survival across ordinary local tool calls in that session
- no general outbound internet access from that tested local execution path

These are empirical observations, **not guaranteed OpenAI product specifications**.

User-verified generated-file handoff from that experiment showed:

```text
449,000,000 bytes <= successful boundary < 449,500,000 bytes
```

The practical packaging rule used in that experiment was 400,000,000 bytes or less per downloadable package for margin.

## Next tool roadmap

1. **Sandbox Launcher** — strong OS sandbox backend for native/opaque external executable verification.
2. **Local Index / Search Engine** — incremental code/document/config index and relationship lookup.
3. **Log / Trace Analyzer** — deterministic failure clustering and compact evidence extraction.
4. **Dependency / Impact Mapper** — dependency/config/reference graph and impacted-file/test candidates.
5. **Worker Hub async job experiment** — only if A/B testing shows material blocking-work reduction.

## Research records

- [`research/INITIAL_FINDINGS_2026-08-30.md`](research/INITIAL_FINDINGS_2026-08-30.md)
- [`research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md`](research/LIBRARY_FIRST_STORAGE_AND_TOOL_ROADMAP_2026-08-30.md)
- [`research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json`](research/ARTIFACT_BUILDER_V0.1.1_INTEGRATED_VERIFICATION_2026-08-30.json)
- [`research/FACT_CONFIRMATION_REDESIGN_2026-08-30.md`](research/FACT_CONFIRMATION_REDESIGN_2026-08-30.md)
