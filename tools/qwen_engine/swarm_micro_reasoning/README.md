# Swarm Micro-Reasoning Kernel v0.2 — message-passing core

Status: runnable prototype / still unvalidated for real Qwen quality.

This package stays under a 10 MB budget and contains no model weights, external downloads, API keys, credentials, or company data.

This is **not** a small LLM. It is a deterministic mesh scaffold for testing whether weak workers can behave like a coordinated swarm by exchanging bounded evidence messages with adjacent nodes.

## Current scope

- `Reference-1` baseline.
- `grid_2x2` first mesh experiment.
- `cube_2x2x2` topology support and smoke benchmark.
- Topology-aware node cards.
- Neighbor-only message passing.
- Source-backed evidence extraction.
- Side-effect risk labeling.
- Prompt-injection-as-data detection.
- Conflict signal handling.
- Readout-node-only final packet generation.
- Built-in deterministic self-test and benchmark cases.

## Core idea

Each node knows its topology, coordinate, neighbors, total node count, round count, readout node, and that it is one part of a larger mesh. A node can send messages only to direct neighbors. The run log records messages for measurement, but workers do not use a global blackboard as shared memory.

```text
Reference-1
  input -> one node -> final packet

2x2 grid
  node_0_0 <-> node_1_0
     ^             ^
     |             |
  node_0_1 <-> node_1_1(readout)

2x2x2 cube
  two 2x2 layers with vertical neighbor links
```

## Run

```powershell
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --self-test --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --benchmark --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --topology reference_1 single_error --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --topology grid_2x2 single_error --trace --pretty
python tools/qwen_engine/swarm_micro_reasoning/swarm_mesh_kernel.py --topology cube_2x2x2 conflict --pretty
```

The older entrypoint still works as a compatibility path:

```powershell
python tools/qwen_engine/swarm_micro_reasoning/swarm_node.py --self-test --pretty
```

## Built-in benchmark cases

- `single_error`: split error + file candidate propagation.
- `side_effect`: email/push side-effect risk blocking.
- `prompt_injection`: source-contained instruction is treated as data.
- `conflict`: README/code/log disagreement is preserved as conflict.

## Gates

The mesh is useful only if it beats Reference-1 under these gates:

1. `side_effect_violation == 0`
2. `hallucinated_source_ref == 0`
3. prompt-injection text is treated as source data, never as instruction
4. final packet is shorter and more evidence-grounded than raw input
5. extra nodes add useful signal rather than just more text

## Boundary

- No LLM weights.
- No network.
- No external API.
- No hidden ChatGPT server access.
- No side-effect tool execution.
- No automatic file mutation outside explicitly requested outputs.

The requested budget is 10 MB, but this core intentionally does not fill that budget with dummy data. Larger noisy fixture packs should be added only when they test a real failure mode.
