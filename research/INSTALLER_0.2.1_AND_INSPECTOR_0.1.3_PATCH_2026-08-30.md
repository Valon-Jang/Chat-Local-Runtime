# Installer 0.2.1 / Workspace Inspector 0.1.3 patch — 2026-08-30

## Why this patch exists

A review of installer 0.2.0-public found three correctness gaps:

1. `ai_contract_version` looked enforced even though missing declarations were accepted.
2. `install-backup-*` directories accumulated without retention.
3. rollback verification compared the restored files to the *current installer* hashes instead of the hashes captured from the previous installation.

The same review also identified a Workspace Inspector contract inconsistency: the documented canonical form was `inputN/...`, but the public build used that prefix only for multi-input runs. The single-input path therefore did not follow one canonical rule.

## Installer 0.2.1-public

Changes:

- Contract policy is now explicit:
  - `contract_policy.enforced = false`
  - `contract_policy.status = NOT_ENFORCED`
  - per-tool `contract_observation = MISSING | MATCH | MISMATCH`
  - contract metadata is **not** presented as a PASS gate until all public tools declare it.
- Tool public version is now checked against the version reported by self-test/capabilities.
- Backup creation records a `backup-manifest.json` containing the actual pre-install existence and SHA-256 of every managed file.
- Rollback verifies against that backup manifest, not against the new installer's expected hashes.
- First-install failure is reported as `NO_PREVIOUS_INSTALL_REMOVED`, not `ROLLED_BACK_TO_PREVIOUS_INSTALL`.
- Rollback failure is reported as `ROLLBACK_FAILED_REVIEW_REQUIRED`.
- Backup retention defaults to the newest 3 backups and is configurable with `--keep-backups`.
- Installer adds a machine-readable `self-test` command covering the previously missed failure cases.

### Installer regression test

Local isolated self-test:

```text
5/5 PASS
```

Cases:

- missing contract is explicitly reported as not enforced
- corrupted source leaves existing installation untouched
- hash-valid candidate with failing self-test restores exact previous bytes using backup-manifest hashes
- failed first install removes the candidate and reports no previous installation
- backup retention keeps only the configured newest N backups

## Workspace Inspector 0.1.3-public

Canonical path behavior is now:

```text
inputN/relative/path
```

for **every** input count, including a single input.

`targeted-content` requires the same canonical form, so the path returned by `inspect` can be passed back unchanged.

This also removes the ambiguity around a real directory named `input0`: such a directory under the first root is represented as `input0/input0/...`.

### Regression test added

The self-test now explicitly runs:

```text
single input inspect
  -> receive input0/README.md
  -> pass that exact path to targeted-content
  -> OK
```

Result:

```text
15/15 PASS
```

An additional live probe reproduced the same round trip with a temporary one-file workspace and returned `status=OK`.

## Updated artifact

`dist/workspaceinspector.pyz`

- version: `0.1.3-public`
- SHA-256: `c4e95ebb291702993dc196c930a63c113beced193dd984cf47ee489303031c85`
- bytes: `3863`

The other three public `.pyz` artifacts are unchanged from the prior verified public build.

## Verification scope

Impact-based verification was used:

- Installer changed: new isolated installer regression suite 5/5 PASS.
- Workspace Inspector changed: rebuilt artifact self-test 15/15 PASS plus explicit single-input live round-trip PASS.
- Local Worker Hub, Verification Runner and Smart Diff binaries were not modified; their prior public-build verification remains the applicable baseline.

The installer contract remains intentionally **not enforced** until a future coordinated artifact build adds the same declared AI contract to all public tools.
