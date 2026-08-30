# Feature Acceptance contracts

`offload-feature-acceptance/1` locks the purpose and executable evidence required for a substantive feature or behavior change.

- `*_feature_acceptance.json`: immutable acceptance target for the implementation cycle. `locked_sha256` is calculated from the canonical JSON with that field omitted.
- `*_functional.json`: lower-level executable functionality contract used by Verification Runner where needed.
- `*_intent_assessment.json`: AI judgment after deterministic acceptance facts are available. The program does not create this judgment for itself.

A required feature release is blocked when the contract is missing or changed, acceptance facts do not pass, or the intent assessment is absent/not satisfied.
