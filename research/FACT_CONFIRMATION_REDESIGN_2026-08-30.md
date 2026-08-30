# Fact-confirmation redesign — 2026-08-30

## Decision

The offload layer is changing its center of gravity:

> **Programs confirm and compress deterministic facts; the AI decides what those facts mean and what to do next.**

This replaces designs that try to make small local utilities act like substitute reasoning engines.

## Applied changes

### Verification Runner v0.2.0

Verification Runner is now a fact-confirmation tool rather than a generic verdict generator.

- Functionality can be supplied as an explicit executable contract with cases for args, stdin, return code, stdout/stderr conditions and expected JSON keys.
- No functional contract naturally yields `INCONCLUSIVE` instead of a fabricated functionality PASS.
- It discovers installed validator backends and can normalize facts from `ruff`, `bandit`, `mypy`, `pytest`, and `coverage`.
- It does not auto-install missing validators. Runtime capability differences remain visible evidence rather than hidden side effects.
- Repeated verification can compare with a prior result and report newly failing, resolved, or changed facts.
- Existing static pattern indicators remain advisory evidence; they do not replace real validator output.

Observed in the tested ChatGPT code runtime: `pytest` and `coverage` are available; `ruff`, `bandit`, and `mypy` are not. This is an environment observation, not a product-wide guarantee.

Self-test: **8/8 PASS**.

A live regression demonstration produced PASS validator facts first, then detected newly introduced `pytest` and coverage failures on the second run.

### Workspace Inspector v0.1.3

Canonical content paths are now uniform regardless of the number of input roots:

```text
inputN/...
```

A path returned by `inspect` can therefore be sent unchanged to `targeted-content` for a single input as well as multiple inputs. A regression test specifically reproduces the previously missed single-input round trip.

Self-test: **15/15 PASS**.

### Smart Diff / State Tracker v0.1.1

Smart Diff is intentionally focused on comparisons where a plain `git diff` is weak or unavailable:

- parsed JSON structural changes
- TOML structural changes
- heuristic YAML structural changes
- ZIP / PYZ internal member changes
- XLSX internal package/member changes
- non-git file-tree comparisons
- auditable `importance_basis` with signals and point contributions rather than an unexplained score

Self-test: **17/17 PASS**.

### Local Worker Hub v0.1.1

No new async job system was promoted in this change.

`submit -> status -> result` for detached long-running work remains a plausible experiment, but its value depends heavily on runtime CPU entitlement and task frequency. Adding it now would expand the system before an A/B benefit is established.

## Installer v0.4.0-public

The current installer preserves historical GitHub fallback artifacts while installing the new active core from versioned `dist/active/` paths.

Key properties:

- strict `offload-ai/1` contract enforcement for the four current core tools
- Artifact Builder v0.1.1 explicitly marked as predating the shared contract rather than falsely declaring it
- source and staging hash gates
- backup-time manifest with SHA-256 fingerprints
- rollback compared against the saved backup manifest, not current expected hashes
- distinct first-install failure state when no previous installation existed
- default retention of the latest 3 backups
- machine-readable `next_action`

Installer self-test: **8/8 PASS**.

## Distribution boundary

Historical `dist/*.pyz` and installer V03 remain untouched for reproducibility. The new exact core line lives under:

```text
dist/active/
```

ChatGPT Library remains the preferred active-artifact store inside ChatGPT; GitHub remains the public reference/fallback/reconstruction layer.

## What was deliberately not claimed

- Missing validators are not described as having run.
- No contract is not described as a functionality PASS.
- A rollback is not described as restoring a previous installation when no previous files existed.
- An importance score is not presented without its basis.
- Worker Hub async execution is not promoted without workload-dependent evidence.
