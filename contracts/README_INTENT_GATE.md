# Intent judgment boundary

Feature Acceptance facts are deterministic evidence. The tool layer does not decide whether the user's original intent was fulfilled.

After acceptance facts pass, the AI records an `offload-feature-intent-assessment/1` decision. Artifact Builder can then enforce that assessment as a release prerequisite.
