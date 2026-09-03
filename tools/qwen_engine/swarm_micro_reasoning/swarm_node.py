#!/usr/bin/env python3
"""Compatibility entrypoint for Swarm Micro-Reasoning Kernel v0.2.

Old usage still works:
  python swarm_node.py --self-test --pretty
  python swarm_node.py single_error --pretty

For mesh runs use:
  python swarm_mesh_kernel.py --topology grid_2x2 single_error --trace --pretty
"""
from __future__ import annotations
from swarm_mesh_kernel import main

if __name__ == "__main__":
    raise SystemExit(main())
