#!/usr/bin/env python3
"""Install/verify current Chat Local Runtime artifacts recovered from ChatGPT Library.

GitHub is the public reference/fallback layer. Exact active .pyz artifacts are expected
from a user-selected/extracted Library bundle via --artifact-dir.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, sys, tempfile, time, uuid
from pathlib import Path

VERSION='0.4.1-public'
CONTRACT='offload-ai/1'
KEEP=3
TOOLS={
 'workerhub.pyz': {'version':'0.1.1','sha256':'2ef1ad5a0e8270ca6e1cc8794058ae04d2f626de7b982331e0bf5596833905b5','contract':True},
 'verificationrunner.pyz': {'version':'0.2.0','sha256':'641da71d80593422ec0d93a8d98930ccc62af8602f2aff05f8dd037feb3bccc3','contract':True},
 'workspaceinspector.pyz': {'version':'0.1.3','sha256':'2317ac17d3fb6cfa6e8983ee1dcb91523e7a86b2639f7ce8c4f58f3bbb49a26d','contract':True},
 'smartdiff.pyz': {'version':'0.1.1','sha256':'1e52cd0761b9a02172d315a16bed651a954821f259ca6c3d9de6c64dd8be6475','contract':True},
}
MANAGED=list(TOOLS)+['registry.json']

def sha256(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def run_json(path:Path, command:str):
    cp=subprocess.run([sys.executable,str(path),command],capture_output=True,text=True,timeout=180)
    try: data=json.loads(cp.stdout)
    except Exception: data={'raw':cp.stdout[:2000]}
    return cp.returncode,data,cp.stderr[:1000]

def observed_version(*payloads):
    for p in payloads:
        if isinstance(p,dict):
            for k in ('version','runner_version','tool_version'):
                if isinstance(p.get(k),str): return p[k]
    return None

def inspect_tool(path:Path,spec:dict):
    got=sha256(path) if path.is_file() else None
    if got!=spec['sha256']:
        return {'ok':False,'hash_ok':False,'expected_sha256':spec['sha256'],'observed_sha256':got,'contract_status':'NOT_CHECKED'}
    try:
        rc,caps,_=run_json(path,'capabilities')
        if rc: return {'ok':False,'hash_ok':True,'contract_status':'CAPABILITIES_FAILED'}
        rc,st,err=run_json(path,'self-test')
        ver=observed_version(st,caps)
        declared=st.get('ai_contract_version') or caps.get('ai_contract_version')
        cs='MATCH' if declared==CONTRACT else ('MISSING' if declared is None else 'MISMATCH')
        ok=rc==0 and st.get('status')=='PASS' and ver==spec['version'] and cs=='MATCH'
        return {'ok':ok,'hash_ok':True,'version':ver,'version_ok':ver==spec['version'],'ai_contract_version':declared,'contract_status':cs,'self_test':st,'stderr':err}
    except Exception as e:
        return {'ok':False,'hash_ok':True,'contract_status':'ERROR','error':f'{type(e).__name__}: {e}'}

def verify(root):
    root=Path(root).resolve(); d=root/'programs'
    tools={n:inspect_tool(d/n,s) for n,s in TOOLS.items()}; ok=all(x['ok'] for x in tools.values())
    return {'schema':'chat-local-runtime/install-result-0.4','installer_version':VERSION,'artifact_source':'ChatGPT Library / explicit local artifact directory','status':'PASS' if ok else 'FAIL','root':str(root),'tools':tools,'next_action':'USE_TOOL_LAYER' if ok else 'REINSTALL_OR_REVIEW_FACTS'}

def source_verify(artifact_dir,deep=True):
    if not artifact_dir:
        return {'schema':'chat-local-runtime/source-verify-0.4','installer_version':VERSION,'status':'BLOCKED','reason':'ACTIVE_ARTIFACT_DIR_REQUIRED','next_action':'SELECT_LIBRARY_ARTIFACT_BUNDLE'}
    d=Path(artifact_dir).resolve(); tools={}
    for n,s in TOOLS.items():
        p=d/n; got=sha256(p) if p.is_file() else None
        tools[n]=inspect_tool(p,s) if deep and got==s['sha256'] else {'ok':got==s['sha256'],'expected_sha256':s['sha256'],'observed_sha256':got}
    ok=all(x['ok'] for x in tools.values())
    return {'schema':'chat-local-runtime/source-verify-0.4','installer_version':VERSION,'status':'PASS' if ok else 'FAIL','artifact_dir':str(d),'tools':tools,'next_action':'INSTALL' if ok else 'DO_NOT_INSTALL'}

def snapshot(d):
    return {n:{'exists':(d/n).is_file(),'sha256':sha256(d/n) if (d/n).is_file() else None} for n in MANAGED}

def snapshot_ok(d,snap):
    checks={}
    for n,e in snap.items():
        p=d/n; got=sha256(p) if p.is_file() else None
        checks[n]=(p.is_file() and got==e['sha256']) if e['exists'] else not p.exists()
    return {'status':'PASS' if all(checks.values()) else 'FAIL','files':checks}

def backup(d,runtime,token):
    snap=snapshot(d)
    if not any(x['exists'] for x in snap.values()): return None,snap
    b=runtime/f'install-backup-{int(time.time())}-{token}'; b.mkdir()
    for n,e in snap.items():
        if e['exists']: shutil.copy2(d/n,b/n)
    (b/'backup-manifest.json').write_text(json.dumps(snap,indent=2),encoding='utf-8')
    if snapshot_ok(b,snap)['status']!='PASS': raise RuntimeError('backup manifest verification failed')
    return b,snap

def restore(d,b,snap):
    for n,e in snap.items():
        p=d/n
        if e['exists']: shutil.copy2(b/n,p)
        elif p.exists(): p.unlink()
    return snapshot_ok(d,snap)

def prune(runtime,keep):
    xs=sorted((p for p in runtime.glob('install-backup-*') if p.is_dir()),key=lambda p:(p.stat().st_mtime_ns,p.name),reverse=True)
    for p in xs[max(0,keep):]: shutil.rmtree(p,ignore_errors=True)
    return len(xs[max(0,keep):])

def registry():
    return {'schema':'chat-local-runtime/registry-0.4','installer_version':VERSION,'ai_contract_version':CONTRACT,'artifact_source':'ChatGPT Library','tools':{n:{'version':s['version'],'sha256':s['sha256'],'contract_required':True} for n,s in TOOLS.items()}}

def install(root,artifact_dir,keep=KEEP):
    gate=source_verify(artifact_dir,deep=False)
    if gate['status']!='PASS': return {**gate,'phase':'SOURCE_HASH_GATE','next_action':'DO_NOT_INSTALL' if gate['status']=='FAIL' else gate['next_action']}
    root=Path(root).resolve(); src=Path(artifact_dir).resolve(); d=root/'programs'; rt=root/'runtime'
    d.mkdir(parents=True,exist_ok=True); rt.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex[:12]; stage=rt/f'install-stage-{token}'; sd=stage/'programs'; sd.mkdir(parents=True)
    b=None; snap=None
    try:
        for n in TOOLS: shutil.copy2(src/n,sd/n)
        (sd/'registry.json').write_text(json.dumps(registry(),indent=2),encoding='utf-8')
        stage_gate=source_verify(sd,deep=False)
        if stage_gate['status']!='PASS': return {'status':'FAIL','phase':'STAGING_HASH_GATE','next_action':'KEEP_EXISTING_INSTALL'}
        b,snap=backup(d,rt,token)
        for n in MANAGED: shutil.copy2(sd/n,d/n)
        final=verify(root); final['phase']='FINAL_SELF_TEST_GATE'
        if final['status']=='PASS': final['backups_pruned']=prune(rt,keep); return final
        if b: rb=restore(d,b,snap)
        else:
            for n in MANAGED:
                p=d/n
                if p.exists(): p.unlink()
            rb={'status':'PASS','files':{n:not (d/n).exists() for n in MANAGED}}
        action='ROLLED_BACK_TO_PREVIOUS_INSTALL' if b and rb['status']=='PASS' else ('NO_PREVIOUS_INSTALL_REMOVED' if not b else 'ROLLBACK_FAILED_REVIEW_REQUIRED')
        return {**final,'status':'FAIL','next_action':action,'rollback_verification':rb,'backups_pruned':prune(rt,keep)}
    finally:
        shutil.rmtree(stage,ignore_errors=True)

def self_test():
    global TOOLS,MANAGED
    old_tools,old_managed=TOOLS,MANAGED; out=[]
    def add(n,v): out.append({'name':n,'pass':bool(v)})
    good="import json,sys\nb={'status':'PASS','version':'9.9','ai_contract_version':'offload-ai/1'}\nprint(json.dumps(b)); raise SystemExit(0)\n"
    missing=good.replace(",'ai_contract_version':'offload-ai/1'",''); fail=good.replace("'status':'PASS'","'status':'FAIL'")
    try:
      with tempfile.TemporaryDirectory() as td:
        x=Path(td); src=x/'src'; src.mkdir(); req=src/'req.pyz'; req.write_text(good)
        TOOLS={'req.pyz':{'version':'9.9','sha256':sha256(req),'contract':True}}; MANAGED=['req.pyz','registry.json']
        a=install(x/'a',src,2); add('contract-enforced',a['status']=='PASS' and a['tools']['req.pyz']['contract_status']=='MATCH')
        req.write_text(missing); TOOLS['req.pyz']['sha256']=sha256(req); a=install(x/'b',src,2); add('missing-contract-fails',a['next_action']=='NO_PREVIOUS_INSTALL_REMOVED')
        req.write_text(good); TOOLS['req.pyz']['sha256']=sha256(req); (x/'c/programs').mkdir(parents=True); old=x/'c/programs/req.pyz'; old.write_bytes(b'old'); oh=sha256(old); req.write_bytes(b'broken'); a=install(x/'c',src,2); add('source-corruption-keeps-existing',a['next_action']=='DO_NOT_INSTALL' and sha256(old)==oh)
        req.write_text(fail); TOOLS['req.pyz']['sha256']=sha256(req); (x/'d/programs').mkdir(parents=True); old=x/'d/programs/req.pyz'; old.write_bytes(b'previous'); oh=sha256(old); a=install(x/'d',src,2); add('rollback-backup-manifest',a['next_action']=='ROLLED_BACK_TO_PREVIOUS_INSTALL' and a['rollback_verification']['status']=='PASS' and sha256(old)==oh)
        a=install(x/'e',src,2); add('first-install-failure-distinct',a['next_action']=='NO_PREVIOUS_INSTALL_REMOVED')
        rr=x/'p/runtime'; rr.mkdir(parents=True); [(rr/f'install-backup-{i}-x').mkdir() for i in range(5)]; prune(rr,2); add('backup-retention',len(list(rr.glob('install-backup-*')))==2)
        add('missing-artifact-dir-blocked',source_verify(None)['next_action']=='SELECT_LIBRARY_ARTIFACT_BUNDLE')
        req.write_text(good); TOOLS['req.pyz']['sha256']=sha256(req); add('machine-next-action','next_action' in install(x/'f',src,2))
    finally: TOOLS,MANAGED=old_tools,old_managed
    n=sum(x['pass'] for x in out); return {'schema':'chat-local-runtime/installer-self-test-0.4','installer_version':VERSION,'status':'PASS' if n==len(out) else 'FAIL','passed':n,'total':len(out),'checks':out}

def main():
    p=argparse.ArgumentParser(); p.add_argument('command',nargs='?',default='install',choices=['install','verify','source-verify','self-test']); p.add_argument('--root',default='/mnt/data/ai_program_lab'); p.add_argument('--artifact-dir'); p.add_argument('--keep-backups',type=int,default=KEEP); a=p.parse_args()
    r=install(a.root,a.artifact_dir,a.keep_backups) if a.command=='install' else verify(a.root) if a.command=='verify' else source_verify(a.artifact_dir,True) if a.command=='source-verify' else self_test()
    print(json.dumps(r,ensure_ascii=False,indent=2)); return 0 if r.get('status')=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
