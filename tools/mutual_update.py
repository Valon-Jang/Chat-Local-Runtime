#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from pathlib import Path

VERSION="0.1.1"
SCHEMA="offload-mutual-update/1"
GRAPH_SCHEMA="offload-mutual-update-graph/1"
REPORT_SCHEMA="offload-mutual-update-report/1"
FACT_STATES={"PASS","FAIL","BLOCKED","INCONCLUSIVE"}
EXECUTABLE_PREFIXES=("src/","tools/")
EXECUTABLE_SUFFIXES=(".py",".pyz",".exe",".bin",".sh",".ps1")

def loadj(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def is_executable_change(path):
    p=path.replace("\\","/"); return (p.startswith(EXECUTABLE_PREFIXES) and p.endswith(EXECUTABLE_SUFFIXES)) or p.startswith(".github/workflows/")
def validate_graph(g):
    errs=[]
    if g.get("schema")!=GRAPH_SCHEMA: errs.append("schema")
    tools=g.get("tools")
    if not isinstance(tools,dict) or not tools: return errs+["tools"]
    roles=set()
    for tid,s in tools.items():
        if not isinstance(s,dict): errs.append(f"tool:{tid}"); continue
        if not s.get("source_prefixes"): errs.append(f"source_prefixes:{tid}")
        if not s.get("roles"): errs.append(f"roles:{tid}")
        if not s.get("artifact"): errs.append(f"artifact:{tid}")
        roles.update(s.get("roles",[]))
    missing=sorted(set(g.get("required_peer_roles",[]))-roles)
    if missing: errs.append("missing_roles:"+",".join(missing))
    return errs
def detect_changed(g,changed_paths):
    tools=g.get("tools",{}); changed=set(); unmatched=[]
    for raw in changed_paths:
        p=raw.replace("\\","/"); matched=False
        for tid,s in tools.items():
            if any(p.startswith(x.rstrip("/")+"/") or p==x.rstrip("/") for x in s.get("source_prefixes",[])): changed.add(tid); matched=True
        if is_executable_change(p) and not matched: unmatched.append(p)
    return {"changed_tools":sorted(changed),"unregistered_executable_changes":sorted(unmatched)}
def _change_contract_status(spec):
    missing=[]
    for key in ("feature_contract","external_pin"):
        if not spec.get(key): missing.append(key)
    baseline_required=bool(spec.get("previously_active",True))
    if baseline_required and not spec.get("baseline_contract"): missing.append("baseline_contract")
    return baseline_required,missing
def plan(g,changed_paths):
    errs=validate_graph(g)
    if errs: return {"schema":SCHEMA,"version":VERSION,"status":"FAIL","reason":"GRAPH_INVALID","errors":errs}
    d=detect_changed(g,changed_paths)
    if d["unregistered_executable_changes"]: return {"schema":SCHEMA,"version":VERSION,"status":"BLOCKED","reason":"UNREGISTERED_EXECUTABLE_CHANGE",**d}
    tools=g["tools"]; required_roles=g.get("required_peer_roles",[]); plans=[]; missing_contracts=[]
    products=[k for k,v in tools.items() if v.get("product",True)]
    for tid in d["changed_tools"]:
        spec=tools[tid]; baseline_required,missing=_change_contract_status(spec)
        if missing: missing_contracts.append({"tool_id":tid,"missing":missing})
        peers={}
        for peer_id,peer in tools.items():
            if peer_id==tid or not peer.get("product",True): continue
            roles=[r for r in peer.get("roles",[]) if r in required_roles]
            if roles: peers[peer_id]=roles
        reciprocal=[peer_id for peer_id in products if peer_id!=tid]
        plans.append({"tool_id":tid,"artifact":spec["artifact"],"peer_checks":peers,"reciprocal_targets":reciprocal,"baseline_contract_required":baseline_required,"baseline_contract":spec.get("baseline_contract"),"feature_acceptance_required":True,"feature_contract":spec.get("feature_contract"),"external_pin_required":True,"external_pin":spec.get("external_pin"),"exact_artifact_binding_required":True})
    if missing_contracts: return {"schema":SCHEMA,"version":VERSION,"status":"BLOCKED","reason":"CHANGE_CONTRACTS_MISSING","changed":d,"missing_contracts":missing_contracts,"plans":plans,"next_action":"CREATE_AND_PIN_CHANGE_CONTRACTS"}
    return {"schema":SCHEMA,"version":VERSION,"status":"PASS","changed":d,"plans":plans,"next_action":"RUN_PEER_GRAPH" if plans else "NO_EXECUTABLE_TOOL_CHANGE"}
def _status(x): return x if isinstance(x,str) else x.get("status") if isinstance(x,dict) else None
def evaluate(report):
    if report.get("schema")!=REPORT_SCHEMA: return {"schema":SCHEMA,"version":VERSION,"status":"FAIL","reason":"REPORT_SCHEMA"}
    mandatory=[]; details=[]
    for item in report.get("tools",[]):
        tid=item.get("tool_id","unknown"); checks={"baseline_preservation":_status(item.get("baseline_preservation")),"feature_acceptance":_status(item.get("feature_acceptance")),"artifact_binding":_status(item.get("artifact_binding")),"lock_pin":_status(item.get("lock_pin")),"source_mutation":"FAIL" if item.get("source_mutation") else "PASS"}
        if item.get("baseline_not_applicable"): checks.pop("baseline_preservation",None)
        if item.get("native_or_opaque"): checks["sandbox"]=_status(item.get("sandbox"))
        for k,v in item.get("peer_checks",{}).items(): checks[f"peer:{k}"]=_status(v)
        for k,v in item.get("reciprocal_checks",{}).items(): checks[f"reciprocal:{k}"]=_status(v)
        for k,v in checks.items(): mandatory.append(v); details.append({"tool_id":tid,"check":k,"status":v})
    invalid=[x for x in mandatory if x not in FACT_STATES]
    if invalid: st="FAIL"; reason="INVALID_STATUS"
    elif any(x in ("FAIL","BLOCKED") for x in mandatory): st="BLOCKED"; reason="MANDATORY_GATE_FAILED"
    elif any(x=="INCONCLUSIVE" for x in mandatory): st="INCONCLUSIVE"; reason="MANDATORY_GATE_INCONCLUSIVE"
    elif not mandatory: st="INCONCLUSIVE"; reason="NO_TOOL_EVIDENCE"
    else: st="PASS"; reason=None
    return {"schema":SCHEMA,"version":VERSION,"status":st,"reason":reason,"checks":details,"next_action":"PROMOTE_ATOMICALLY" if st=="PASS" else "KEEP_PREVIOUS_ACTIVE"}
def promote(current_manifest,candidate_manifest,report_path,output):
    report=loadj(report_path); ev=evaluate(report)
    if ev["status"]!="PASS": return {"schema":SCHEMA,"version":VERSION,"status":ev["status"],"reason":"REPORT_NOT_PASS","evaluation":ev,"next_action":"KEEP_PREVIOUS_ACTIVE"}
    current=loadj(current_manifest); candidate=loadj(candidate_manifest)
    if not isinstance(candidate.get("tools"),dict) or not candidate["tools"]: return {"schema":SCHEMA,"version":VERSION,"status":"FAIL","reason":"CANDIDATE_MANIFEST_INVALID"}
    for tid,s in candidate["tools"].items():
        if not s.get("sha256"): return {"schema":SCHEMA,"version":VERSION,"status":"FAIL","reason":"CANDIDATE_SHA_MISSING","tool_id":tid}
    new={"schema":"offload-stack-manifest/1","promoted_from":current,"tools":candidate["tools"],"promotion_report_sha256":sha256_file(report_path)}; output=Path(output).resolve(); output.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=output.name+".",suffix=".tmp",dir=str(output.parent)); os.close(fd); t=Path(tmp)
    try: t.write_text(json.dumps(new,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(t,output)
    finally:
        if t.exists(): t.unlink()
    return {"schema":SCHEMA,"version":VERSION,"status":"PASS","output":str(output),"manifest_sha256":sha256_file(output),"next_action":"AI_REVIEW_AND_PUBLISH"}
def capabilities(): return {"schema":SCHEMA,"version":VERSION,"status":"PASS","facts_only":True,"ai_intent_judgment_external":True,"commands":["capabilities","self-test","plan","evaluate","promote"],"policy":{"peer_source_mutation":False,"atomic_metadata_promotion":True,"fail_closed":True,"generic_change_contract_enforcement":True,"statuses":["PASS","FAIL","BLOCKED","INCONCLUSIVE"]}}
def self_test():
    checks={}; graph={"schema":GRAPH_SCHEMA,"required_peer_roles":["hub","inspect","diff","verify","build","sandbox"],"tools":{"hub":{"artifact":"dist/hub.pyz","source_prefixes":["src/hub"],"roles":["hub"],"feature_contract":"h-feature.json","external_pin":"h-pin.json","baseline_contract":"h-base.json"},"runner":{"artifact":"dist/runner.pyz","source_prefixes":["src/runner"],"roles":["verify"],"feature_contract":"r-feature.json","external_pin":"r-pin.json","baseline_contract":"r-base.json"},"inspector":{"artifact":"dist/inspector.pyz","source_prefixes":["src/inspector"],"roles":["inspect"]},"diff":{"artifact":"dist/diff.pyz","source_prefixes":["src/diff"],"roles":["diff"]},"builder":{"artifact":"dist/builder.pyz","source_prefixes":["src/builder"],"roles":["build"]},"sandbox":{"artifact":"dist/sandbox.pyz","source_prefixes":["src/sandbox"],"roles":["sandbox"]},"controller":{"artifact":"tools/mutual.py","source_prefixes":["tools/mutual.py"],"roles":["controller"],"product":False,"previously_active":False,"feature_contract":"m-feature.json","external_pin":"m-pin.json"}}}; p=plan(graph,["src/runner/main.py"]); one=p["plans"][0]; checks["reciprocal_peer_graph"]=p["status"]=="PASS" and len(one["peer_checks"])==5 and len(one["reciprocal_targets"])==5; checks["baseline_preservation"]=one["baseline_contract_required"] is True and one["baseline_contract"]=="r-base.json"; checks["exact_artifact_binding"]=one["exact_artifact_binding_required"] is True; checks["mandatory_external_lock"]=one["external_pin_required"] is True; missing=plan(graph,["src/inspector/main.py"]); checks["generic_contract_enforcement"]=missing["status"]=="BLOCKED" and missing["reason"]=="CHANGE_CONTRACTS_MISSING"; fresh=plan(graph,["tools/mutual.py"]); checks["new-controller-no-baseline"]=fresh["status"]=="PASS" and fresh["plans"][0]["baseline_contract_required"] is False; report={"schema":REPORT_SCHEMA,"tools":[{"tool_id":"runner","baseline_preservation":{"status":"PASS"},"feature_acceptance":{"status":"PASS"},"artifact_binding":{"status":"PASS"},"lock_pin":{"status":"PASS"},"native_or_opaque":True,"sandbox":{"status":"PASS"},"source_mutation":False,"peer_checks":{k:{"status":"PASS"} for k in ("hub","inspector","diff","builder","sandbox")},"reciprocal_checks":{k:{"status":"PASS"} for k in ("hub","inspector","diff","builder","sandbox")}}]}; e=evaluate(report); checks["native_sandbox_gate"]=e["status"]=="PASS"; checks["no_source_mutation"]=e["status"]=="PASS"
    with tempfile.TemporaryDirectory(prefix="mu-self-") as td:
        r=Path(td); cur=r/"current.json"; cand=r/"candidate.json"; rep=r/"report.json"; out=r/"out.json"; cur.write_text(json.dumps({"tools":{"runner":{"sha256":"old"}}})); cand.write_text(json.dumps({"tools":{"runner":{"sha256":"new"}}})); rep.write_text(json.dumps(report)); pr=promote(cur,cand,rep,out); checks["atomic_promotion"]=pr["status"]=="PASS" and out.is_file(); bad=json.loads(json.dumps(report)); bad["tools"][0]["peer_checks"]["diff"]["status"]="FAIL"; rep.write_text(json.dumps(bad)); before=out.read_bytes(); pr2=promote(cur,cand,rep,out); checks["fail_closed"]=pr2["status"]=="BLOCKED" and out.read_bytes()==before
    p2=plan(graph,["tools/new_unregistered.py"]); checks["generic_change_detection"]=p2["status"]=="BLOCKED" and p2["reason"]=="UNREGISTERED_EXECUTABLE_CHANGE"; checks["status_semantics"]=set(capabilities()["policy"]["statuses"])==FACT_STATES; checks["facts_only"]=capabilities()["facts_only"] and capabilities()["ai_intent_judgment_external"]; status="PASS" if all(checks.values()) else "FAIL"; return {"schema":SCHEMA,"version":VERSION,"status":status,"passed":sum(checks.values()),"total":len(checks),"checks":checks}
def main():
    p=argparse.ArgumentParser(); sp=p.add_subparsers(dest="command"); sp.add_parser("capabilities"); sp.add_parser("self-test"); q=sp.add_parser("plan"); q.add_argument("--graph",required=True); q.add_argument("--changed",nargs="+",required=True); q=sp.add_parser("evaluate"); q.add_argument("report"); q=sp.add_parser("promote"); q.add_argument("--current",required=True); q.add_argument("--candidate",required=True); q.add_argument("--report",required=True); q.add_argument("--output",required=True); a=p.parse_args(); cmd=a.command or "capabilities"
    if cmd=="capabilities": out=capabilities()
    elif cmd=="self-test": out=self_test()
    elif cmd=="plan": out=plan(loadj(a.graph),a.changed)
    elif cmd=="evaluate": out=evaluate(loadj(a.report))
    else: out=promote(Path(a.current),Path(a.candidate),Path(a.report),Path(a.output))
    print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out.get("status")=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
