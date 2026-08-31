#!/usr/bin/env python3
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
import zipfile
from pathlib import Path

VERSION = "0.3.1"
AI_CONTRACT_VERSION = "offload-ai/1"
SCHEMA = "verification-runner/0.3"
ACCEPTANCE_SCHEMA = "offload-feature-acceptance/1"
PIN_SCHEMA = "offload-feature-pin/1"
FUNCTION_SCHEMA = "offload-functional-contract/1"
VALIDATORS = ("ruff", "bandit", "mypy", "pytest", "coverage")
BAD_STATES = {"FAIL", "BLOCKED", "ERROR"}


def jdump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_contract_payload(data):
    out = json.loads(json.dumps(data))
    out.pop("locked_sha256", None)
    return out


def contract_sha256(data):
    return hashlib.sha256(jdump(canonical_contract_payload(data)).encode("utf-8")).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def json_subset(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and json_subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) >= len(expected) and all(json_subset(a, e) for a, e in zip(actual, expected))
    return actual == expected


def resolve_tokens(value, *, target, workdir, contract_dir):
    if isinstance(value, str):
        return value.replace("{target}", str(target)).replace("{workdir}", str(workdir)).replace("{contract_dir}", str(contract_dir))
    if isinstance(value, list):
        return [resolve_tokens(v, target=target, workdir=workdir, contract_dir=contract_dir) for v in value]
    if isinstance(value, dict):
        return {k: resolve_tokens(v, target=target, workdir=workdir, contract_dir=contract_dir) for k, v in value.items()}
    return value


def is_python_target(target):
    return Path(target).suffix.lower() in {".py", ".pyz"}


def is_native_or_opaque(target):
    target = Path(target)
    if target.is_dir() or is_python_target(target):
        return False
    if target.suffix.lower() in {".zip", ".json", ".toml", ".yaml", ".yml", ".md", ".txt"}:
        return False
    return target.is_file()


def run_case(target, case, *, contract_dir):
    target = Path(target).resolve()
    case_id = str(case.get("id") or "unnamed")
    if is_native_or_opaque(target):
        return {"id": case_id, "status": "BLOCKED", "reason": "BLOCKED_NEEDS_SANDBOX"}
    timeout = float(case.get("timeout_seconds", 60))
    with tempfile.TemporaryDirectory(prefix="verify-case-") as td:
        workdir = Path(td)
        args = resolve_tokens(case.get("args", []), target=target, workdir=workdir, contract_dir=contract_dir)
        stdin_text = case.get("stdin_text")
        if "stdin_json" in case:
            stdin_text = json.dumps(resolve_tokens(case["stdin_json"], target=target, workdir=workdir, contract_dir=contract_dir), ensure_ascii=False)
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in resolve_tokens(case.get("env", {}), target=target, workdir=workdir, contract_dir=contract_dir).items()})
        for item in case.get("precreate", []):
            rel = resolve_tokens(item["path"], target=target, workdir=workdir, contract_dir=contract_dir)
            path = Path(rel)
            if not path.is_absolute():
                path = workdir / path
            path.parent.mkdir(parents=True, exist_ok=True)
            if item.get("kind", "file") == "dir":
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.write_text(str(item.get("content", "")), encoding="utf-8")
        cmd = [sys.executable, str(target), *map(str, args)] if is_python_target(target) else [str(target), *map(str, args)]
        started = time.perf_counter()
        try:
            cp = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, cwd=workdir, env=env, timeout=timeout, shell=False)
        except subprocess.TimeoutExpired as exc:
            return {"id": case_id, "status": "BLOCKED", "reason": "TIMEOUT", "stdout": (exc.stdout or "")[:2000], "stderr": (exc.stderr or "")[:2000]}
        except Exception as exc:
            return {"id": case_id, "status": "BLOCKED", "reason": f"EXEC_ERROR:{type(exc).__name__}", "detail": str(exc)[:500]}
        checks = []
        expected = case.get("expect", {})
        def check(name, ok, observed=None, want=None):
            checks.append({"name": name, "pass": bool(ok), "observed": observed, "expected": want})
        allowed = expected.get("returncode_in", [0])
        check("returncode", cp.returncode in allowed, cp.returncode, allowed)
        for key, stream, positive in (
            ("stdout_contains", cp.stdout, True),
            ("stdout_not_contains", cp.stdout, False),
            ("stderr_contains", cp.stderr, True),
            ("stderr_not_contains", cp.stderr, False),
        ):
            if key in expected:
                values = expected[key] if isinstance(expected[key], list) else [expected[key]]
                for value in values:
                    present = str(value) in stream
                    check(f"{key}:{value}", present if positive else not present)
        if "stdout_json_subset" in expected:
            try:
                parsed = json.loads(cp.stdout)
            except Exception:
                parsed = None
            want = resolve_tokens(expected["stdout_json_subset"], target=target, workdir=workdir, contract_dir=contract_dir)
            check("stdout_json_subset", parsed is not None and json_subset(parsed, want), parsed, want)
        for rel in expected.get("files_present", []):
            path = Path(resolve_tokens(rel, target=target, workdir=workdir, contract_dir=contract_dir))
            if not path.is_absolute():
                path = workdir / path
            check(f"file_present:{rel}", path.exists())
        for rel in expected.get("files_absent", []):
            path = Path(resolve_tokens(rel, target=target, workdir=workdir, contract_dir=contract_dir))
            if not path.is_absolute():
                path = workdir / path
            check(f"file_absent:{rel}", not path.exists())
        return {
            "id": case_id,
            "status": "PASS" if checks and all(x["pass"] for x in checks) else "FAIL",
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "returncode": cp.returncode,
            "checks": checks,
            "stdout": cp.stdout[:4000],
            "stderr": cp.stderr[:2000],
        }


def evidence_fact(contract_dir, spec):
    evidence_id = str(spec.get("id") or "unnamed-evidence")
    rel = spec.get("path")
    if not rel:
        return {"id": evidence_id, "status": "FAIL", "reason": "MISSING_PATH"}
    path = Path(rel)
    if not path.is_absolute():
        path = (Path(contract_dir) / path).resolve()
    if not path.is_file():
        return {"id": evidence_id, "status": "FAIL", "reason": "EVIDENCE_FILE_MISSING", "path": str(path)}
    try:
        data = load_json(path)
    except Exception as exc:
        return {"id": evidence_id, "status": "FAIL", "reason": "EVIDENCE_JSON_INVALID", "detail": str(exc)}
    expected = spec.get("json_subset", {})
    return {
        "id": evidence_id,
        "status": "PASS" if json_subset(data, expected) else "FAIL",
        "path": str(path),
        "sha256": file_sha256(path),
        "expected_subset": expected,
    }


def validate_acceptance_contract(data):
    errors = []
    if data.get("schema") != ACCEPTANCE_SCHEMA:
        errors.append("schema")
    for key in ("contract_id", "target_id", "purpose", "requirements", "scenarios", "locked_sha256"):
        if key not in data:
            errors.append(f"missing:{key}")
    evidence_ids = set()
    for scenario in data.get("scenarios", []):
        sid = scenario.get("id")
        if not sid or sid in evidence_ids:
            errors.append("scenario-id")
        evidence_ids.add(sid)
    for evidence in data.get("evidence_files", []):
        eid = evidence.get("id")
        if not eid or eid in evidence_ids:
            errors.append("evidence-id")
        evidence_ids.add(eid)
    for requirement in data.get("requirements", []):
        rid = requirement.get("id")
        if not rid or not requirement.get("statement"):
            errors.append("requirement")
        refs = requirement.get("evidence", [])
        if not refs:
            errors.append(f"requirement-no-evidence:{rid}")
        for ref in refs:
            if ref not in evidence_ids:
                errors.append(f"unknown-evidence:{rid}:{ref}")
    return errors


def validate_external_pin(pin_path, contract_path, contract_sha):
    if not pin_path:
        return {"status": "FAIL", "reason": "EXTERNAL_PIN_REQUIRED"}
    try:
        pin = load_json(pin_path)
    except Exception as exc:
        return {"status": "FAIL", "reason": "EXTERNAL_PIN_INVALID", "detail": str(exc)}
    if pin.get("schema") != PIN_SCHEMA:
        return {"status": "FAIL", "reason": "EXTERNAL_PIN_SCHEMA"}
    if pin.get("contract_sha256") != contract_sha:
        return {"status": "FAIL", "reason": "EXTERNAL_PIN_MISMATCH", "expected": contract_sha, "observed": pin.get("contract_sha256")}
    contract_ref = pin.get("contract")
    if contract_ref and Path(contract_ref).name != Path(contract_path).name:
        return {"status": "FAIL", "reason": "EXTERNAL_PIN_CONTRACT_MISMATCH", "observed": contract_ref}
    return {"status": "PASS", "contract_sha256": contract_sha, "preimplementation_commit": pin.get("preimplementation_commit")}


def acceptance(target, contract_path, external_pin=None):
    target = Path(target).resolve()
    contract_path = Path(contract_path).resolve()
    if not target.exists():
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "BLOCKED", "facts_status": "BLOCKED", "reason": "TARGET_MISSING"}
    try:
        contract = load_json(contract_path)
    except Exception as exc:
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "reason": "CONTRACT_INVALID_JSON", "detail": str(exc)}
    errors = validate_acceptance_contract(contract)
    sha = contract_sha256(contract)
    locked = contract.get("locked_sha256")
    if errors:
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "contract_sha256": sha, "contract_errors": errors}
    if locked != sha:
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "contract_sha256": sha, "locked_sha256": locked, "reason": "ACCEPTANCE_CONTRACT_CHANGED"}
    pin = validate_external_pin(external_pin, contract_path, sha)
    if pin.get("status") != "PASS":
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "contract_sha256": sha, "locked_sha256": locked, "pin": pin, "reason": pin.get("reason")}
    if is_native_or_opaque(target):
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "BLOCKED", "facts_status": "BLOCKED", "reason": "BLOCKED_NEEDS_SANDBOX", "target": str(target), "target_sha256": file_sha256(target)}
    contract_dir = contract_path.parent
    facts = [run_case(target, scenario, contract_dir=contract_dir) for scenario in contract.get("scenarios", [])]
    facts.extend(evidence_fact(contract_dir, evidence) for evidence in contract.get("evidence_files", []))
    by_id = {fact["id"]: fact for fact in facts}
    requirements = []
    for requirement in contract.get("requirements", []):
        refs = requirement.get("evidence", [])
        states = [by_id.get(ref, {}).get("status", "MISSING") for ref in refs]
        if states and all(state == "PASS" for state in states):
            state = "PASS"
        elif any(item == "BLOCKED" for item in states):
            state = "BLOCKED"
        else:
            state = "FAIL"
        requirements.append({"id": requirement["id"], "type": requirement.get("type", "MUST_WORK"), "statement": requirement["statement"], "status": state, "evidence": refs})
    if not facts or not requirements:
        facts_status = "INCONCLUSIVE"
    elif any(item["status"] == "BLOCKED" for item in requirements):
        facts_status = "BLOCKED"
    elif all(item["status"] == "PASS" for item in requirements):
        facts_status = "PASS"
    else:
        facts_status = "FAIL"
    return {
        "schema": SCHEMA,
        "runner_version": VERSION,
        "ai_contract_version": AI_CONTRACT_VERSION,
        "status": "PASS" if facts_status == "PASS" else facts_status,
        "mode": "feature_acceptance_facts",
        "facts_status": facts_status,
        "target": str(target),
        "target_sha256": file_sha256(target) if target.is_file() else None,
        "contract_id": contract["contract_id"],
        "target_id": contract["target_id"],
        "purpose": contract["purpose"],
        "contract_sha256": sha,
        "locked_sha256": locked,
        "external_pin": pin,
        "facts": facts,
        "requirements": requirements,
        "next_action": "AI_ASSESS_INTENT" if facts_status == "PASS" else "FIX_OR_REVIEW_ACCEPTANCE",
    }


def functionality(target, contract_path):
    if not contract_path:
        return {"status": "INCONCLUSIVE", "reason": "NO_FUNCTIONAL_CONTRACT"}
    try:
        contract = load_json(contract_path)
    except Exception as exc:
        return {"status": "FAIL", "reason": "CONTRACT_INVALID_JSON", "detail": str(exc)}
    if contract.get("schema") != FUNCTION_SCHEMA:
        return {"status": "FAIL", "reason": "FUNCTIONAL_CONTRACT_SCHEMA"}
    facts = [run_case(Path(target).resolve(), case, contract_dir=Path(contract_path).resolve().parent) for case in contract.get("cases", [])]
    if not facts:
        status = "INCONCLUSIVE"
    elif all(fact["status"] == "PASS" for fact in facts):
        status = "PASS"
    elif any(fact["status"] == "BLOCKED" for fact in facts):
        status = "BLOCKED"
    else:
        status = "FAIL"
    return {"status": status, "contract_sha256": contract_sha256(contract), "cases": facts}


def static_facts(target):
    target = Path(target)
    facts = {"exists": target.exists(), "is_file": target.is_file(), "size": target.stat().st_size if target.is_file() else None}
    if target.is_file():
        facts["sha256"] = file_sha256(target)
        facts["zipfile"] = zipfile.is_zipfile(target)
        if facts["zipfile"]:
            try:
                with zipfile.ZipFile(target) as archive:
                    facts["zip_test"] = archive.testzip() is None
            except Exception:
                facts["zip_test"] = False
    return facts


def run_validator(name, root):
    executable = shutil.which(name)
    if not executable:
        return {"available": False, "status": "UNAVAILABLE"}
    root = Path(root).resolve()
    if name == "ruff":
        cmd = [executable, "check", str(root), "--output-format", "json"]
    elif name == "bandit":
        cmd = [executable] + (["-r", str(root)] if root.is_dir() else [str(root)]) + ["-f", "json", "-q"]
    elif name == "mypy":
        cmd = [executable, str(root), "--no-error-summary"]
    elif name == "pytest":
        has_tests = (root.is_file() and root.name.startswith("test")) or (root.is_dir() and any(root.rglob("test*.py")))
        if not has_tests:
            return {"available": True, "status": "INCONCLUSIVE", "reason": "NO_TEST_FILES"}
        cmd = [executable, "-q", str(root)]
    else:
        has_tests = root.is_dir() and any(root.rglob("test*.py"))
        if not has_tests:
            return {"available": True, "status": "INCONCLUSIVE", "reason": "NO_TEST_FILES"}
        with tempfile.TemporaryDirectory(prefix="coverage-") as td:
            env = os.environ.copy()
            env["COVERAGE_FILE"] = str(Path(td) / ".coverage")
            run = subprocess.run([executable, "run", "-m", "pytest", "-q", str(root)], text=True, capture_output=True, env=env, timeout=180)
            report = subprocess.run([executable, "json", "-o", str(Path(td) / "coverage.json")], text=True, capture_output=True, env=env, timeout=60)
            percent = None
            path = Path(td) / "coverage.json"
            if path.is_file():
                try:
                    percent = json.loads(path.read_text(encoding="utf-8"))["totals"]["percent_covered"]
                except Exception:
                    pass
            return {"available": True, "status": "PASS" if run.returncode == 0 and report.returncode == 0 else "FAIL", "returncode": run.returncode, "coverage_percent": percent, "stdout": run.stdout[-2000:], "stderr": run.stderr[-1000:]}
    try:
        cp = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"available": True, "status": "BLOCKED", "reason": "VALIDATOR_TIMEOUT", "command": cmd}
    return {"available": True, "status": "PASS" if cp.returncode == 0 else "FAIL", "returncode": cp.returncode, "command": cmd, "stdout": cp.stdout[-3000:], "stderr": cp.stderr[-1500:]}


def validator_facts(root=None):
    available = {name: bool(shutil.which(name)) for name in VALIDATORS}
    results = {} if root is None else {name: run_validator(name, root) for name in VALIDATORS}
    return {"available": available, "results": results, "policy": "discover installed validators; do not auto-install"}


def flatten_statuses(result):
    out = {f"gate:{key}": str(value) for key, value in (result.get("gates") or {}).items()}
    for key, value in (((result.get("facts") or {}).get("validators") or {}).get("results") or {}).items():
        out[f"validator:{key}"] = str(value.get("status"))
    functionality_status = (((result.get("facts") or {}).get("functionality") or {}).get("status"))
    if functionality_status:
        out["functionality"] = str(functionality_status)
    acceptance_status = (result.get("feature_acceptance") or {}).get("facts_status")
    if acceptance_status:
        out["acceptance"] = str(acceptance_status)
    return out


def regression_facts(previous, current):
    if not previous:
        return {"status": "INCONCLUSIVE", "reason": "NO_PREVIOUS_RESULT", "newly_failing": [], "resolved": [], "changed": []}
    before = flatten_statuses(previous)
    after = flatten_statuses(current)
    newly_failing, resolved, changed = [], [], []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        changed.append({"key": key, "previous": old, "current": new})
        if new in BAD_STATES and old not in BAD_STATES:
            newly_failing.append(key)
        if old in BAD_STATES and new not in BAD_STATES:
            resolved.append(key)
    return {"status": "FAIL" if newly_failing else "PASS", "newly_failing": newly_failing, "resolved": resolved, "changed": changed}


def verify(target, functional_contract=None, acceptance_contract=None, external_pin=None, validator_root=None, previous_result=None):
    target = Path(target).resolve()
    static = static_facts(target)
    if not target.exists():
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "verdict": "FAIL", "reason": "TARGET_MISSING"}
    if is_native_or_opaque(target):
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "BLOCKED", "verdict": "BLOCKED", "reason": "BLOCKED_NEEDS_SANDBOX", "target": str(target), "facts": {"static": static}}
    function = functionality(target, functional_contract)
    validators = validator_facts(Path(validator_root).resolve() if validator_root else None)
    validator_states = [item.get("status") for item in validators.get("results", {}).values()]
    gates = {
        "functionality": function["status"],
        "safety": "INCONCLUSIVE",
        "performance": "INCONCLUSIVE",
        "compatibility": "PASS" if target.suffix.lower() in {".py", ".pyz", ".zip"} else "INCONCLUSIVE",
    }
    feature = acceptance(target, acceptance_contract, external_pin) if acceptance_contract else None
    if function["status"] in {"FAIL", "BLOCKED"} or any(state in {"FAIL", "BLOCKED"} for state in validator_states) or (feature and feature["facts_status"] in {"FAIL", "BLOCKED"}):
        verdict = "FAIL"
    elif function["status"] == "PASS" and (not feature or feature["facts_status"] == "PASS"):
        verdict = "PASS_WITH_INCONCLUSIVE_GATES" if "INCONCLUSIVE" in gates.values() or any(state == "INCONCLUSIVE" for state in validator_states) else "PASS"
    else:
        verdict = "INCONCLUSIVE"
    out = {
        "schema": SCHEMA,
        "runner_version": VERSION,
        "ai_contract_version": AI_CONTRACT_VERSION,
        "status": "PASS" if verdict.startswith("PASS") else verdict,
        "verdict": verdict,
        "target": str(target),
        "target_sha256": file_sha256(target) if target.is_file() else None,
        "facts": {"static": static, "validators": validators, "functionality": function},
        "gates": gates,
        "feature_acceptance": feature,
    }
    regression = regression_facts(previous_result, out)
    out["regression"] = regression
    if regression.get("newly_failing"):
        out["status"] = "FAIL"
        out["verdict"] = "FAIL"
        out["next_action"] = "FIX_REGRESSION"
    elif feature and feature.get("facts_status") == "PASS":
        out["next_action"] = "AI_ASSESS_INTENT"
    elif verdict == "INCONCLUSIVE":
        out["next_action"] = "REVIEW_FACTS"
    elif verdict.startswith("PASS"):
        out["next_action"] = "USE_VERIFIED_FACTS"
    else:
        out["next_action"] = "FIX_OR_BLOCK"
    return out


def capabilities():
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "runner_version": VERSION,
        "ai_contract_version": AI_CONTRACT_VERSION,
        "status": "PASS",
        "commands": ["capabilities", "self-test", "verify", "acceptance", "contract-hash", "request"],
        "validators": list(VALIDATORS),
        "regression_comparison": True,
        "feature_acceptance": {"schema": ACCEPTANCE_SCHEMA, "facts_only": True, "ai_intent_judgment_external": True, "mandatory_locked_sha256": True, "external_pin_required": True, "exact_target_sha256": True},
        "native_execution": "BLOCKED_NEEDS_SANDBOX",
    }


def self_test():
    checks = []
    def add(name, ok):
        checks.append({"name": name, "pass": bool(ok)})
    with tempfile.TemporaryDirectory(prefix="vr-self-") as td:
        root = Path(td)
        target = root / "target.py"
        target.write_text("import json,sys\nprint(json.dumps({'status':'PASS','echo':sys.argv[1:] if len(sys.argv)>1 else []}))\n", encoding="utf-8")
        functional = {"schema": FUNCTION_SCHEMA, "cases": [{"id": "f1", "args": ["x"], "expect": {"returncode_in": [0], "stdout_json_subset": {"status": "PASS", "echo": ["x"]}}}]}
        functional_path = root / "functional.json"
        functional_path.write_text(json.dumps(functional), encoding="utf-8")
        add("functional-contract-pass", verify(target, functional_path)["facts"]["functionality"]["status"] == "PASS")
        add("no-contract-inconclusive", verify(target)["facts"]["functionality"]["status"] == "INCONCLUSIVE")

        feature = {"schema": ACCEPTANCE_SCHEMA, "contract_id": "A", "target_id": "T", "purpose": "echo x", "requirements": [{"id": "R1", "type": "MUST_WORK", "statement": "echo", "evidence": ["S1"]}], "scenarios": [{"id": "S1", "args": ["x"], "expect": {"stdout_json_subset": {"status": "PASS", "echo": ["x"]}}}]}
        feature["locked_sha256"] = contract_sha256(feature)
        feature_path = root / "accept.json"
        feature_path.write_text(json.dumps(feature), encoding="utf-8")
        pin = {"schema": PIN_SCHEMA, "contract": feature_path.name, "contract_sha256": feature["locked_sha256"], "preimplementation_commit": "test"}
        pin_path = root / "pin.json"
        pin_path.write_text(json.dumps(pin), encoding="utf-8")
        accepted = acceptance(target, feature_path, pin_path)
        add("acceptance-pass-with-pin", accepted["facts_status"] == "PASS" and accepted["target_sha256"] == file_sha256(target))

        no_lock = json.loads(json.dumps(feature)); no_lock.pop("locked_sha256")
        no_lock_path = root / "nolock.json"; no_lock_path.write_text(json.dumps(no_lock), encoding="utf-8")
        add("missing-lock-fails", acceptance(target, no_lock_path, pin_path).get("facts_status") == "FAIL")

        drift = json.loads(json.dumps(feature)); drift["purpose"] = "changed"
        drift_path = root / "drift.json"; drift_path.write_text(json.dumps(drift), encoding="utf-8")
        add("locked-contract-drift", acceptance(target, drift_path, pin_path).get("reason") == "ACCEPTANCE_CONTRACT_CHANGED")

        bad_pin = dict(pin); bad_pin["contract_sha256"] = "0" * 64
        bad_pin_path = root / "bad-pin.json"; bad_pin_path.write_text(json.dumps(bad_pin), encoding="utf-8")
        add("external-pin-mismatch", acceptance(target, feature_path, bad_pin_path).get("reason") == "EXTERNAL_PIN_MISMATCH")

        evidence = root / "evidence.json"; evidence.write_text(json.dumps({"security": {"network": "blocked"}}), encoding="utf-8")
        feature2 = {"schema": ACCEPTANCE_SCHEMA, "contract_id": "B", "target_id": "T", "purpose": "evidence", "requirements": [{"id": "R", "statement": "network blocked", "evidence": ["E"]}], "scenarios": [], "evidence_files": [{"id": "E", "path": "evidence.json", "json_subset": {"security": {"network": "blocked"}}}]}
        feature2["locked_sha256"] = contract_sha256(feature2)
        feature2_path = root / "feature2.json"; feature2_path.write_text(json.dumps(feature2), encoding="utf-8")
        pin2_path = root / "pin2.json"; pin2_path.write_text(json.dumps({"schema": PIN_SCHEMA, "contract": feature2_path.name, "contract_sha256": feature2["locked_sha256"]}), encoding="utf-8")
        add("evidence-file-pass", acceptance(target, feature2_path, pin2_path)["facts_status"] == "PASS")

        empty = {"schema": ACCEPTANCE_SCHEMA, "contract_id": "C", "target_id": "T", "purpose": "empty", "requirements": [], "scenarios": []}
        empty["locked_sha256"] = contract_sha256(empty)
        empty_path = root / "empty.json"; empty_path.write_text(json.dumps(empty), encoding="utf-8")
        empty_pin = root / "empty-pin.json"; empty_pin.write_text(json.dumps({"schema": PIN_SCHEMA, "contract": empty_path.name, "contract_sha256": empty["locked_sha256"]}), encoding="utf-8")
        add("empty-inconclusive", acceptance(target, empty_path, empty_pin)["facts_status"] == "INCONCLUSIVE")

        native = root / "native.bin"; native.write_bytes(b"opaque fixture"); native.chmod(0o755)
        add("native-blocked", acceptance(native, feature_path, pin_path).get("reason") == "BLOCKED_NEEDS_SANDBOX")

        previous = {"gates": {"functionality": "PASS"}, "facts": {"validators": {"results": {"pytest": {"status": "PASS"}}}, "functionality": {"status": "PASS"}}}
        current = {"gates": {"functionality": "PASS"}, "facts": {"validators": {"results": {"pytest": {"status": "FAIL"}}}, "functionality": {"status": "PASS"}}}
        add("regression-new-failure", regression_facts(previous, current)["newly_failing"] == ["validator:pytest"])
        add("validator-discovery", set(validator_facts(None)["available"]) == set(VALIDATORS))
        add("capabilities-contract", capabilities()["feature_acceptance"]["external_pin_required"] is True)
    passed = sum(item["pass"] for item in checks)
    return {"schema": SCHEMA, "version": VERSION, "runner_version": VERSION, "ai_contract_version": AI_CONTRACT_VERSION, "status": "PASS" if passed == len(checks) else "FAIL", "passed": passed, "total": len(checks), "checks": checks}


def request(payload):
    operation = payload.get("operation") or payload.get("command")
    if operation == "capabilities": return capabilities()
    if operation == "self-test": return self_test()
    if operation == "contract-hash": return {"schema": SCHEMA, "status": "PASS", "contract_sha256": contract_sha256(load_json(payload["contract"]))}
    if operation == "acceptance": return acceptance(Path(payload["target"]), Path(payload["contract"]), Path(payload["external_pin"]) if payload.get("external_pin") else None)
    if operation == "verify":
        return verify(
            Path(payload["target"]),
            Path(payload["functional_contract"]) if payload.get("functional_contract") else None,
            Path(payload["acceptance_contract"]) if payload.get("acceptance_contract") else None,
            Path(payload["external_pin"]) if payload.get("external_pin") else None,
            Path(payload["validator_root"]) if payload.get("validator_root") else None,
            load_json(payload["previous_result"]) if payload.get("previous_result") else None,
        )
    return {"schema": SCHEMA, "status": "FAIL", "reason": "UNKNOWN_OPERATION"}


def main():
    parser = argparse.ArgumentParser(description="AI-first deterministic fact confirmation and feature acceptance evidence runner")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("capabilities")
    sub.add_parser("self-test")
    q = sub.add_parser("contract-hash"); q.add_argument("contract")
    q = sub.add_parser("acceptance"); q.add_argument("target"); q.add_argument("--contract", required=True); q.add_argument("--external-pin", required=True)
    q = sub.add_parser("verify"); q.add_argument("target"); q.add_argument("--functional-contract", "--contract", dest="functional_contract"); q.add_argument("--acceptance-contract"); q.add_argument("--external-pin"); q.add_argument("--validator-root"); q.add_argument("--previous-result")
    q = sub.add_parser("request"); q.add_argument("source", nargs="?", default="-"); q.add_argument("--json-file")
    args = parser.parse_args()
    command = args.command or "capabilities"
    if command == "capabilities": out = capabilities()
    elif command == "self-test": out = self_test()
    elif command == "contract-hash": out = {"schema": SCHEMA, "status": "PASS", "contract_sha256": contract_sha256(load_json(args.contract))}
    elif command == "acceptance": out = acceptance(Path(args.target), Path(args.contract), Path(args.external_pin))
    elif command == "verify": out = verify(Path(args.target), Path(args.functional_contract) if args.functional_contract else None, Path(args.acceptance_contract) if args.acceptance_contract else None, Path(args.external_pin) if args.external_pin else None, Path(args.validator_root) if args.validator_root else None, load_json(args.previous_result) if args.previous_result else None)
    else:
        payload = load_json(args.json_file) if args.json_file else json.load(sys.stdin) if args.source == "-" else load_json(args.source)
        out = request(payload)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("status") in {"PASS", "INCONCLUSIVE", "PASS_WITH_INCONCLUSIVE_GATES"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
