# Swarm Micro-Reasoning Kernel v0.1 — Reference-1 Prototype

Status: design/prototype. This package stays under a 10 MB budget and contains no model weights, external downloads, API keys, or company data.

## Goal

The first test is recognition, not intelligence:

- Does a node know whether it is `Reference-1` or part of a mesh?
- Does it know its coordinate, neighbors, round, readout node, and final-output authority?
- Does it refuse unsupported conclusions?
- Does it keep source-backed evidence separate from unsupported claims?
- Does it flag side-effect risk before any execution decision?

## Current scope

`swarm_node.py` is a dependency-free deterministic micro-kernel. It can operate as:

1. `Reference-1` single node, which may produce one final packet.
2. A non-readout mesh node, which must only emit neighbor messages and must not produce the final packet.

The next expansion should be a real `2x2` mesh scheduler that runs four nodes through multiple message-passing rounds.

## Run

```powershell
python tools/qwen_engine/swarm_micro_reasoning/swarm_node.py --self-test
python tools/qwen_engine/swarm_micro_reasoning/swarm_node.py tests/fixtures/reference_1/input.json
```

## Node card

Every node receives a `node_card`:

```json
{
  "swarm_id": "run_001",
  "topology": "reference_1",
  "node_id": "ref_0",
  "coordinate": [0],
  "neighbors": [],
  "total_nodes": 1,
  "round": 0,
  "max_rounds": 1,
  "readout_node": "ref_0",
  "global_goal": "produce one final evidence-grounded ChatGPT packet",
  "local_rule": "communicate only with neighbors",
  "topology_awareness": true,
  "role": "reference_readout"
}
```

A non-readout mesh node must not produce `final_packet`; it only emits `outgoing_messages` to neighbors.

## Boundary

This is not an LLM. It is a tiny system-intelligence scaffold: topology awareness, message schema, evidence extraction, safety labeling, and final packet shaping.
