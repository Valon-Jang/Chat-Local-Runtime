# Built-in swarm cases

`swarm_mesh_kernel.py` embeds the first benchmark cases so the core can run without extra fixture files.

Current built-in cases:

- `single_error`: split error + file candidate propagation.
- `side_effect`: email/push side-effect risk blocking.
- `prompt_injection`: source-contained instruction is treated as data.
- `conflict`: README/code/log disagreement is preserved as conflict.

External fixture files can still be passed as the positional case path. Keep larger noisy fixture packs outside the core unless they test a real failure mode.
