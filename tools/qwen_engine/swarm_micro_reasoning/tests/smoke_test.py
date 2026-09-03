#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "swarm_mesh_kernel.py"

proc = subprocess.run([sys.executable, str(KERNEL), "--self-test"], text=True, capture_output=True)
print(proc.stdout)
if proc.returncode != 0:
    print(proc.stderr, file=sys.stderr)
    raise SystemExit(proc.returncode)
result = json.loads(proc.stdout)
if not result.get("ok"):
    raise SystemExit(1)
