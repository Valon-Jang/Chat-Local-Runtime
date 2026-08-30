# Feature Acceptance contracts

`offload-feature-acceptance/1` locks the purpose and executable evidence required for a substantive feature or behavior change.

- `*_feature_acceptance.json`: acceptance target written before implementation. `locked_sha256` is calculated from the canonical JSON with that field omitted.
- `*_functional.json`: lower-level executable functionality contract used by Verification Runner where needed.
- `*_intent_assessment.json`: AI judgment made after deterministic acceptance facts are available. The program does not create this judgment for itself.

## Lock rule

The contract SHA must also be pinned in task/controller state before implementation starts. The hash inside the contract is tamper evidence; the externally retained pre-implementation SHA is the authority used to detect a contract and lock being rewritten together.

A required feature release is blocked when the pinned contract changes, acceptance facts do not pass, or the intent assessment is absent/not satisfied.
