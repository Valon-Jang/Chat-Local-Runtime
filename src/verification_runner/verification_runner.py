#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time, zipfile
from pathlib import Path

VERSION = "0.3.1"
AI_CONTRACT_VERSION = "offload-ai/1"
SCHEMA = "verification-runner/0.3"
ACCEPTANCE_SCHEMA = "offload-feature-acceptance/1"
PIN_SCHEMA = "offload-feature-pin/1"
FUNCTION_SCHEMA = "offload-functional-contract/1"
VALIDATORS = ("ruff", "bandit", "mypy", "pytest", "coverage")
BAD_STATES = {"FAIL", "BLOCKED", "ERROR"}

def jdump(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def canonical_contract_payload(data):
    d=json.loads(json.dumps(data)); d.pop("locked_sha256",None); return d
def contract_sha256(data): return hashlib.sha256(jdump(canonical_contract_payload(data)).encode("utf-8")).hexdigest()
def file_sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""): h.update(chunk)
    return h.hexdigest()
def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))

def json_subset(actual, expected):
    if isinstance(expected,dict): return isinstance(actual,dict) and all(k in actual and json_subset(actual[k],v) for k,v in expected.items())
    if isinstance(expected,list): return isinstance(actual,list) and len(actual)>=len(expected) and all(json_subset(a,e) for a,e in zip(actual,expected))
    return actual==expected

def resolve_tokens(value,*,target,workdir,contract_dir):
    if isinstance(value,str): return value.replace("{target}",str(target)).replace("{workdir}",str(workdir)).replace("{contract_dir}",str(contract_dir))
    if isinstance(value,list): return [resolve_tokens(v,target=target,workdir=workdir,contract_dir=contract_dir) for v in value]
    if isinstance(value,dict): return {k:resolve_tokens(v,target=target,workdir=workdir,contract_dir=contract_dir) for k,v in value.items()}
    return value

def is_python_target(target): return Path(target).suffix.lower() in {".py",".pyz"}
def is_native_or_opaque(target):
    target=Path(target)
    if target.is_dir() or is_python_target(target) or target.suffix.lower() in {".zip",".json",".toml",".yaml",".yml",".md",".txt"}: return False
    return os.access(target,os.X_OK) or target.is_file()

def run_case(target,case,*,contract_dir):
    target=Path(target); cid=str(case.get("id") or "unnamed"); timeout=float(case.get("timeout_seconds",60))
    if is_native_or_opaque(target): return {"id":cid,"status":"BLOCKED","reason":"BLOCKED_NEEDS_SANDBOX"}
    with tempfile.TemporaryDirectory(prefix="verify-case-") as td:
        workdir=Path(td); args=resolve_tokens(case.get("args",[]),target=target,workdir=workdir,contract_dir=contract_dir)
        stdin_text=case.get("stdin_text")
        if "stdin_json" in case: stdin_text=json.dumps(resolve_tokens(case["stdin_json"],target=target,workdir=workdir,contract_dir=contract_dir),ensure_ascii=False)
        env=os.environ.copy(); env.update({str(k):str(v) for k,v in resolve_tokens(case.get("env",{}),target=target,workdir=workdir,contract_dir=contract_dir).items()})
        for item in case.get("precreate",[]):
            rel=resolve_tokens(item["path"],target=target,workdir=workdir,contract_dir=contract_dir); p=Path(rel)
            if not p.is_absolute(): p=workdir/p
            p.parent.mkdir(parents=True,exist_ok=True)
            if item.get("kind","file")=="dir": p.mkdir(parents=True,exist_ok=True)
            else: p.write_text(str(item.get("content","")),encoding="utf-8")
        cmd=[sys.executable,str(target),*map(str,args)] if is_python_target(target) else [str(target),*map(str,args)]
        started=time.perf_counter()
        try: cp=subprocess.run(cmd,input=stdin_text,text=True,capture_output=True,cwd=workdir,env=env,timeout=timeout,shell=False); elapsed=time.perf_counter()-started
        except subprocess.TimeoutExpired as exc: return {"id":cid,"status":"BLOCKED","reason":"TIMEOUT","elapsed_seconds":timeout,"stdout":(exc.stdout or "")[:2000],"stderr":(exc.stderr or "")[:2000]}
        except Exception as exc: return {"id":cid,"status":"BLOCKED","reason":f"EXEC_ERROR:{type(exc).__name__}","detail":str(exc)[:500]}
        exp=case.get("expect",{}); checks=[]
        def ck(name,ok,observed=None,expected=None): checks.append({"name":name,"pass":bool(ok),"observed":observed,"expected":expected})
        allowed=exp.get("returncode_in",[0]); ck("returncode",cp.returncode in allowed,cp.returncode,allowed)
        for key,stream,positive in (("stdout_contains",cp.stdout,True),("stdout_not_contains",cp.stdout,False),("stderr_contains",cp.stderr,True),("stderr_not_contains",cp.stderr,False)):
            if key in exp:
                vals=exp[key] if isinstance(exp[key],list) else [exp[key]]
                for s in vals:
                    ok=str(s) in stream; ck(f"{key}:{s}",ok if positive else not ok)
        if "stdout_json_subset" in exp:
            try: parsed=json.loads(cp.stdout)
            except Exception: parsed=None
            expected=resolve_tokens(exp["stdout_json_subset"],target=target,workdir=workdir,contract_dir=contract_dir); ck("stdout_json_subset",parsed is not None and json_subset(parsed,expected),parsed,expected)
        for rel in exp.get("files_present",[]):
            p=Path(resolve_tokens(rel,target=target,workdir=workdir,contract_dir=contract_dir)); p=p if p.is_absolute() else workdir/p; ck(f"file_present:{rel}",p.exists())
        for rel in exp.get("files_absent",[]):
            p=Path(resolve_tokens(rel,target=target,workdir=workdir,contract_dir=contract_dir)); p=p if p.is_absolute() else workdir/p; ck(f"file_absent:{rel}",not p.exists())
        status="PASS" if checks and all(c["pass"] for c in checks) else "FAIL"
        return {"id":cid,"status":status,"elapsed_seconds":round(elapsed,6),"returncode":cp.returncode,"checks":checks,"stdout":cp.stdout[:4000],"stderr":cp.stderr[:2000]}

def evidence_fact(contract_dir,spec):
    eid=str(spec.get("id") or "unnamed-evidence"); rel=spec.get("path")
    if not rel: return {"id":eid,"status":"FAIL","reason":"MISSING_PATH"}
    path=Path(rel); path=path if path.is_absolute() else (Path(contract_dir)/path).resolve()
    if not path.is_file(): return {"id":eid,"status":"FAIL","reason":"EVIDENCE_FILE_MISSING","path":str(path)}
    try: data=load_json(path)
    except Exception as exc: return {"id":eid,"status":"FAIL","reason":"EVIDENCE_JSON_INVALID","detail":str(exc)}
    expected=spec.get("json_subset",{}); ok=json_subset(data,expected)
    return {"id":eid,"status":"PASS" if ok else "FAIL","path":str(path),"sha256":file_sha256(path),"expected_subset":expected}

def validate_acceptance_contract(data):
    errs=[]
    if data.get("schema")!=ACCEPTANCE_SCHEMA: errs.append("schema")
    for k in ("contract_id","target_id","purpose","requirements","scenarios","locked_sha256"):
        if k not in data: errs.append(f"missing:{k}")
    ids=set()
    for s in data.get("scenarios",[]):
        sid=s.get("id")
        if not sid or sid in ids: errs.append("scenario-id")
        ids.add(sid)
    for e in data.get("evidence_files",[]):
        eid=e.get("id")
        if not eid or eid in ids: errs.append("evidence-id")
        ids.add(eid)
    for r in data.get("requirements",[]):
        rid=r.get("id")
        if not rid or not r.get("statement"): errs.append("requirement")
        refs=r.get("evidence",[])
        if not refs: errs.append(f"requirement-no-evidence:{rid}")
        for ref in refs:
            if ref not in ids: errs.append(f"unknown-evidence:{rid}:{ref}")
    return errs

def validate_external_pin(pin_path,contract_path,contract_sha):
    if not pin_path: return {"status":"FAIL","reason":"EXTERNAL_PIN_REQUIRED"}
    try: pin=load_json(pin_path)
    except Exception as exc: return {"status":"FAIL","reason":"EXTERNAL_PIN_INVALID","detail":str(exc)}
    if pin.get("schema")!=PIN_SCHEMA: return {"status":"FAIL","reason":"EXTERNAL_PIN_SCHEMA"}
    if pin.get("contract_sha256")!=contract_sha: return {"status":"FAIL","reason":"EXTERNAL_PIN_MISMATCH","expected":contract_sha,"observed":pin.get("contract_sha256")}
    cref=pin.get("contract")
    if cref and Path(cref).name!=Path(contract_path).name: return {"status":"FAIL","reason":"EXTERNAL_PIN_CONTRACT_MISMATCH","observed":cref}
    return {"status":"PASS","contract_sha256":contract_sha,"preimplementation_commit":pin.get("preimplementation_commit")}

def acceptance(target,contract_path,external_pin=None):
    target=Path(target).resolve(); contract_path=Path(contract_path).resolve(); contract_dir=contract_path.parent
    if not target.exists(): return {"schema":SCHEMA,"runner_version":VERSION,"status":"BLOCKED","facts_status":"BLOCKED","reason":"TARGET_MISSING"}
    try: c=load_json(contract_path)
    except Exception as exc: return {"schema":SCHEMA,"runner_version":VERSION,"status":"FAIL","facts_status":"FAIL","reason":"CONTRACT_INVALID_JSON","detail":str(exc)}
    errs=validate_acceptance_contract(c); sha=contract_sha256(c); locked=c.get("locked_sha256")
    if errs: return {"schema":SCHEMA,"runner_version":VERSION,"status":"FAIL","facts_status":"FAIL","contract_sha256":sha,"contract_errors":errs}
    if locked!=sha: return {"schema":SCHEMA,"runner_version":VERSION,"status":"FAIL","facts_status":"FAIL","contract_sha256":sha,"locked_sha256":locked,"reason":"ACCEPTANCE_CONTRACT_CHANGED"}
    pin=validate_external_pin(external_pin,contract_path,sha)
    if pin["status"]!="PASS": return {"schema":SCHEMA,"runner_version":VERSION,"status":"FAIL","facts_status":"FAIL","contract_sha256":sha,"locked_sha256":locked,**pin}
    if is_native_or_opaque(target): return {"schema":SCHEMA,"runner_version":VERSION,"status":"BLOCKED","facts_status":"BLOCKED","reason":"BLOCKED_NEEDS_SANDBOX","target":str(target),"target_sha256":file_sha256(target)}
    facts=[run_case(target,s,contract_dir=contract_dir) for s in c.get("scenarios",[])]+[evidence_fact(contract_dir,e) for e in c.get("evidence_files",[])]
    byid={f["id"]:f for f in facts}; reqs=[]
    for r in c.get("requirements",[]):
        refs=r.get("evidence",[]); statuses=[byid.get(x,{}).get("status","MISSING") for x in refs]
        st="PASS" if statuses and all(x=="PASS" for x in statuses) else "BLOCKED" if any(x=="BLOCKED" for x in statuses) else "FAIL"
        reqs.append({"id":r["id"],"type":r.get("type","MUST_WORK"),"statement":r["statement"],"status":st,"evidence":refs})
    if not facts or not reqs: fs="INCONCLUSIVE"
    elif any(r["status"]=="BLOCKED" for r in reqs): fs="BLOCKED"
    elif all(r["status"]=="PASS" for r in reqs): fs="PASS"
    else: fs="FAIL"
    return {"schema":SCHEMA,"runner_version":VERSION,"ai_contract_version":AI_CONTRACT_VERSION,"status":"PASS" if fs=="PASS" else fs,"mode":"feature_acceptance_facts","facts_status":fs,"target":str(target),"target_sha256":file_sha256(target) if target.is_file() else None,"contract_id":c["contract_id"],"target_id":c["target_id"],"purpose":c["purpose"],"contract_sha256":sha,"locked_sha256":locked,"external_pin":pin,"facts":facts,"requirements":reqs,"next_action":"AI_ASSESS_INTENT" if fs=="PASS" else "FIX_OR_REVIEW_ACCEPTANCE"}

def functionality(target,contract_path):
    if not contract_path: return {"status":"INCONCLUSIVE","reason":"NO_FUNCTIONAL_CONTRACT"}
    try: c=load_json(contract_path)
    except Exception as exc: return {"status":"FAIL","reason":"CONTRACT_INVALID_JSON","detail":str(exc)}
    if c.get("schema")!=FUNCTION_SCHEMA: return {"status":"FAIL","reason":"FUNCTIONAL_CONTRACT_SCHEMA"}
    facts=[run_case(Path(target).resolve(),x,contract_dir=Path(contract_path).resolve().parent) for x in c.get("cases",[])]
    if not facts: st="INCONCLUSIVE"
    elif all(x["status"]=="PASS" for x in facts): st="PASS"
    elif any(x["status"]=="BLOCKED" for x in facts): st="BLOCKED"
    else: st="FAIL"
    return {"status":st,"contract_sha256":contract_sha256(c),"cases":facts}

def static_facts(target):
    target=Path(target); facts={"exists":target.exists(),"is_file":target.is_file(),"size":target.stat().st_size if target.exists() and target.is_file() else None}
    if target.is_file():
        facts["sha256"]=file_sha256(target); facts["zipfile"]=zipfile.is_zipfile(target)
        if facts["zipfile"]:
            try:
                with zipfile.ZipFile(target) as z: facts["zip_test"]=z.testzip() is None
            except Exception: facts["zip_test"]=False
    return facts

def _run_validator(name,root):
    exe=shutil.which(name)
    if not exe: return {"available":False,"status":"UNAVAILABLE"}
    root=Path(root).resolve()
    if name=="ruff": cmd=[exe,"check",str(root),"--output-format","json"]
    elif name=="bandit": cmd=[exe]+(["-r",str(root)] if root.is_dir() else [str(root)])+["-f","json","-q"]
    elif name=="mypy": cmd=[exe,str(root),"--no-error-summary"]
    elif name=="pytest":
        has_tests=(root.is_file() and root.name.startswith("test")) or (root.is_dir() and any(root.rglob("test*.py")))
        if not has_tests: return {"available":True,"status":"INCONCLUSIVE","reason":"NO_TEST_FILES"}
        cmd=[exe,"-q",str(root)]
    else:
        has_tests=root.is_dir() and any(root.rglob("test*.py"))
        if not has_tests: return {"available":True,"status":"INCONCLUSIVE","reason":"NO_TEST_FILES"}
        with tempfile.TemporaryDirectory(prefix="coverage-") as td:
            env=os.environ.copy(); env["COVERAGE_FILE"]=str(Path(td)/".coverage")
            run=subprocess.run([exe,"run","-m","pytest","-q",str(root)],text=True,capture_output=True,env=env,timeout=180)
            report=subprocess.run([exe,"json","-o",str(Path(td)/"coverage.json")],text=True,capture_output=True,env=env,timeout=60)
            pct=None; p=Path(td)/"coverage.json"
            if p.is_file():
                try: pct=json.loads(p.read_text())["totals"]["percent_covered"]
                except Exception: pass
            return {"available":True,"status":"PASS" if run.returncode==0 and report.returncode==0 else "FAIL","returncode":run.returncode,"coverage_percent":pct,"stdout":run.stdout[-2000:],"stderr":run.stderr[-1000:]}
    try: cp=subprocess.run(cmd,text=True,capture_output=True,timeout=180)
    except subprocess.TimeoutExpired: return {"available":True,"status":"BLOCKED","reason":"VALIDATOR_TIMEOUT","command":cmd}
    return {"available":True,"status":"PASS" if cp.returncode==0 else "FAIL","returncode":cp.returncode,"command":cmd,"stdout":cp.stdout[-3000:],"stderr":cp.stderr[-1500:]}

def validator_facts(root=None):
    available={name:bool(shutil.which(name)) for name in VALIDATORS}
    if root is None: return {"available":available,"results":{},"policy":"discover installed validators; do not auto-install"}
    return {"available":available,"results":{name:_run_validator(name,root) for name in VALIDATORS},"policy":"discover installed validators; do not auto-install"}

def _flatten_statuses(result):
    out={}
    for k,v in (result.get("gates") or {}).items(): out[f"gate:{k}"]=str(v)
    for k,v in ((result.get("facts") or {}).get("validators") or {}).get("results",{}).items(): out[f"validator:{k}"]=str(v.get("status"))
    fn=((result.get("facts") or {}).get("functionality") or {}).get("status")
    if fn: out["functionality"]=str(fn)
    acc=(result.get("feature_acceptance") or {}).get("facts_status")
    if acc: out["acceptance"]=str(acc)
    return out

def regression_facts(previous,current):
    if not previous: return {"status":"INCONCLUSIVE","reason":"NO_PREVIOUS_RESULT","newly_failing":[],"resolved":[],"changed":[]}
    p,c=_flatten_statuses(previous),_flatten_statuses(current); newly=[]; resolved=[]; changed=[]
    for key in sorted(set(p)|set(c)):
        a,b=p.get(key),c.get(key)
        if a==b: continue
        changed.append({"key":key,"previous":a,"current":b})
        if b in BAD_STATES and a not in BAD_STATES: newly.append(key)
        if a in BAD_STATES and b not in BAD_STATES: resolved.append(key)
    return {"status":"FAIL" if newly else "PASS","newly_failing":newly,"resolved":resolved,"changed":changed}

def verify(target,functional_contract=None,acceptance_contract=None,external_pin=None,validator_root=None,previous_result=None):
    target=Path(target).resolve(); static=static_facts(target)
    if not target.exists(): return {"schema":SCHEMA,"runner_version":VERSION,"status":"FAIL","verdict":"FAIL","reason":"TARGET_MISSING"}
    if is_native_or_opaque(target): return {"schema":SCHEMA,"runner_version":VERSION,"status":"BLOCKED","verdict":"BLOCKED","reason":"BLOCKED_NEEDS_SANDBOX","target":str(target),"facts":{"static":static}}
    fn=functionality(target,functional_contract); validators=validator_facts(Path(validator_root).resolve() if validator_root else None); validator_states=[v.get("status") for v in validators.get("results",{}).values()]
    gates={"functionality":fn["status"],"safety":"INCONCLUSIVE","performance":"INCONCLUSIVE","compatibility":"PASS" if target.suffix.lower() in (".py",".pyz",".zip") else "INCONCLUSIVE"}
    acc=acceptance(target,acceptance_contract,external_pin) if acceptance_contract else None
    if fn["status"] in ("FAIL","BLOCKED") or any(x in ("FAIL","BLOCKED") for x in validator_states) or (acc and acc["facts_status"] in ("FAIL","BLOCKED")): verdict="FAIL"
    elif fn["status"]=="PASS" and (not acc or acc["facts_status"]=="PASS"): verdict="PASS_WITH_INCONCLUSIVE_GATES" if "INCONCLUSIVE" in gates.values() or any(x=="INCONCLUSIVE" for x in validator_states) else "PASS"
    else: verdict="INCONCLUSIVE"
    out={"schema":SCHEMA,"runner_version":VERSION,"ai_contract_version":AI_CONTRACT_VERSION,"status":"PASS" if verdict.startswith("PASS") else verdict,"verdict":verdict,"target":str(target),"target_sha256":file_sha256(target) if target.is_file() else None,"facts":{"static":static,"validators":validators,"functionality":fn},"gates":gates,"feature_acceptance":acc}
    reg=regression_facts(previous_result,out); out["regression"]=reg
    if reg.get("newly_failing"): out["status"]=out["verdict"]="FAIL"; out["next_action"]="FIX_REGRESSION"
    else: out["next_action"]="AI_ASSESS_INTENT" if acc and acc.get("facts_status")=="PASS" else "REVIEW_FACTS" if verdict=="INCONCLUSIVE" else "USE_VERIFIED_FACTS" if verdict.startswith("PASS") else "FIX_OR_BLOCK"
    return out

def capabilities(): return {"schema":SCHEMA,"version":VERSION,"runner_version":VERSION,"ai_contract_version":AI_CONTRACT_VERSION,"status":"PASS","commands":["capabilities","self-test","verify","acceptance","contract-hash","request"],"validators":list(VALIDATORS),"regression_comparison":True,"feature_acceptance":{"schema":ACCEPTANCE_SCHEMA,"facts_only":True,"ai_intent_judgment_external":True,"mandatory_locked_sha256":True,"external_pin_required":True,"exact_target_sha256":True},"native_execution":"BLOCKED_NEEDS_SANDBOX"}

def self_test():
    checks=[]
    def add(name,ok): checks.append({"name":name,"pass":bool(ok)})
    with tempfile.TemporaryDirectory(prefix="vr-self-") as td:
        root=Path(td); tgt=root/"target.py"; tgt.write_text("import json,sys\nprint(json.dumps({'status':'PASS','echo':sys.argv[1:] if len(sys.argv)>1 else []}))\n",encoding="utf-8")
        fc={"schema":FUNCTION_SCHEMA,"cases":[{"id":"f1","args":["x"],"expect":{"returncode_in":[0],"stdout_json_subset":{"status":"PASS","echo":["x"]}}}]}; fcp=root/"functional.json"; fcp.write_text(json.dumps(fc))
        add("functional-contract-pass",verify(tgt,fcp)["facts"]["functionality"]["status"]=="PASS"); add("no-contract-inconclusive",verify(tgt)["facts"]["functionality"]["status"]=="INCONCLUSIVE")
        ac={"schema":ACCEPTANCE_SCHEMA,"contract_id":"A","target_id":"T","purpose":"echo x","requirements":[{"id":"R1","type":"MUST_WORK","statement":"echo","evidence":["S1"]}],"scenarios":[{"id":"S1","args":["x"],"expect":{"stdout_json_subset":{"status":"PASS","echo":["x"]}}}]}; ac["locked_sha256"]=contract_sha256(ac); acp=root/"accept.json"; acp.write_text(json.dumps(ac))
        pin={"schema":PIN_SCHEMA,"contract":acp.name,"contract_sha256":ac["locked_sha256"],"preimplementation_commit":"test"}; pp=root/"pin.json"; pp.write_text(json.dumps(pin)); ar=acceptance(tgt,acp,pp); add("acceptance-pass-with-pin",ar["facts_status"]=="PASS" and ar["target_sha256"]==file_sha256(tgt))
        nolock=json.loads(json.dumps(ac)); nolock.pop("locked_sha256"); np=root/"nolock.json"; np.write_text(json.dumps(nolock)); add("missing-lock-fails",acceptance(tgt,np,pp).get("facts_status")=="FAIL")
        bad=json.loads(json.dumps(ac)); bad["purpose"]="changed"; bp=root/"bad.json"; bp.write_text(json.dumps(bad)); add("locked-contract-drift",acceptance(tgt,bp,pp).get("reason")=="ACCEPTANCE_CONTRACT_CHANGED")
        pinbad=dict(pin); pinbad["contract_sha256"]="0"*64; pb=root/"pinbad.json"; pb.write_text(json.dumps(pinbad)); add("external-pin-mismatch",acceptance(tgt,acp,pb).get("reason")=="EXTERNAL_PIN_MISMATCH")
        ev=root/"evidence.json"; ev.write_text(json.dumps({"security":{"network":"blocked"}})); ac2={"schema":ACCEPTANCE_SCHEMA,"contract_id":"B","target_id":"T","purpose":"evidence","requirements":[{"id":"R","statement":"network blocked","evidence":["E"]}],"scenarios":[],"evidence_files":[{"id":"E","path":"evidence.json","json_subset":{"security":{"network":"blocked"}}}]}; ac2["locked_sha256"]=contract_sha256(ac2); ac2p=root/"evc.json"; ac2p.write_text(json.dumps(ac2)); pp2=root/"pin2.json"; pp2.write_text(json.dumps({"schema":PIN_SCHEMA,"contract":ac2p.name,"contract_sha256":ac2["locked_sha256"]})); add("evidence-file-pass",acceptance(tgt,ac2p,pp2)["facts_status"]=="PASS")
        empty={"schema":ACCEPTANCE_SCHEMA,"contract_id":"C","target_id":"T","purpose":"empty","requirements":[],"scenarios":[]}; empty["locked_sha256"]=contract_sha256(empty); ep=root/"empty.json"; ep.write_text(json.dumps(empty)); epp=root/"emptypin.json"; epp.write_text(json.dumps({"schema":PIN_SCHEMA,"contract":ep.name,"contract_sha256":empty["locked_sha256"]})); add("empty-inconclusive",acceptance(tgt,ep,epp)["facts_status"]=="INCONCLUSIVE")
        native=root/"native.bin"; native.write_bytes(b"\x7fELFfixture"); native.chmod(0o755); add("native-blocked",acceptance(native,acp,pp).get("reason")=="BLOCKED_NEEDS_SANDBOX")
        prev={"gates":{"functionality":"PASS"},"facts":{"validators":{"results":{"pytest":{"status":"PASS"}}},"functionality":{"status":"PASS"}}; cur={"gates":{"functionality":"PASS"},"facts":{"validators":{"results":{"pytest":{"status":"FAIL"}}},"functionality":{"status":"PASS"}}; add("regression-new-failure",regression_facts(prev,cur)["newly_failing"]==["validator:pytest"])
        add("validator-discovery",set(validator_facts(None)["available"])==set(VALIDATORS)); add("capabilities-contract",capabilities()["feature_acceptance"]["external_pin_required"] is True)
    n=sum(x["pass"] for x in checks); return {"schema":SCHEMA,"version":VERSION,"runner_version":VERSION,"ai_contract_version":AI_CONTRACT_VERSION,"status":"PASS" if n==len(checks) else "FAIL","passed":n,"total":len(checks),"checks":checks}

def request(payload):
    op=payload.get("operation") or payload.get("command")
    if op=="capabilities": return capabilities()
    if op=="self-test": return self_test()
    if op=="contract-hash": return {"schema":SCHEMA,"status":"PASS","contract_sha256":contract_sha256(load_json(payload["contract"]))}
    if op=="acceptance": return acceptance(Path(payload["target"]),Path(payload["contract"]),Path(payload["external_pin"]) if payload.get("external_pin") else None)
    if op=="verify": return verify(Path(payload["target"]),Path(payload["functional_contract"]) if payload.get("functional_contract") else None,Path(payload["acceptance_contract"]) if payload.get("acceptance_contract") else None,Path(payload["external_pin"]) if payload.get("external_pin") else None,Path(payload["validator_root"]) if payload.get("validator_root") else None,load_json(payload["previous_result"]) if payload.get("previous_result") else None)
    return {"schema":SCHEMA,"status":"FAIL","reason":"UNKNOWN_OPERATION"}

def main():
    p=argparse.ArgumentParser(description="AI-first deterministic fact confirmation and feature acceptance evidence runner"); sp=p.add_subparsers(dest="command"); sp.add_parser("capabilities"); sp.add_parser("self-test"); q=sp.add_parser("contract-hash"); q.add_argument("contract"); q=sp.add_parser("acceptance"); q.add_argument("target"); q.add_argument("--contract",required=True); q.add_argument("--external-pin",required=True); q=sp.add_parser("verify"); q.add_argument("target"); q.add_argument("--functional-contract","--contract",dest="functional_contract"); q.add_argument("--acceptance-contract"); q.add_argument("--external-pin"); q.add_argument("--validator-root"); q.add_argument("--previous-result"); q=sp.add_parser("request"); q.add_argument("source",nargs="?",default="-"); q.add_argument("--json-file")
    a=p.parse_args(); cmd=a.command or "capabilities"
    if cmd=="capabilities": out=capabilities()
    elif cmd=="self-test": out=self_test()
    elif cmd=="contract-hash": out={"schema":SCHEMA,"status":"PASS","contract_sha256":contract_sha256(load_json(a.contract))}
    elif cmd=="acceptance": out=acceptance(Path(a.target),Path(a.contract),Path(a.external_pin))
    elif cmd=="verify": out=verify(Path(a.target),Path(a.functional_contract) if a.functional_contract else None,Path(a.acceptance_contract) if a.acceptance_contract else None,Path(a.external_pin) if a.external_pin else None,Path(a.validator_root) if a.validator_root else None,load_json(a.previous_result) if a.previous_result else None)
    else:
        payload=load_json(a.json_file) if a.json_file else json.load(sys.stdin) if a.source=="-" else load_json(a.source); out=request(payload)
    print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out.get("status") in ("PASS","INCONCLUSIVE","PASS_WITH_INCONCLUSIVE_GATES") else 1
if __name__=="__main__": raise SystemExit(main())
