#!/usr/bin/env python3
"""Install the legacy GitHub public fallback tool layer safely into a ChatGPT code runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

INSTALLER_VERSION = "0.2.1-public"
BUILD_ROLE = "github-legacy-public-fallback"
AI_CONTRACT_VERSION = "offload-ai/1"
CONTRACT_ENFORCED = False
DEFAULT_KEEP_BACKUPS = 3

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
DIRS = ["code", "programs", "tests", "fixtures", "benchmarks", "artifacts", "cache", "runtime", "logs", "scratch"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def contract_policy() -> dict:
    return {
        "expected": AI_CONTRACT_VERSION,
        "enforced": CONTRACT_ENFORCED,
        "status": "NOT_ENFORCED",
        "note": "This legacy public fallback observes contract metadata but does not use it as a PASS gate. The newer active Library line declares offload-ai/1 and is verified separately.",
    }


def _run_json(path: Path, command: str, timeout: int = 90) -> dict:
    cp = subprocess.run([sys.executable, str(path), command], capture_output=True, text=True, timeout=timeout, shell=False)
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        payload = {"raw": cp.stdout[:4000]}
    return {"returncode": cp.returncode, "payload": payload, "stderr": cp.stderr[:2000]}


def _observed_version(*payloads: dict) -> str | None:
    for payload in payloads:
        if isinstance(payload, dict):
            for key in ("version", "runner_version"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
    return None


def _contract_observation(value: str | None) -> str:
    if value is None:
        return "MISSING"
    return "MATCH" if value == AI_CONTRACT_VERSION else "MISMATCH"


def _file_gate(programs: Path) -> dict:
    tools = {}
    for name, spec in TOOLS.items():
        path = programs / name
        observed = sha256(path) if path.is_file() else None
        ok = bool(path.is_file() and observed == spec["sha256"])
        tools[name] = {
            "ok": ok,
            "path": str(path),
            "expected_sha256": spec["sha256"],
            "observed_sha256": observed,
            "public_version": spec["public_version"],
        }
    return {"status": "PASS" if all(x["ok"] for x in tools.values()) else "FAIL", "tools": tools}


def inspect_tool(path: Path, spec: dict) -> dict:
    base = _file_gate(path.parent)["tools"][path.name]
    if not base["ok"]:
        return {**base, "ok": False, "observed_version": None, "version_ok": False, "ai_contract_version": None, "contract_observation": "MISSING", "contract_enforced": False, "capabilities": None, "self_test": None}
    try:
        capabilities_run = _run_json(path, "capabilities")
        self_test_run = _run_json(path, "self-test")
        capabilities = capabilities_run["payload"] if capabilities_run["returncode"] == 0 else {}
        self_test = self_test_run["payload"] if self_test_run["returncode"] == 0 else {}
        observed_version = _observed_version(self_test, capabilities)
        version_ok = observed_version == spec["public_version"]
        contract = self_test.get("ai_contract_version") or capabilities.get("ai_contract_version")
        self_test_ok = self_test_run["returncode"] == 0 and self_test.get("status") == "PASS"
        ok = bool(base["ok"] and version_ok and self_test_ok)
        return {
            **base,
            "ok": ok,
            "observed_version": observed_version,
            "version_ok": version_ok,
            "ai_contract_version": contract,
            "contract_observation": _contract_observation(contract),
            "contract_enforced": False,
            "capabilities": capabilities_run,
            "self_test": self_test_run,
        }
    except Exception as exc:
        return {**base, "ok": False, "observed_version": None, "version_ok": False, "ai_contract_version": None, "contract_observation": "MISSING", "contract_enforced": False, "capabilities": None, "self_test": {"returncode": None, "payload": {}, "stderr": f"{type(exc).__name__}: {exc}"}}


def verify(root: str | Path) -> dict:
    root = Path(root).resolve()
    programs = root / "programs"
    tools = {name: inspect_tool(programs / name, spec) for name, spec in TOOLS.items()}
    ok = all(info["ok"] for info in tools.values())
    return {
        "schema": "chat-local-runtime/install-result-0.2.1",
        "installer_version": INSTALLER_VERSION,
        "build_role": BUILD_ROLE,
        "contract_policy": contract_policy(),
        "storage_policy": {
            "preferred_active_source": "ChatGPT Library when exact active artifacts are available",
            "this_installer": "legacy GitHub public fallback/reference build",
        },
        "status": "PASS" if ok else "FAIL",
        "root": str(root),
        "tools": tools,
        "next_action": "USE_TOOL_LAYER" if ok else "REINSTALL_OR_REVIEW",
    }


def source_verify(deep: bool = True, src: Path | None = None) -> dict:
    src = (src or repo_root() / "dist").resolve()
    if deep:
        tools = {name: inspect_tool(src / name, spec) for name, spec in TOOLS.items()}
        status = "PASS" if all(info["ok"] for info in tools.values()) else "FAIL"
        body = {"status": status, "tools": tools}
    else:
        body = _file_gate(src)
    return {"schema": "chat-local-runtime/source-verify-0.2.1", "installer_version": INSTALLER_VERSION, "build_role": BUILD_ROLE, "contract_policy": contract_policy(), **body}


def registry_payload() -> dict:
    return {
        "schema": "chat-local-runtime/registry-0.2.1",
        "installer_version": INSTALLER_VERSION,
        "build_role": BUILD_ROLE,
        "contract_policy": contract_policy(),
        "tools": TOOLS,
        "storage_policy": {"preferred_active_source": "ChatGPT Library", "github_role": "legacy public fallback/reference"},
    }


def _managed_names() -> list[str]:
    return list(TOOLS) + ["registry.json"]


def _snapshot(programs: Path) -> dict:
    files = {}
    for name in _managed_names():
        path = programs / name
        if path.is_file():
            files[name] = {"exists": True, "sha256": sha256(path), "bytes": path.stat().st_size}
        else:
            files[name] = {"exists": False, "sha256": None, "bytes": 0}
    return {"schema": "chat-local-runtime/backup-manifest-0.1", "created_unix": int(time.time()), "files": files}


def _has_previous(snapshot: dict) -> bool:
    return any(v.get("exists") for v in snapshot.get("files", {}).values())


def _make_backup(programs: Path, runtime: Path, token: str) -> tuple[Path | None, dict]:
    snapshot = _snapshot(programs)
    if not _has_previous(snapshot):
        return None, snapshot
    backup = runtime / f"install-backup-{int(time.time())}-{token}"
    backup.mkdir(parents=True, exist_ok=False)
    for name, info in snapshot["files"].items():
        if info["exists"]:
            shutil.copy2(programs / name, backup / name)
            if sha256(backup / name) != info["sha256"]:
                raise RuntimeError(f"backup verification failed: {name}")
    (backup / "backup-manifest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup, snapshot


def _verify_snapshot(programs: Path, snapshot: dict) -> dict:
    checks = {}
    for name, expected in snapshot.get("files", {}).items():
        path = programs / name
        observed = sha256(path) if path.is_file() else None
        ok = (path.is_file() and observed == expected["sha256"]) if expected["exists"] else (not path.exists())
        checks[name] = {"ok": ok, "expected_exists": expected["exists"], "expected_sha256": expected["sha256"], "observed_exists": path.exists(), "observed_sha256": observed}
    return {"status": "PASS" if all(x["ok"] for x in checks.values()) else "FAIL", "files": checks}


def _restore(programs: Path, backup: Path | None, snapshot: dict) -> dict:
    errors = []
    for name, expected in snapshot.get("files", {}).items():
        installed = programs / name
        if expected["exists"]:
            saved = backup / name if backup else None
            if saved is None or not saved.is_file() or sha256(saved) != expected["sha256"]:
                errors.append(f"invalid backup for {name}")
                continue
            shutil.copy2(saved, installed)
        elif installed.exists():
            installed.unlink()
    result = _verify_snapshot(programs, snapshot)
    if errors:
        result["status"] = "FAIL"
        result["errors"] = errors
    return result


def _prune_backups(runtime: Path, keep: int) -> list[str]:
    keep = max(0, int(keep))
    backups = sorted((p for p in runtime.glob("install-backup-*") if p.is_dir()), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    removed = []
    for path in backups[keep:]:
        shutil.rmtree(path, ignore_errors=True)
        removed.append(str(path))
    return removed


def _install_from_src(root: str | Path, src: Path, keep_backups: int) -> dict:
    root, src = Path(root).resolve(), Path(src).resolve()
    source_gate = source_verify(False, src)
    if source_gate["status"] != "PASS":
        return {**source_gate, "schema": "chat-local-runtime/install-result-0.2.1", "root": str(root), "phase": "SOURCE_HASH_GATE", "next_action": "DO_NOT_INSTALL"}

    root.mkdir(parents=True, exist_ok=True)
    for directory in DIRS:
        (root / directory).mkdir(parents=True, exist_ok=True)
    programs, runtime = root / "programs", root / "runtime"
    token = uuid.uuid4().hex[:12]
    stage = runtime / f"install-stage-{token}"
    stage_programs = stage / "programs"
    stage_programs.mkdir(parents=True, exist_ok=False)

    try:
        for name in TOOLS:
            shutil.copy2(src / name, stage_programs / name)
        (stage_programs / "registry.json").write_text(json.dumps(registry_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        stage_gate = _file_gate(stage_programs)
        if stage_gate["status"] != "PASS":
            return {"schema": "chat-local-runtime/install-result-0.2.1", "installer_version": INSTALLER_VERSION, "status": "FAIL", "root": str(root), "phase": "STAGING_HASH_GATE", "staging": stage_gate, "next_action": "KEEP_EXISTING_INSTALL"}

        backup, previous = _make_backup(programs, runtime, token)
        for name in TOOLS:
            shutil.copy2(stage_programs / name, programs / name)
        shutil.copy2(stage_programs / "registry.json", programs / "registry.json")

        final = verify(root)
        final["phase"] = "FINAL_SELF_TEST_GATE"
        final["backup"] = str(backup) if backup else None
        if final["status"] == "PASS":
            final["backup_pruned"] = _prune_backups(runtime, keep_backups)
            return final

        rollback = _restore(programs, backup, previous)
        if rollback["status"] != "PASS":
            next_action = "ROLLBACK_FAILED_REVIEW_REQUIRED"
        elif _has_previous(previous):
            next_action = "ROLLED_BACK_TO_PREVIOUS_INSTALL"
        else:
            next_action = "NO_PREVIOUS_INSTALL_REMOVED"
        return {**final, "status": "FAIL", "next_action": next_action, "rollback_verification": rollback, "backup_pruned": _prune_backups(runtime, keep_backups)}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def install(root: str | Path, keep_backups: int = DEFAULT_KEEP_BACKUPS) -> dict:
    return _install_from_src(root, repo_root() / "dist", keep_backups)


def installer_self_test() -> dict:
    global TOOLS
    original = TOOLS
    checks = []
    def ck(name, condition): checks.append({"name": name, "pass": bool(condition)})
    good = """import json,sys\ncmd=sys.argv[1] if len(sys.argv)>1 else ''\nbase={'version':'9.9-test','ai_contract_version':'offload-ai/1'}\nif cmd=='capabilities': print(json.dumps({'status':'SUCCESS',**base})); raise SystemExit(0)\nif cmd=='self-test': print(json.dumps({'status':'PASS',**base})); raise SystemExit(0)\nraise SystemExit(2)\n"""
    missing = good.replace(",'ai_contract_version':'offload-ai/1'", "")
    failing = good.replace("'status':'PASS'", "'status':'FAIL'")
    try:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td); src = base / "repo" / "dist"; src.mkdir(parents=True); cand = src / "fake.pyz"
            cand.write_text(missing, encoding="utf-8"); TOOLS = {"fake.pyz": {"public_version": "9.9-test", "sha256": sha256(cand)}}
            r = _install_from_src(base / "contract", src, 2); tool = r.get("tools", {}).get("fake.pyz", {})
            ck("contract-policy-explicit", r.get("status") == "PASS" and r.get("contract_policy", {}).get("enforced") is False and tool.get("contract_observation") == "MISSING")

            cand.write_text(good, encoding="utf-8"); TOOLS["fake.pyz"]["sha256"] = sha256(cand)
            root2 = base / "corrupt"; (root2 / "programs").mkdir(parents=True); old = root2 / "programs" / "fake.pyz"; old.write_bytes(b"old"); old_hash = sha256(old)
            cand.write_bytes(b"corrupt")
            r2 = _install_from_src(root2, src, 2)
            ck("source-corruption-keeps-existing", r2.get("next_action") == "DO_NOT_INSTALL" and sha256(old) == old_hash)

            cand.write_text(failing, encoding="utf-8"); TOOLS["fake.pyz"]["sha256"] = sha256(cand)
            root3 = base / "rollback"; (root3 / "programs").mkdir(parents=True); prev = root3 / "programs" / "fake.pyz"; prev.write_bytes(b"previous"); prev_hash = sha256(prev)
            r3 = _install_from_src(root3, src, 2)
            ck("rollback-uses-backup-manifest", r3.get("next_action") == "ROLLED_BACK_TO_PREVIOUS_INSTALL" and r3.get("rollback_verification", {}).get("status") == "PASS" and sha256(prev) == prev_hash)

            root4 = base / "first"; r4 = _install_from_src(root4, src, 2)
            ck("first-install-failure-distinct", r4.get("next_action") == "NO_PREVIOUS_INSTALL_REMOVED" and not (root4 / "programs" / "fake.pyz").exists())

            runtime = base / "prune" / "runtime"; runtime.mkdir(parents=True)
            for i in range(5):
                p = runtime / f"install-backup-{100+i}-x{i}"; p.mkdir(); os.utime(p, ns=(1_000_000_000+i, 1_000_000_000+i))
            _prune_backups(runtime, 2)
            ck("backup-retention", len(list(runtime.glob("install-backup-*"))) == 2)
    finally:
        TOOLS = original
    passed = sum(x["pass"] for x in checks)
    return {"schema": "chat-local-runtime/installer-self-test-0.1", "installer_version": INSTALLER_VERSION, "status": "PASS" if passed == len(checks) else "FAIL", "passed": passed, "total": len(checks), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or verify the legacy Chat Local Runtime GitHub public fallback safely.")
    parser.add_argument("command", nargs="?", default="install", choices=["install", "verify", "source-verify", "self-test"])
    parser.add_argument("--root", default="/mnt/data/ai_program_lab")
    parser.add_argument("--keep-backups", type=int, default=DEFAULT_KEEP_BACKUPS)
    args = parser.parse_args()
    result = install(args.root, args.keep_backups) if args.command == "install" else verify(args.root) if args.command == "verify" else source_verify(True) if args.command == "source-verify" else installer_self_test()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
