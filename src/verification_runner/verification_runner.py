#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, zipfile
from pathlib import Path

VERSION = "0.3.0"
AI_CONTRACT_VERSION = "offload-ai/1"
SCHEMA = "verification-runner/0.3"
ACCEPTANCE_SCHEMA = "offload-feature-acceptance/1"
ASSESSMENT_SCHEMA = "offload-feature-intent-assessment/1"
FUNCTION_SCHEMA = "offload-functional-contract/1"


def jdump(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_contract_payload(data: dict) -> dict:
    d = json.loads(json.dumps(data))
    d.pop("locked_sha256", None)
    return d


def contract_sha256(data: dict) -> str:
    return hashlib.sha256(jdump(canonical_contract_payload(data)).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_subset(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and json_subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return len(actual) >= len(expected) and all(json_subset(a, e) for a, e in zip(actual, expected))
    return actual == expected


def resolve_tokens(value, *, target: Path, workdir: Path, contract_dir: Path):
    if isinstance(value, str):
        return (value.replace("{target}", str(target))
                     .replace("{workdir}", str(workdir))
                     .replace("{contract_dir}", str(contract_dir)))
    if isinstance(value, list):
        return [resolve_tokens(v, target=target, workdir=workdir, contract_dir=contract_dir) for v in value]
    if isinstance(value, dict):
        return {k: resolve_tokens(v, target=target, workdir=workdir, contract_dir=contract_dir) for k, v in value.items()}
    return value


def run_case(target: Path, case: dict, *, contract_dir: Path) -> dict:
    cid = str(case.get("id") or "unnamed")
    timeout = float(case.get("timeout_seconds", 60))
    with tempfile.TemporaryDirectory(prefix="verify-case-") as td:
        workdir = Path(td)
        args = resolve_tokens(case.get("args", []), target=target, workdir=workdir, contract_dir=contract_dir)
        stdin_text = case.get("stdin_text")
        if "stdin_json" in case:
            stdin_text = json.dumps(resolve_tokens(case["stdin_json"], target=target, workdir=workdir, contract_dir=contract_dir), ensure_ascii=False)
        env = os.environ.copy()
        for k, v in resolve_tokens(case.get("env", {}), target=target, workdir=workdir, contract_dir=contract_dir).items():
            env[str(k)] = str(v)
        for item in case.get("precreate", []):
            rel = resolve_tokens(item["path"], target=target, workdir=workdir, contract_dir=contract_dir)
            p = Path(rel)
            if not p.is_absolute(): p = workdir / p
            p.parent.mkdir(parents=True, exist_ok=True)
            if item.get("kind", "file") == "dir": p.mkdir(parents=True, exist_ok=True)
            else: p.write_text(str(item.get("content", "")), encoding="utf-8")
        cmd = [sys.executable, str(target), *map(str, args)] if target.suffix == ".pyz" or target.suffix == ".py" else [str(target), *map(str, args)]
        started = time.perf_counter()
        try:
            cp = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, cwd=workdir, env=env, timeout=timeout, shell=False)
            elapsed = time.perf_counter() - started
        except subprocess.TimeoutExpired as exc:
            return {"id": cid, "status": "BLOCKED", "reason": "TIMEOUT", "elapsed_seconds": timeout,
                    "stdout": (exc.stdout or "")[:2000], "stderr": (exc.stderr or "")[:2000]}
        except Exception as exc:
            return {"id": cid, "status": "BLOCKED", "reason": f"EXEC_ERROR:{type(exc).__name__}", "detail": str(exc)[:500]}
        exp = case.get("expect", {})
        checks = []
        def ck(name, ok, observed=None, expected=None):
            checks.append({"name": name, "pass": bool(ok), "observed": observed, "expected": expected})
        allowed = exp.get("returncode_in", [0])
        ck("returncode", cp.returncode in allowed, cp.returncode, allowed)
        if "stdout_contains" in exp:
            vals = exp["stdout_contains"] if isinstance(exp["stdout_contains"], list) else [exp["stdout_contains"]]
            for s in vals: ck(f"stdout_contains:{s}", str(s) in cp.stdout)
        if "stdout_not_contains" in exp:
            vals = exp["stdout_not_contains"] if isinstance(exp["stdout_not_contains"], list) else [exp["stdout_not_contains"]]
            for s in vals: ck(f"stdout_not_contains:{s}", str(s) not in cp.stdout)
        if "stderr_contains" in exp:
            vals = exp["stderr_contains"] if isinstance(exp["stderr_contains"], list) else [exp["stderr_contains"]]
            for s in vals: ck(f"stderr_contains:{s}", str(s) in cp.stderr)
        if "stderr_not_contains" in exp:
            vals = exp["stderr_not_contains"] if isinstance(exp["stderr_not_contains"], list) else [exp["stderr_not_contains"]]
            for s in vals: ck(f"stderr_not_contains:{s}", str(s) not in cp.stderr)
        parsed = None
        if "stdout_json_subset" in exp:
            try: parsed = json.loads(cp.stdout)
            except Exception: parsed = None
            expected = resolve_tokens(exp["stdout_json_subset"], target=target, workdir=workdir, contract_dir=contract_dir)
            ck("stdout_json_subset", parsed is not None and json_subset(parsed, expected), parsed, expected)
        for rel in exp.get("files_present", []):
            p = Path(resolve_tokens(rel, target=target, workdir=workdir, contract_dir=contract_dir))
            if not p.is_absolute(): p = workdir / p
            ck(f"file_present:{rel}", p.exists())
        for rel in exp.get("files_absent", []):
            p = Path(resolve_tokens(rel, target=target, workdir=workdir, contract_dir=contract_dir))
            if not p.is_absolute(): p = workdir / p
            ck(f"file_absent:{rel}", not p.exists())
        status = "PASS" if checks and all(c["pass"] for c in checks) else "FAIL"
        return {"id": cid, "status": status, "elapsed_seconds": round(elapsed, 6), "returncode": cp.returncode,
                "checks": checks, "stdout": cp.stdout[:4000], "stderr": cp.stderr[:2000]}


def evidence_fact(contract_dir: Path, spec: dict) -> dict:
    eid = str(spec.get("id") or "unnamed-evidence")
    rel = spec.get("path")
    if not rel:
        return {"id": eid, "status": "FAIL", "reason": "MISSING_PATH"}
    path = Path(rel)
    if not path.is_absolute(): path = (contract_dir / path).resolve()
    if not path.is_file(): return {"id": eid, "status": "FAIL", "reason": "EVIDENCE_FILE_MISSING", "path": str(path)}
    try: data = load_json(path)
    except Exception as exc: return {"id": eid, "status": "FAIL", "reason": "EVIDENCE_JSON_INVALID", "detail": str(exc)}
    expected = spec.get("json_subset", {})
    ok = json_subset(data, expected)
    return {"id": eid, "status": "PASS" if ok else "FAIL", "path": str(path), "sha256": file_sha256(path), "expected_subset": expected}


def validate_acceptance_contract(data: dict) -> list[str]:
    errs = []
    if data.get("schema") != ACCEPTANCE_SCHEMA: errs.append("schema")
    for k in ("contract_id", "target_id", "purpose", "requirements", "scenarios"):
        if k not in data: errs.append(f"missing:{k}")
    ids = set()
    for s in data.get("scenarios", []):
        sid = s.get("id")
        if not sid or sid in ids: errs.append("scenario-id")
        ids.add(sid)
    for e in data.get("evidence_files", []):
        eid = e.get("id")
        if not eid or eid in ids: errs.append("evidence-id")
        ids.add(eid)
    for r in data.get("requirements", []):
        rid = r.get("id")
        if not rid or not r.get("statement"): errs.append("requirement")
        refs = r.get("evidence", [])
        if not refs: errs.append(f"requirement-no-evidence:{rid}")
        for ref in refs:
            if ref not in ids: errs.append(f"unknown-evidence:{rid}:{ref}")
    return errs


def acceptance(target: Path, contract_path: Path) -> dict:
    target = target.resolve(); contract_path = contract_path.resolve(); contract_dir = contract_path.parent
    if not target.exists():
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "BLOCKED", "facts_status": "BLOCKED", "reason": "TARGET_MISSING"}
    try: c = load_json(contract_path)
    except Exception as exc:
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "reason": "CONTRACT_INVALID_JSON", "detail": str(exc)}
    errs = validate_acceptance_contract(c); sha = contract_sha256(c); locked = c.get("locked_sha256")
    if errs:
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "contract_sha256": sha, "contract_errors": errs}
    if locked and locked != sha:
        return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "facts_status": "FAIL", "contract_sha256": sha, "locked_sha256": locked, "reason": "ACCEPTANCE_CONTRACT_CHANGED"}
    scenario_facts = [run_case(target, s, contract_dir=contract_dir) for s in c.get("scenarios", [])]
    file_facts = [evidence_fact(contract_dir, e) for e in c.get("evidence_files", [])]
    facts = scenario_facts + file_facts
    byid = {f["id"]: f for f in facts}
    reqs = []
    for r in c.get("requirements", []):
        refs = r.get("evidence", []); statuses = [byid.get(x, {}).get("status", "MISSING") for x in refs]
        st = "PASS" if statuses and all(x == "PASS" for x in statuses) else "BLOCKED" if any(x == "BLOCKED" for x in statuses) else "FAIL"
        reqs.append({"id": r["id"], "type": r.get("type", "MUST_WORK"), "statement": r["statement"], "status": st, "evidence": refs})
    if not facts or not reqs: fs = "INCONCLUSIVE"
    elif any(r["status"] == "BLOCKED" for r in reqs): fs = "BLOCKED"
    elif all(r["status"] == "PASS" for r in reqs): fs = "PASS"
    else: fs = "FAIL"
    return {"schema": SCHEMA, "runner_version": VERSION, "ai_contract_version": AI_CONTRACT_VERSION,
            "status": "PASS" if fs == "PASS" else fs, "mode": "feature_acceptance_facts", "facts_status": fs,
            "target": str(target), "target_sha256": file_sha256(target) if target.is_file() else None,
            "contract_id": c["contract_id"], "target_id": c["target_id"], "purpose": c["purpose"],
            "contract_sha256": sha, "locked_sha256": locked, "facts": facts, "requirements": reqs,
            "next_action": "AI_ASSESS_INTENT" if fs == "PASS" else "FIX_OR_REVIEW_ACCEPTANCE"}


def functionality(target: Path, contract_path: Path | None) -> dict:
    if not contract_path:
        return {"status": "INCONCLUSIVE", "reason": "NO_FUNCTIONAL_CONTRACT"}
    try: c = load_json(contract_path)
    except Exception as exc: return {"status": "FAIL", "reason": "CONTRACT_INVALID_JSON", "detail": str(exc)}
    if c.get("schema") != FUNCTION_SCHEMA: return {"status": "FAIL", "reason": "FUNCTIONAL_CONTRACT_SCHEMA"}
    facts = [run_case(target.resolve(), x, contract_dir=contract_path.resolve().parent) for x in c.get("cases", [])]
    if not facts: st = "INCONCLUSIVE"
    elif all(x["status"] == "PASS" for x in facts): st = "PASS"
    elif any(x["status"] == "BLOCKED" for x in facts): st = "BLOCKED"
    else: st = "FAIL"
    return {"status": st, "contract_sha256": contract_sha256(c), "cases": facts}


def static_facts(target: Path) -> dict:
    facts = {"exists": target.exists(), "is_file": target.is_file(), "size": target.stat().st_size if target.exists() else None}
    if target.is_file():
        facts["sha256"] = file_sha256(target)
        facts["zipfile"] = zipfile.is_zipfile(target)
        if facts["zipfile"]:
            try:
                with zipfile.ZipFile(target) as z: facts["zip_test"] = z.testzip() is None
            except Exception: facts["zip_test"] = False
    return facts


def validator_facts(target: Path) -> dict:
    available = {name: bool(shutil.which(name)) for name in ("ruff", "bandit", "mypy", "pytest", "coverage")}
    return {"available": available, "policy": "discover-only; no auto-install"}


def verify(target: Path, functional_contract: Path | None = None, acceptance_contract: Path | None = None) -> dict:
    target = target.resolve(); static = static_facts(target)
    if not target.exists(): return {"schema": SCHEMA, "runner_version": VERSION, "status": "FAIL", "verdict": "FAIL", "reason": "TARGET_MISSING"}
    fn = functionality(target, functional_contract)
    gates = {
        "functionality": fn["status"],
        "safety": "PASS" if target.is_file() else "INCONCLUSIVE",
        "performance": "INCONCLUSIVE",
        "compatibility": "PASS" if (target.suffix in (".py", ".pyz", ".zip") or os.access(target, os.X_OK)) else "INCONCLUSIVE",
    }
    acc = acceptance(target, acceptance_contract) if acceptance_contract else None
    if fn["status"] in ("FAIL", "BLOCKED") or (acc and acc["facts_status"] in ("FAIL", "BLOCKED")): verdict = "FAIL"
    elif fn["status"] == "PASS" and (not acc or acc["facts_status"] == "PASS"): verdict = "PASS_WITH_INCONCLUSIVE_GATES" if "INCONCLUSIVE" in gates.values() else "PASS"
    else: verdict = "INCONCLUSIVE"
    return {"schema": SCHEMA, "runner_version": VERSION, "ai_contract_version": AI_CONTRACT_VERSION,
            "status": "PASS" if verdict.startswith("PASS") else verdict, "verdict": verdict, "target": str(target),
            "facts": {"static": static, "validators": validator_facts(target), "functionality": fn}, "gates": gates,
            "feature_acceptance": acc, "next_action": "AI_ASSESS_INTENT" if acc and acc.get("facts_status") == "PASS" else "REVIEW_FACTS" if verdict == "INCONCLUSIVE" else "USE_VERIFIED_FACTS" if verdict.startswith("PASS") else "FIX_OR_BLOCK"}


def capabilities():
    return {"schema": SCHEMA, "version": VERSION, "runner_version": VERSION, "ai_contract_version": AI_CONTRACT_VERSION, "status": "PASS",
            "commands": ["capabilities", "self-test", "verify", "acceptance", "contract-hash", "request"],
            "feature_acceptance": {"schema": ACCEPTANCE_SCHEMA, "facts_only": True, "ai_intent_judgment_external": True}}


def self_test():
    checks = []
    def add(name, ok): checks.append({"name": name, "pass": bool(ok)})
    with tempfile.TemporaryDirectory(prefix="vr-self-") as td:
        root = Path(td); tgt = root / "target.py"
        tgt.write_text("import json,sys\nprint(json.dumps({'status':'PASS','echo':sys.argv[1:] if len(sys.argv)>1 else []}))\n", encoding="utf-8")
        fc = {"schema": FUNCTION_SCHEMA, "cases": [{"id":"f1","args":["x"],"expect":{"returncode_in":[0],"stdout_json_subset":{"status":"PASS","echo":["x"]}}}]}
        fcp = root / "functional.json"; fcp.write_text(json.dumps(fc), encoding="utf-8")
        vr = verify(tgt, fcp); add("functional-contract-pass", vr["facts"]["functionality"]["status"] == "PASS")
        vr2 = verify(tgt); add("no-contract-inconclusive", vr2["facts"]["functionality"]["status"] == "INCONCLUSIVE")
        ac = {"schema": ACCEPTANCE_SCHEMA,"contract_id":"A","target_id":"T","purpose":"echo x","requirements":[{"id":"R1","type":"MUST_WORK","statement":"echo","evidence":["S1"]}],"scenarios":[{"id":"S1","args":["x"],"expect":{"stdout_json_subset":{"status":"PASS","echo":["x"]}}}]}
        sha = contract_sha256(ac); ac["locked_sha256"] = sha
        acp=root/"accept.json"; acp.write_text(json.dumps(ac),encoding="utf-8")
        ar=acceptance(tgt,acp); add("acceptance-pass", ar["facts_status"]=="PASS" and ar["contract_sha256"]==sha)
        bad=json.loads(json.dumps(ac)); bad["purpose"]="changed"; (root/"bad.json").write_text(json.dumps(bad),encoding="utf-8")
        br=acceptance(tgt,root/"bad.json"); add("locked-contract-drift",br.get("reason")=="ACCEPTANCE_CONTRACT_CHANGED")
        ev=root/"evidence.json"; ev.write_text(json.dumps({"security":{"network":"blocked"}}),encoding="utf-8")
        ac2={"schema":ACCEPTANCE_SCHEMA,"contract_id":"B","target_id":"T","purpose":"evidence","requirements":[{"id":"R","statement":"network blocked","evidence":["E"]}],"scenarios":[],"evidence_files":[{"id":"E","path":"evidence.json","json_subset":{"security":{"network":"blocked"}}}]}
        ac2["locked_sha256"]=contract_sha256(ac2); (root/"evc.json").write_text(json.dumps(ac2),encoding="utf-8")
        er=acceptance(tgt,root/"evc.json"); add("evidence-file-pass",er["facts_status"]=="PASS")
        add("capabilities-contract",capabilities()["ai_contract_version"]==AI_CONTRACT_VERSION)
        add("canonical-hash-stable",contract_sha256({"b":1,"a":2})==contract_sha256({"a":2,"b":1}))
        empty={"schema":ACCEPTANCE_SCHEMA,"contract_id":"C","target_id":"T","purpose":"empty","requirements":[],"scenarios":[]}; empty["locked_sha256"]=contract_sha256(empty); (root/"empty.json").write_text(json.dumps(empty),encoding="utf-8")
        add("empty-inconclusive",acceptance(tgt,root/"empty.json")["facts_status"]=="INCONCLUSIVE")
    n=sum(x["pass"] for x in checks)
    return {"schema": SCHEMA, "version": VERSION, "runner_version": VERSION, "ai_contract_version": AI_CONTRACT_VERSION, "status":"PASS" if n==len(checks) else "FAIL","passed":n,"total":len(checks),"checks":checks}


def request(payload: dict) -> dict:
    op=payload.get("operation") or payload.get("command")
    if op=="capabilities": return capabilities()
    if op=="self-test": return self_test()
    if op=="contract-hash":
        c=load_json(payload["contract"]); return {"schema":SCHEMA,"status":"PASS","contract_sha256":contract_sha256(c)}
    if op=="acceptance": return acceptance(Path(payload["target"]),Path(payload["contract"]))
    if op=="verify": return verify(Path(payload["target"]),Path(payload["functional_contract"]) if payload.get("functional_contract") else None,Path(payload["acceptance_contract"]) if payload.get("acceptance_contract") else None)
    return {"schema":SCHEMA,"status":"FAIL","reason":"UNKNOWN_OPERATION"}


def main():
    p=argparse.ArgumentParser(description="AI-first deterministic fact confirmation and feature acceptance evidence runner")
    sp=p.add_subparsers(dest="command")
    sp.add_parser("capabilities"); sp.add_parser("self-test")
    q=sp.add_parser("contract-hash"); q.add_argument("contract")
    q=sp.add_parser("acceptance"); q.add_argument("target"); q.add_argument("--contract",required=True)
    q=sp.add_parser("verify"); q.add_argument("target"); q.add_argument("--functional-contract","--contract",dest="functional_contract"); q.add_argument("--acceptance-contract")
    q=sp.add_parser("request"); q.add_argument("source",nargs="?",default="-"); q.add_argument("--json-file")
    a=p.parse_args(); cmd=a.command or "capabilities"
    if cmd=="capabilities": out=capabilities()
    elif cmd=="self-test": out=self_test()
    elif cmd=="contract-hash": out={"schema":SCHEMA,"status":"PASS","contract_sha256":contract_sha256(load_json(a.contract))}
    elif cmd=="acceptance": out=acceptance(Path(a.target),Path(a.contract))
    elif cmd=="verify": out=verify(Path(a.target),Path(a.functional_contract) if a.functional_contract else None,Path(a.acceptance_contract) if a.acceptance_contract else None)
    else:
        if a.json_file: payload=load_json(a.json_file)
        elif a.source=="-": payload=json.load(sys.stdin)
        else: payload=load_json(a.source)
        out=request(payload)
    print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out.get("status") in ("PASS","INCONCLUSIVE","PASS_WITH_INCONCLUSIVE_GATES") else 1

if __name__=="__main__": raise SystemExit(main())
