#!/usr/bin/env python3
"""Install/verify the five-tool Chat Local Runtime GitHub fallback layer."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

INSTALLER_VERSION = "0.3.0-public"
BUILD_ROLE = "github-public-fallback"
AI_CONTRACT_VERSION = "offload-ai/1"

TOOLS = {
    "workerhub.pyz": {
        "version": "0.1.1-public",
        "sha256": "df16e41eb749b1fec1c360a51a8f36131b44c7bfe0f425d3c0864b8f162d82c2",
        "capabilities": "capabilities",
        "self_test": "self-test",
    },
    "verificationrunner.pyz": {
        "version": "0.1.1-public",
        "sha256": "e205e651faf3f40c20a5d577916e9c5cf127ccc902d462073aa35c6594fd79db",
        "capabilities": "capabilities",
        "self_test": "self-test",
    },
    "workspaceinspector.pyz": {
        "version": "0.1.2-public",
        "sha256": "1c91a206c69c469098f717d6fef9446e41a8c0f8afea7d4989defb80eb0b91c3",
        "capabilities": "capabilities",
        "self_test": "self-test",
    },
    "smartdiff.pyz": {
        "version": "0.1.0-public",
        "sha256": "40f4a392b25ea69a99f64ba1e543baac430cb0fdd5663977d65276792762c2cd",
        "capabilities": "capabilities",
        "self_test": "self-test",
    },
    "artifactbuilder.pyz": {
        "version": "0.1.1",
        "sha256": "1677f84252d0e275f0448426ac6702318ad30589c462493aea533e1ddfe63c3a",
        "parts": [f"artifactbuilder.pyz.part{i:02d}" for i in range(1, 6)],
        "capabilities": None,
        "self_test": "self-test",
    },
}

DIRS = ["code", "programs", "tests", "fixtures", "benchmarks", "artifacts", "cache", "runtime", "logs", "scratch"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_json(path: Path, command: str, timeout: int = 120) -> dict:
    cp = subprocess.run([sys.executable, str(path), command], capture_output=True, text=True, timeout=timeout, shell=False)
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        payload = {"raw": cp.stdout[:4000]}
    return {"returncode": cp.returncode, "payload": payload, "stderr": cp.stderr[:2000]}


def observed_version(*payloads: dict) -> str | None:
    for payload in payloads:
        if isinstance(payload, dict):
            for key in ("version", "runner_version", "tool_version"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
    return None


def materialize_one(dist: Path, name: str, spec: dict, dst: Path) -> None:
    direct = dist / name
    if direct.is_file():
        shutil.copy2(direct, dst)
        return
    parts = spec.get("parts") or []
    if parts:
        with dst.open("wb") as out:
            for part in parts:
                p = dist / part
                if not p.is_file():
                    raise FileNotFoundError(f"missing artifact part: {p}")
                out.write(p.read_bytes())
        return
    raise FileNotFoundError(f"missing artifact source for {name}")


def materialize_all(dist: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name, spec in TOOLS.items():
        materialize_one(dist, name, spec, dst / name)


def file_checks(programs: Path) -> dict:
    tools = {}
    for name, spec in TOOLS.items():
        p = programs / name
        observed = sha256(p) if p.is_file() else None
        tools[name] = {
            "ok": bool(p.is_file() and observed == spec["sha256"]),
            "version": spec["version"],
            "expected_sha256": spec["sha256"],
            "observed_sha256": observed,
            "path": str(p),
        }
    return {"status": "PASS" if all(v["ok"] for v in tools.values()) else "FAIL", "tools": tools}


def inspect_tool(path: Path, spec: dict) -> dict:
    base = file_checks(path.parent)["tools"][path.name]
    if not base["ok"]:
        return {**base, "ok": False, "capabilities": None, "self_test": None}
    caps_run = None
    caps_payload = {}
    if spec.get("capabilities"):
        caps_run = run_json(path, spec["capabilities"])
        if caps_run["returncode"] == 0:
            caps_payload = caps_run["payload"]
    self_run = run_json(path, spec.get("self_test", "self-test"))
    self_payload = self_run["payload"] if self_run["returncode"] == 0 else {}
    contract = self_payload.get("ai_contract_version") or caps_payload.get("ai_contract_version")
    ok = bool(
        base["ok"]
        and (caps_run is None or caps_run["returncode"] == 0)
        and self_run["returncode"] == 0
        and self_payload.get("status") == "PASS"
        and contract in (None, AI_CONTRACT_VERSION)
    )
    return {
        **base,
        "ok": ok,
        "observed_version": observed_version(self_payload, caps_payload),
        "ai_contract_version": contract,
        "capabilities": caps_run,
        "self_test": self_run,
    }


def verify(root: str | Path) -> dict:
    root = Path(root).resolve()
    programs = root / "programs"
    tools = {name: inspect_tool(programs / name, spec) for name, spec in TOOLS.items()}
    ok = all(v["ok"] for v in tools.values())
    return {
        "schema": "chat-local-runtime/install-result-0.3",
        "installer_version": INSTALLER_VERSION,
        "build_role": BUILD_ROLE,
        "status": "PASS" if ok else "FAIL",
        "root": str(root),
        "tools": tools,
        "next_action": "USE_TOOL_LAYER" if ok else "REINSTALL_OR_REVIEW",
    }


def source_verify(deep: bool = True) -> dict:
    with tempfile.TemporaryDirectory(prefix="chat-local-runtime-source-") as td:
        programs = Path(td) / "programs"
        try:
            materialize_all(repo_root() / "dist", programs)
            if deep:
                tools = {name: inspect_tool(programs / name, spec) for name, spec in TOOLS.items()}
                result = {"status": "PASS" if all(v["ok"] for v in tools.values()) else "FAIL", "tools": tools}
            else:
                result = file_checks(programs)
        except Exception as exc:
            result = {"status": "FAIL", "error": f"{type(exc).__name__}: {exc}", "tools": {}}
    return {"schema": "chat-local-runtime/source-verify-0.3", "installer_version": INSTALLER_VERSION, **result}


def install(root: str | Path) -> dict:
    root = Path(root).resolve()
    source_gate = source_verify(deep=False)
    if source_gate["status"] != "PASS":
        return {**source_gate, "schema": "chat-local-runtime/install-result-0.3", "root": str(root), "phase": "SOURCE_HASH_GATE", "next_action": "DO_NOT_INSTALL"}

    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex[:12]
    stage = root / "runtime" / f"install-stage-{token}"
    backup = root / "runtime" / f"install-backup-{int(time.time())}-{token}"
    stage_programs = stage / "programs"
    stage_programs.mkdir(parents=True)

    try:
        materialize_all(repo_root() / "dist", stage_programs)
        if file_checks(stage_programs)["status"] != "PASS":
            return {"schema": "chat-local-runtime/install-result-0.3", "status": "FAIL", "phase": "STAGING_HASH_GATE", "next_action": "KEEP_EXISTING_INSTALL"}

        installed = root / "programs"
        backup.mkdir(parents=True, exist_ok=True)
        for name in TOOLS:
            if (installed / name).exists():
                shutil.copy2(installed / name, backup / name)
            shutil.copy2(stage_programs / name, installed / name)

        result = verify(root)
        result["phase"] = "FINAL_SELF_TEST_GATE"
        if result["status"] == "PASS":
            return result

        for name in TOOLS:
            saved = backup / name
            current = installed / name
            if saved.exists():
                shutil.copy2(saved, current)
            elif current.exists():
                current.unlink()
        return {**result, "status": "FAIL", "next_action": "ROLLED_BACK_TO_PREVIOUS_INSTALL", "rollback_verification": verify(root)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Install/verify Chat Local Runtime five-tool GitHub fallback layer")
    p.add_argument("command", nargs="?", default="install", choices=["install", "verify", "source-verify"])
    p.add_argument("--root", default="/mnt/data/ai_program_lab")
    args = p.parse_args()
    result = install(args.root) if args.command == "install" else verify(args.root) if args.command == "verify" else source_verify(deep=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
