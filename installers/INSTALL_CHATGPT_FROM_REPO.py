#!/usr/bin/env python3
"""Install the Chat Local Runtime GitHub public fallback tool layer into a ChatGPT code runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

INSTALLER_VERSION = "0.2.0-public"
BUILD_ROLE = "github-public-fallback"
AI_CONTRACT_VERSION = "offload-ai/1"

# These hashes intentionally track the public reference builds committed under dist/.
# ChatGPT Library remains the preferred source for exact active artifacts when available.
TOOLS = {
    "workerhub.pyz": {
        "public_version": "0.1.1-public",
        "sha256": "df16e41eb749b1fec1c360a51a8f36131b44c7bfe0f425d3c0864b8f162d82c2",
    },
    "verificationrunner.pyz": {
        "public_version": "0.1.1-public",
        "sha256": "e205e651faf3f40c20a5d577916e9c5cf127ccc902d462073aa35c6594fd79db",
    },
    "workspaceinspector.pyz": {
        "public_version": "0.1.2-public",
        "sha256": "1c91a206c69c469098f717d6fef9446e41a8c0f8afea7d4989defb80eb0b91c3",
    },
    "smartdiff.pyz": {
        "public_version": "0.1.0-public",
        "sha256": "40f4a392b25ea69a99f64ba1e543baac430cb0fdd5663977d65276792762c2cd",
    },
}

DIRS = [
    "code",
    "programs",
    "tests",
    "fixtures",
    "benchmarks",
    "artifacts",
    "cache",
    "runtime",
    "logs",
    "scratch",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_json(path: Path, command: str, timeout: int = 90) -> dict:
    cp = subprocess.run(
        [sys.executable, str(path), command],
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        payload = {"raw": cp.stdout[:4000]}
    return {
        "returncode": cp.returncode,
        "payload": payload,
        "stderr": cp.stderr[:2000],
    }


def _observed_version(*payloads: dict) -> str | None:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("version", "runner_version"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _files_only(programs: Path) -> dict:
    checks = {}
    for name, spec in TOOLS.items():
        path = programs / name
        observed = sha256(path) if path.is_file() else None
        checks[name] = {
            "ok": bool(path.is_file() and observed == spec["sha256"]),
            "path": str(path),
            "expected_sha256": spec["sha256"],
            "observed_sha256": observed,
            "public_version": spec["public_version"],
        }
    return {
        "status": "PASS" if all(x["ok"] for x in checks.values()) else "FAIL",
        "tools": checks,
    }


def inspect_tool(path: Path, spec: dict) -> dict:
    file_check = _files_only(path.parent)["tools"][path.name]
    if not file_check["ok"]:
        return {**file_check, "capabilities": None, "self_test": None, "observed_version": None}

    capabilities_run = None
    self_test_run = None
    observed_version = None
    contract = None
    ok = False
    try:
        capabilities_run = _run_json(path, "capabilities")
        self_test_run = _run_json(path, "self-test")
        capabilities = capabilities_run["payload"] if capabilities_run["returncode"] == 0 else {}
        self_test = self_test_run["payload"] if self_test_run["returncode"] == 0 else {}
        observed_version = _observed_version(self_test, capabilities)
        contract = self_test.get("ai_contract_version") or capabilities.get("ai_contract_version")
        self_test_ok = self_test_run["returncode"] == 0 and self_test.get("status") == "PASS"
        contract_ok = contract in (None, AI_CONTRACT_VERSION)
        ok = bool(file_check["ok"] and self_test_ok and contract_ok)
    except Exception as exc:
        self_test_run = {
            "returncode": None,
            "payload": {},
            "stderr": f"{type(exc).__name__}: {exc}",
        }

    return {
        **file_check,
        "ok": ok,
        "observed_version": observed_version,
        "ai_contract_version": contract,
        "capabilities": capabilities_run,
        "self_test": self_test_run,
    }


def verify(root: str | Path) -> dict:
    root = Path(root).resolve()
    programs = root / "programs"
    tools = {name: inspect_tool(programs / name, spec) for name, spec in TOOLS.items()}
    ok_all = all(info["ok"] for info in tools.values())
    return {
        "schema": "chat-local-runtime/install-result-0.2",
        "installer_version": INSTALLER_VERSION,
        "build_role": BUILD_ROLE,
        "storage_policy": {
            "preferred_active_source": "ChatGPT Library when exact generated artifacts are available",
            "this_installer": "GitHub public fallback/reference build",
        },
        "status": "PASS" if ok_all else "FAIL",
        "root": str(root),
        "tools": tools,
        "next_action": "USE_TOOL_LAYER" if ok_all else "REINSTALL_OR_REVIEW",
    }


def source_verify(deep: bool = True) -> dict:
    src = repo_root() / "dist"
    if not deep:
        result = _files_only(src)
    else:
        tools = {name: inspect_tool(src / name, spec) for name, spec in TOOLS.items()}
        result = {
            "status": "PASS" if all(info["ok"] for info in tools.values()) else "FAIL",
            "tools": tools,
        }
    return {
        "schema": "chat-local-runtime/source-verify-0.2",
        "installer_version": INSTALLER_VERSION,
        "build_role": BUILD_ROLE,
        **result,
    }


def registry_payload() -> dict:
    return {
        "schema": "chat-local-runtime/registry-0.2",
        "installer_version": INSTALLER_VERSION,
        "build_role": BUILD_ROLE,
        "ai_contract_version": AI_CONTRACT_VERSION,
        "tools": TOOLS,
        "storage_policy": {
            "preferred_active_source": "ChatGPT Library",
            "github_role": "public reference/fallback/reconstruction",
        },
    }


def install(root: str | Path) -> dict:
    root = Path(root).resolve()
    src = repo_root() / "dist"

    # Installation uses a lightweight source SHA gate first. Full self-tests run after install.
    source_gate = source_verify(deep=False)
    if source_gate["status"] != "PASS":
        return {
            **source_gate,
            "schema": "chat-local-runtime/install-result-0.2",
            "root": str(root),
            "phase": "SOURCE_HASH_GATE",
            "next_action": "DO_NOT_INSTALL",
        }

    root.mkdir(parents=True, exist_ok=True)
    for directory in DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex[:12]
    stage = root / "runtime" / f"install-stage-{token}"
    backup = root / "runtime" / f"install-backup-{int(time.time())}-{token}"
    stage_programs = stage / "programs"
    stage_programs.mkdir(parents=True, exist_ok=False)

    try:
        for name in TOOLS:
            shutil.copy2(src / name, stage_programs / name)
        (stage_programs / "registry.json").write_text(
            json.dumps(registry_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        stage_gate = _files_only(stage_programs)
        if stage_gate["status"] != "PASS":
            return {
                "schema": "chat-local-runtime/install-result-0.2",
                "installer_version": INSTALLER_VERSION,
                "build_role": BUILD_ROLE,
                "status": "FAIL",
                "root": str(root),
                "phase": "STAGING_HASH_GATE",
                "staging": stage_gate,
                "next_action": "KEEP_EXISTING_INSTALL",
            }

        installed_programs = root / "programs"
        backup.mkdir(parents=True, exist_ok=False)
        for name in list(TOOLS) + ["registry.json"]:
            current = installed_programs / name
            if current.exists():
                shutil.copy2(current, backup / name)

        for name in TOOLS:
            shutil.copy2(stage_programs / name, installed_programs / name)
        shutil.copy2(stage_programs / "registry.json", installed_programs / "registry.json")

        final_result = verify(root)
        final_result["phase"] = "FINAL_SELF_TEST_GATE"
        final_result["backup"] = str(backup)
        if final_result["status"] == "PASS":
            return final_result

        # Restore the previous installation if any final self-test fails.
        for name in list(TOOLS) + ["registry.json"]:
            installed = installed_programs / name
            saved = backup / name
            if saved.exists():
                shutil.copy2(saved, installed)
            elif installed.exists():
                installed.unlink()

        return {
            **final_result,
            "status": "FAIL",
            "next_action": "ROLLED_BACK_TO_PREVIOUS_INSTALL",
            "rollback_verification": verify(root),
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install or verify the Chat Local Runtime GitHub public fallback tool layer."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="install",
        choices=["install", "verify", "source-verify"],
    )
    parser.add_argument("--root", default="/mnt/data/ai_program_lab")
    args = parser.parse_args()

    if args.command == "install":
        result = install(args.root)
    elif args.command == "verify":
        result = verify(args.root)
    else:
        result = source_verify(deep=True)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
