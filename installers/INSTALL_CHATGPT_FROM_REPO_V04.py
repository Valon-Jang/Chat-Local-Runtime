#!/usr/bin/env python3
"""Install/verify the current Chat Local Runtime GitHub fallback layer safely."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time, uuid
from pathlib import Path

VERSION="0.4.0-public"; CONTRACT="offload-ai/1"; KEEP=3
TOOLS={
 "workerhub.pyz":dict(version="0.1.1",sha256="2ef1ad5a0e8270ca6e1cc8794058ae04d2f626de7b982331e0bf5596833905b5",path="dist/active/workerhub-0.1.1.pyz",contract=True),
 "verificationrunner.pyz":dict(version="0.2.0",sha256="641da71d80593422ec0d93a8d98930ccc62af8602f2aff05f8dd037feb3bccc3",path="dist/active/verificationrunner-0.2.0.pyz",contract=True),
 "workspaceinspector.pyz":dict(version="0.1.3",sha256="2317ac17d3fb6cfa6e8983ee1dcb91523e7a86b2639f7ce8c4f58f3bbb49a26d",path="dist/active/workspaceinspector-0.1.3.pyz",contract=True),
 "smartdiff.pyz":dict(version="0.1.1",sha256="1e52cd0761b9a02172d315a16bed651a954821f259ca6c3d9de6c64dd8be6475",path="dist/active/smartdiff-0.1.1.pyz",contract=True),
 "artifactbuilder.pyz":dict(version="0.1.1",sha256="1677f84252d0e275f0448426ac6702318ad30589c462493aea533e1ddfe63c3a",parts=[f"dist/artifactbuilder.pyz.part{i:02d}" for i in range(1,6)],contract=False),
}
def managed(): return list(TOOLS)+["registry.json"]

def digest(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def repo(): return Path(__file__).resolve().parent.parent
def runj(p,cmd):
 cp=subprocess.run([sys.executable,str(p),cmd],capture_output=True,text=True,timeout=180)
 try: data=json.loads(cp.stdout)
 except Exception: data={"raw":cp.stdout[:2000]}
 return cp.returncode,data,cp.stderr[:1000]
def observed_version(*xs):
 for x in xs:
  if isinstance(x,dict):
   for k in ("version","runner_version","tool_version"):
    if isinstance(x.get(k),str): return x[k]
def materialize(base,dst):
 dst.mkdir(parents=True,exist_ok=True)
 for name,s in TOOLS.items():
  out=dst/name
  if "path" in s: shutil.copy2(base/s["path"],out)
  else:
   with out.open("wb") as w:
    for rel in s["parts"]:
     with (base/rel).open("rb") as r: shutil.copyfileobj(r,w,1<<20)
def hashes(d):
 r={}
 for n,s in TOOLS.items():
  p=d/n; got=digest(p) if p.is_file() else None
  r[n]={"ok":got==s["sha256"],"expected":s["sha256"],"observed":got}
 return {"status":"PASS" if all(x["ok"] for x in r.values()) else "FAIL","tools":r}
def inspect(p,s):
 got=digest(p) if p.is_file() else None
 if got!=s["sha256"]: return {"ok":False,"hash_ok":False,"contract_status":"NOT_CHECKED"}
 caps={}; cr=None
 try:
  if s["contract"]:
   rc,caps,_=runj(p,"capabilities")
   if rc: return {"ok":False,"hash_ok":True,"contract_status":"CAPABILITIES_FAILED"}
  rc,st,err=runj(p,"self-test")
  ver=observed_version(st,caps); declared=st.get("ai_contract_version") or caps.get("ai_contract_version")
  cs="NOT_REQUIRED" if not s["contract"] else ("MATCH" if declared==CONTRACT else "MISSING" if declared is None else "MISMATCH")
  ok=rc==0 and st.get("status")=="PASS" and ver==s["version"] and (not s["contract"] or cs=="MATCH")
  return {"ok":ok,"hash_ok":True,"version":ver,"version_ok":ver==s["version"],"ai_contract_version":declared,"contract_required":s["contract"],"contract_status":cs,"self_test":st,"stderr":err}
 except Exception as e: return {"ok":False,"hash_ok":True,"contract_status":"ERROR","error":f"{type(e).__name__}: {e}"}
def verify(root):
 root=Path(root).resolve(); d=root/"programs"; t={n:inspect(d/n,s) for n,s in TOOLS.items()}; ok=all(x["ok"] for x in t.values())
 return {"schema":"chat-local-runtime/install-result-0.4","installer_version":VERSION,"status":"PASS" if ok else "FAIL","root":str(root),"tools":t,"next_action":"USE_TOOL_LAYER" if ok else "REINSTALL_OR_REVIEW_FACTS"}
def source_verify(deep=True,base=None):
 base=Path(base or repo()).resolve()
 with tempfile.TemporaryDirectory() as td:
  try:
   d=Path(td); materialize(base,d); r={"status":"PASS","tools":{n:inspect(d/n,s) for n,s in TOOLS.items()}} if deep else hashes(d)
   if deep and not all(x["ok"] for x in r["tools"].values()): r["status"]="FAIL"
  except Exception as e: r={"status":"FAIL","error":f"{type(e).__name__}: {e}","tools":{}}
 return {"schema":"chat-local-runtime/source-verify-0.4","installer_version":VERSION,**r}
def snapshot(d):
 return {n:{"exists":(d/n).is_file(),"sha256":digest(d/n) if (d/n).is_file() else None} for n in managed()}
def snapshot_ok(d,snap):
 checks={}
 for n,e in snap.items():
  p=d/n; got=digest(p) if p.is_file() else None; ok=(p.is_file() and got==e["sha256"]) if e["exists"] else not p.exists(); checks[n]=ok
 return {"status":"PASS" if all(checks.values()) else "FAIL","files":checks}
def backup(d,runtime,token):
 snap=snapshot(d)
 if not any(x["exists"] for x in snap.values()): return None,snap
 b=runtime/f"install-backup-{int(time.time())}-{token}"; b.mkdir()
 for n,e in snap.items():
  if e["exists"]: shutil.copy2(d/n,b/n)
 (b/"backup-manifest.json").write_text(json.dumps(snap,indent=2),encoding="utf-8")
 if snapshot_ok(b,snap)["status"]!="PASS": raise RuntimeError("backup manifest verification failed")
 return b,snap
def restore(d,b,snap):
 for n,e in snap.items():
  p=d/n
  if e["exists"]: shutil.copy2(b/n,p)
  elif p.exists(): p.unlink()
 return snapshot_ok(d,snap)
def prune(runtime,keep):
 xs=sorted((p for p in runtime.glob("install-backup-*") if p.is_dir()),key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True)
 for p in xs[max(0,keep):]: shutil.rmtree(p,ignore_errors=True)
 return len(xs[max(0,keep):])
def registry(): return {"schema":"chat-local-runtime/registry-0.4","installer_version":VERSION,"ai_contract_version":CONTRACT,"tools":{n:{"version":s["version"],"sha256":s["sha256"],"contract_required":s["contract"]} for n,s in TOOLS.items()}}
def install(root,keep=KEEP,base=None):
 base=Path(base or repo()).resolve(); gate=source_verify(False,base)
 if gate["status"]!="PASS": return {**gate,"phase":"SOURCE_HASH_GATE","next_action":"DO_NOT_INSTALL"}
 root=Path(root).resolve(); d=root/"programs"; rt=root/"runtime"; d.mkdir(parents=True,exist_ok=True); rt.mkdir(parents=True,exist_ok=True)
 token=uuid.uuid4().hex[:12]; stage=rt/f"install-stage-{token}"; sd=stage/"programs"; b=None; snap=None
 try:
  materialize(base,sd); (sd/"registry.json").write_text(json.dumps(registry(),indent=2),encoding="utf-8")
  if hashes(sd)["status"]!="PASS": return {"status":"FAIL","phase":"STAGING_HASH_GATE","next_action":"KEEP_EXISTING_INSTALL"}
  b,snap=backup(d,rt,token)
  for n in managed(): shutil.copy2(sd/n,d/n)
  final=verify(root); final["phase"]="FINAL_SELF_TEST_GATE"
  if final["status"]=="PASS": final["backups_pruned"]=prune(rt,keep); return final
  if b:
   rb=restore(d,b,snap)
  else:
   for n in managed():
    p=d/n
    if p.exists(): p.unlink()
   rb={"status":"PASS","files":{n:not (d/n).exists() for n in managed()}}
  action="ROLLED_BACK_TO_PREVIOUS_INSTALL" if b and rb["status"]=="PASS" else "NO_PREVIOUS_INSTALL_REMOVED" if not b else "ROLLBACK_FAILED_REVIEW_REQUIRED"
  return {**final,"status":"FAIL","next_action":action,"rollback_verification":rb,"backups_pruned":prune(rt,keep)}
 finally: shutil.rmtree(stage,ignore_errors=True)

def self_test():
 global TOOLS
 old=TOOLS; out=[]
 def add(n,v): out.append({"name":n,"pass":bool(v)})
 good="import json,sys\nc=sys.argv[1]; b={'status':'PASS','version':'9.9','ai_contract_version':'offload-ai/1'}\nprint(json.dumps(b)); raise SystemExit(0)\n"
 opt=good.replace(",'ai_contract_version':'offload-ai/1'","")
 fail=good.replace("'status':'PASS'","'status':'FAIL'")
 try:
  with tempfile.TemporaryDirectory() as td:
   x=Path(td); rp=x/"repo"; (rp/"dist/active").mkdir(parents=True); req=rp/"dist/active/req.pyz"; op=rp/"dist/opt.pyz"; op.write_text(opt)
   req.write_text(good); TOOLS={"req.pyz":dict(version="9.9",sha256=digest(req),path="dist/active/req.pyz",contract=True),"opt.pyz":dict(version="9.9",sha256=digest(op),path="dist/opt.pyz",contract=False)}
   a=install(x/"a",2,rp); add("required-contract-enforced",a["status"]=="PASS" and a["tools"]["req.pyz"]["contract_status"]=="MATCH"); add("optional-contract-explicit-not-required",a["tools"]["opt.pyz"]["contract_status"]=="NOT_REQUIRED")
   req.write_text(opt); TOOLS["req.pyz"]["sha256"]=digest(req); a=install(x/"b",2,rp); add("required-missing-contract-fails",a["next_action"]=="NO_PREVIOUS_INSTALL_REMOVED")
   req.write_text(good); TOOLS["req.pyz"]["sha256"]=digest(req); (x/"c/programs").mkdir(parents=True); oldf=x/"c/programs/req.pyz"; oldf.write_bytes(b"old"); oldhash=digest(oldf); req.write_bytes(b"broken"); a=install(x/"c",2,rp); add("source-corruption-keeps-existing",a["next_action"]=="DO_NOT_INSTALL" and digest(oldf)==oldhash)
   req.write_text(fail); TOOLS["req.pyz"]["sha256"]=digest(req); (x/"d/programs").mkdir(parents=True); oldf=x/"d/programs/req.pyz"; oldf.write_bytes(b"previous"); oldhash=digest(oldf); a=install(x/"d",2,rp); add("rollback-uses-backup-manifest",a["next_action"]=="ROLLED_BACK_TO_PREVIOUS_INSTALL" and a["rollback_verification"]["status"]=="PASS" and digest(oldf)==oldhash)
   a=install(x/"e",2,rp); add("first-install-failure-distinct",a["next_action"]=="NO_PREVIOUS_INSTALL_REMOVED")
   rr=x/"p/runtime"; rr.mkdir(parents=True); [(rr/f"install-backup-{i}-x").mkdir() for i in range(5)]; prune(rr,2); add("backup-retention",len(list(rr.glob('install-backup-*')))==2)
   add("machine-next-action",all("next_action" in z for z in (install(x/"f",2,rp),)))
 finally: TOOLS=old
 n=sum(x["pass"] for x in out); return {"schema":"chat-local-runtime/installer-self-test-0.4","installer_version":VERSION,"status":"PASS" if n==len(out) else "FAIL","passed":n,"total":len(out),"checks":out}

def main():
 p=argparse.ArgumentParser(); p.add_argument("command",nargs="?",default="install",choices=["install","verify","source-verify","self-test"]); p.add_argument("--root",default="/mnt/data/ai_program_lab"); p.add_argument("--keep-backups",type=int,default=KEEP); a=p.parse_args()
 r=install(a.root,a.keep_backups) if a.command=="install" else verify(a.root) if a.command=="verify" else source_verify(True) if a.command=="source-verify" else self_test(); print(json.dumps(r,ensure_ascii=False,indent=2)); return 0 if r.get("status")=="PASS" else 1
if __name__=="__main__": raise SystemExit(main())
