#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sys, tempfile, zipfile
from pathlib import Path

VERSION="0.1.3"
AI_CONTRACT_VERSION="offload-ai/1"
SCHEMA="artifact-builder/0.1.3"
ACCEPTANCE_SCHEMA="offload-feature-acceptance/1"
ASSESSMENT_SCHEMA="offload-feature-intent-assessment/1"
PIN_SCHEMA="offload-feature-pin/1"
FIXED_DT=(2026,1,1,0,0,0)
SECRET_NAMES={".env","id_rsa","id_ed25519","credentials.json","service-account.json"}

def sha256_file(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def canonical_contract(data):
    d=json.loads(json.dumps(data)); d.pop('locked_sha256',None); return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def loadj(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def excluded(p): return Path(p).name in SECRET_NAMES or Path(p).suffix.lower() in {'.pem','.key','.p12','.pfx'}
def collect(src,outdir=None):
    src=Path(src).resolve(); files=[]
    if src.is_file(): return [(src,src.name)]
    for p in sorted(src.rglob('*')):
        if not p.is_file() or p.is_symlink() or excluded(p): continue
        if outdir:
            try: p.resolve().relative_to(Path(outdir).resolve()); continue
            except ValueError: pass
        files.append((p,p.relative_to(src).as_posix()))
    return files
def deterministic_zip(src,dst,pyz=False):
    files=collect(src,Path(dst).parent)
    if not files: raise ValueError('no packageable files')
    with zipfile.ZipFile(dst,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p,arc in files:
            zi=zipfile.ZipInfo(arc,FIXED_DT); zi.compress_type=zipfile.ZIP_DEFLATED; zi.external_attr=(0o644&0xffff)<<16; z.writestr(zi,p.read_bytes())
    return files
def choose_mode(src):
    src=Path(src); return 'pyz' if src.is_dir() and (src/'__main__.py').is_file() else 'zip'
def inspect_source(src):
    src=Path(src); files=collect(src); return {"schema":SCHEMA,"version":VERSION,"status":"PASS","source":str(src.resolve()),"mode":choose_mode(src),"files":len(files),"excluded_secret_like":sum(1 for p in src.rglob('*') if p.is_file() and excluded(p)) if src.is_dir() else int(excluded(src))}
def normalize_verification(path):
    if not path: return None
    d=loadj(path); verdict=d.get('verdict') or d.get('status')
    if verdict in ('FAIL','BLOCK','BLOCKED'): state='FAIL'
    elif isinstance(verdict,str) and verdict.startswith('PASS'): state='PASS'
    else: state='INCONCLUSIVE'
    return {"state":state,"raw":d}
def validate_pin(pin_path,contract_path,contract_sha):
    if not pin_path: return {"status":"BLOCK","reason":"EXTERNAL_PIN_MISSING","next_action":"PIN_PREIMPLEMENTATION_CONTRACT"}
    try: p=loadj(pin_path)
    except Exception as exc: return {"status":"BLOCK","reason":"EXTERNAL_PIN_INVALID","detail":str(exc)}
    if p.get('schema')!=PIN_SCHEMA: return {"status":"BLOCK","reason":"EXTERNAL_PIN_SCHEMA"}
    if p.get('contract_sha256')!=contract_sha: return {"status":"BLOCK","reason":"EXTERNAL_PIN_MISMATCH","pin_contract_sha256":p.get('contract_sha256'),"contract_sha256":contract_sha}
    cref=p.get('contract')
    if cref and Path(cref).name!=Path(contract_path).name: return {"status":"BLOCK","reason":"EXTERNAL_PIN_CONTRACT_MISMATCH"}
    return {"status":"PASS","preimplementation_commit":p.get('preimplementation_commit')}
def acceptance_gate(contract_path,evidence_path,assessment_path,external_pin,required,expected_target_sha):
    if not required and not any((contract_path,evidence_path,assessment_path,external_pin)): return {"required":False,"status":"NOT_REQUIRED"}
    if not contract_path: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_CONTRACT_MISSING","next_action":"CREATE_FEATURE_ACCEPTANCE_CONTRACT"}
    contract=loadj(contract_path); csha=canonical_contract(contract); locked=contract.get('locked_sha256')
    if contract.get('schema')!=ACCEPTANCE_SCHEMA: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_CONTRACT_SCHEMA"}
    if not locked: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_LOCK_MISSING"}
    if locked!=csha: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_CONTRACT_CHANGED","contract_sha256":csha,"locked_sha256":locked}
    pin=validate_pin(external_pin,contract_path,csha)
    if pin['status']!='PASS': return {"required":required,**pin}
    if not evidence_path: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_EVIDENCE_MISSING","contract_sha256":csha,"next_action":"RUN_FEATURE_ACCEPTANCE"}
    ev=loadj(evidence_path)
    if ev.get('contract_sha256')!=csha: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_EVIDENCE_CONTRACT_MISMATCH","contract_sha256":csha,"evidence_contract_sha256":ev.get('contract_sha256')}
    if ev.get('facts_status')!='PASS': return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_FACTS_NOT_PASS","facts_status":ev.get('facts_status')}
    observed_target=ev.get('target_sha256')
    if not observed_target or observed_target!=expected_target_sha: return {"required":required,"status":"BLOCK","reason":"ACCEPTANCE_TARGET_SHA_MISMATCH","expected_target_sha256":expected_target_sha,"evidence_target_sha256":observed_target}
    evidence_sha=sha256_file(Path(evidence_path))
    if not assessment_path: return {"required":required,"status":"BLOCK","reason":"INTENT_ASSESSMENT_MISSING","next_action":"AI_ASSESS_INTENT","contract_sha256":csha}
    a=loadj(assessment_path)
    if a.get('schema')!=ASSESSMENT_SCHEMA: return {"required":required,"status":"BLOCK","reason":"INTENT_ASSESSMENT_SCHEMA"}
    if a.get('contract_sha256')!=csha: return {"required":required,"status":"BLOCK","reason":"INTENT_ASSESSMENT_CONTRACT_MISMATCH"}
    if a.get('target_sha256')!=expected_target_sha: return {"required":required,"status":"BLOCK","reason":"INTENT_TARGET_SHA_MISMATCH"}
    if a.get('acceptance_evidence_sha256')!=evidence_sha: return {"required":required,"status":"BLOCK","reason":"INTENT_EVIDENCE_SHA_MISMATCH","expected":evidence_sha,"observed":a.get('acceptance_evidence_sha256')}
    if a.get('status')!='SATISFIED': return {"required":required,"status":"BLOCK","reason":"INTENT_NOT_SATISFIED","intent_status":a.get('status')}
    pass_ids={x.get('id') for x in ev.get('facts',[]) if x.get('status')=='PASS'}|{x.get('id') for x in ev.get('requirements',[]) if x.get('status')=='PASS'}; refs=a.get('evidence_ids',[])
    if not refs or not set(refs).issubset(pass_ids): return {"required":required,"status":"BLOCK","reason":"INTENT_EVIDENCE_INVALID","unknown":sorted(set(refs)-pass_ids)}
    return {"required":required,"status":"PASS","contract_sha256":csha,"assessment":"SATISFIED","target_sha256":expected_target_sha,"acceptance_evidence_sha256":evidence_sha,"evidence_ids":refs,"external_pin":pin}
def build(src,outdir,release_version,verification_json=None,acceptance_contract=None,acceptance_evidence=None,intent_assessment=None,external_pin=None,require_feature_acceptance=False,mode='auto'):
    src=Path(src).resolve(); outdir=Path(outdir).resolve(); outdir.mkdir(parents=True,exist_ok=True); before={str(p):sha256_file(p) for p,_ in collect(src,outdir)}; use=choose_mode(src) if mode=='auto' else mode; name=src.name or 'artifact'; ext='.pyz' if use=='pyz' else '.zip'; artifact=outdir/f'{name}-{release_version}{ext}'; files=deterministic_zip(src,artifact,pyz=use=='pyz'); artifact_sha=sha256_file(artifact); manifest={arc:sha256_file(p) for p,arc in files}; manifest_path=outdir/f'{artifact.name}.manifest.json'; manifest_path.write_text(json.dumps({"schema":"artifact-manifest/1","artifact":artifact.name,"artifact_sha256":artifact_sha,"files":manifest},sort_keys=True,indent=2),encoding='utf-8'); after={str(p):sha256_file(p) for p,_ in collect(src,outdir)}; mutation=before!=after; verify=normalize_verification(verification_json); ag=acceptance_gate(acceptance_contract,acceptance_evidence,intent_assessment,external_pin,require_feature_acceptance,artifact_sha); warnings=[]; blockers=[]
    if mutation: blockers.append('SOURCE_MUTATION')
    if verify and verify['state']=='FAIL': blockers.append('VERIFICATION_FAIL')
    if verify and verify['state']=='INCONCLUSIVE': warnings.append('VERIFICATION_INCONCLUSIVE')
    if ag['status']=='BLOCK': blockers.append(ag['reason'])
    decision='BLOCK' if blockers else 'RELEASE_WITH_WARNINGS' if warnings else 'RELEASE'
    return {"schema":SCHEMA,"version":VERSION,"status":decision,"decision":decision,"source":str(src),"artifact":str(artifact),"artifact_sha256":artifact_sha,"manifest":str(manifest_path),"source_mutation":mutation,"verification":verify,"feature_acceptance":ag,"warnings":warnings,"blockers":blockers,"next_action":"USE_RELEASE" if decision=='RELEASE' else "REVIEW_WARNINGS" if decision=='RELEASE_WITH_WARNINGS' else ag.get('next_action','FIX_AND_RETEST')}
def capabilities(): return {"schema":SCHEMA,"version":VERSION,"tool_version":VERSION,"ai_contract_version":AI_CONTRACT_VERSION,"status":"PASS","commands":["capabilities","self-test","inspect","build","request"],"feature_acceptance_gate":True,"exact_artifact_binding":True,"mandatory_locked_sha256":True,"external_pin_required":True,"intent_evidence_digest_binding":True}
def request(payload):
    op=payload.get('operation') or payload.get('command')
    if op=='capabilities': return capabilities()
    if op=='self-test': return self_test()
    if op=='inspect': return inspect_source(Path(payload['source']))
    if op=='build': return build(Path(payload['source']),Path(payload['output']),str(payload.get('release_version','0')),payload.get('verification_json'),payload.get('acceptance_contract'),payload.get('acceptance_evidence'),payload.get('intent_assessment'),payload.get('external_pin'),bool(payload.get('require_feature_acceptance')),payload.get('mode','auto'))
    return {"schema":SCHEMA,"status":"FAIL","reason":"UNKNOWN_OPERATION"}
def self_test():
    checks=[]
    def add(n,v): checks.append({"name":n,"pass":bool(v)})
    with tempfile.TemporaryDirectory(prefix='ab-self-') as td:
        r=Path(td); src=r/'src'; src.mkdir(); (src/'__main__.py').write_text("print('ok')\n",encoding='utf-8'); a=build(src,r/'out','1'); add('basic-release',a['decision']=='RELEASE' and Path(a['artifact']).is_file()); a2=build(src,r/'out2','1',require_feature_acceptance=True); add('required-acceptance-blocks-missing',a2['decision']=='BLOCK' and a2['feature_acceptance']['reason']=='ACCEPTANCE_CONTRACT_MISSING'); c={"schema":ACCEPTANCE_SCHEMA,"contract_id":"C","target_id":"T","purpose":"p","requirements":[{"id":"R","statement":"works","evidence":["S"]}],"scenarios":[{"id":"S"}]}; c['locked_sha256']=canonical_contract(c); cp=r/'c.json'; cp.write_text(json.dumps(c)); pin={"schema":PIN_SCHEMA,"contract":cp.name,"contract_sha256":c['locked_sha256'],"preimplementation_commit":"x"}; pp=r/'pin.json'; pp.write_text(json.dumps(pin)); probe=build(src,r/'probe','1'); target_sha=probe['artifact_sha256']; ev={"contract_sha256":c['locked_sha256'],"facts_status":"PASS","target_sha256":target_sha,"facts":[{"id":"S","status":"PASS"}],"requirements":[{"id":"R","status":"PASS"}]}; ep=r/'e.json'; ep.write_text(json.dumps(ev)); ass={"schema":ASSESSMENT_SCHEMA,"contract_sha256":c['locked_sha256'],"target_sha256":target_sha,"acceptance_evidence_sha256":sha256_file(ep),"status":"SATISFIED","evidence_ids":["R"]}; ap=r/'a.json'; ap.write_text(json.dumps(ass)); a3=build(src,r/'out3','1',acceptance_contract=cp,acceptance_evidence=ep,intent_assessment=ap,external_pin=pp,require_feature_acceptance=True); add('acceptance-allows-release',a3['decision']=='RELEASE' and a3['artifact_sha256']==target_sha); no_lock=json.loads(json.dumps(c)); no_lock.pop('locked_sha256'); nlp=r/'nolock.json'; nlp.write_text(json.dumps(no_lock)); a4=build(src,r/'out4','1',acceptance_contract=nlp,acceptance_evidence=ep,intent_assessment=ap,external_pin=pp,require_feature_acceptance=True); add('missing-lock-blocks',a4['decision']=='BLOCK' and a4['feature_acceptance']['reason']=='ACCEPTANCE_LOCK_MISSING'); a5=build(src,r/'out5','1',acceptance_contract=cp,acceptance_evidence=ep,intent_assessment=ap,require_feature_acceptance=True); add('missing-pin-blocks',a5['decision']=='BLOCK' and a5['feature_acceptance']['reason']=='EXTERNAL_PIN_MISSING'); bad=json.loads(json.dumps(c)); bad['purpose']='changed'; bp=r/'bad.json'; bp.write_text(json.dumps(bad)); a6=build(src,r/'out6','1',acceptance_contract=bp,acceptance_evidence=ep,intent_assessment=ap,external_pin=pp,require_feature_acceptance=True); add('contract-drift-blocks',a6['decision']=='BLOCK' and a6['feature_acceptance']['reason']=='ACCEPTANCE_CONTRACT_CHANGED'); evbad=dict(ev); evbad['target_sha256']='0'*64; ebp=r/'ebad.json'; ebp.write_text(json.dumps(evbad)); assbad=dict(ass); assbad['acceptance_evidence_sha256']=sha256_file(ebp); abp=r/'abad.json'; abp.write_text(json.dumps(assbad)); a7=build(src,r/'out7','1',acceptance_contract=cp,acceptance_evidence=ebp,intent_assessment=abp,external_pin=pp,require_feature_acceptance=True); add('target-sha-mismatch-blocks',a7['decision']=='BLOCK' and a7['feature_acceptance']['reason']=='ACCEPTANCE_TARGET_SHA_MISMATCH'); ass2=dict(ass); ass2['status']='NOT_SATISFIED'; ap2=r/'a2.json'; ap2.write_text(json.dumps(ass2)); a8=build(src,r/'out8','1',acceptance_contract=cp,acceptance_evidence=ep,intent_assessment=ap2,external_pin=pp,require_feature_acceptance=True); add('intent-not-satisfied-blocks',a8['decision']=='BLOCK'); ass3=dict(ass); ass3['acceptance_evidence_sha256']='0'*64; ap3=r/'a3.json'; ap3.write_text(json.dumps(ass3)); a9=build(src,r/'out9','1',acceptance_contract=cp,acceptance_evidence=ep,intent_assessment=ap3,external_pin=pp,require_feature_acceptance=True); add('evidence-digest-mismatch-blocks',a9['decision']=='BLOCK' and a9['feature_acceptance']['reason']=='INTENT_EVIDENCE_SHA_MISMATCH'); add('source-not-mutated',not a3['source_mutation']); add('capabilities-contract',capabilities()['external_pin_required'] is True and capabilities()['exact_artifact_binding'] is True); add('request-contract',request({'operation':'inspect','source':str(src)})['status']=='PASS')
    n=sum(x['pass'] for x in checks); return {"schema":SCHEMA,"version":VERSION,"tool_version":VERSION,"ai_contract_version":AI_CONTRACT_VERSION,"status":"PASS" if n==len(checks) else "FAIL","passed":n,"total":len(checks),"checks":checks}
def main():
    p=argparse.ArgumentParser(); sp=p.add_subparsers(dest='command'); sp.add_parser('capabilities'); sp.add_parser('self-test'); q=sp.add_parser('inspect'); q.add_argument('source'); q=sp.add_parser('build'); q.add_argument('source'); q.add_argument('--output',required=True); q.add_argument('--release-version',default='0'); q.add_argument('--mode',choices=['auto','pyz','zip'],default='auto'); q.add_argument('--verification-json'); q.add_argument('--acceptance-contract'); q.add_argument('--acceptance-evidence'); q.add_argument('--intent-assessment'); q.add_argument('--external-pin'); q.add_argument('--require-feature-acceptance',action='store_true'); q=sp.add_parser('request'); q.add_argument('source',nargs='?',default='-'); q.add_argument('--json-file'); a=p.parse_args(); cmd=a.command or 'capabilities'
    if cmd=='capabilities': out=capabilities()
    elif cmd=='self-test': out=self_test()
    elif cmd=='inspect': out=inspect_source(Path(a.source))
    elif cmd=='build': out=build(Path(a.source),Path(a.output),a.release_version,a.verification_json,a.acceptance_contract,a.acceptance_evidence,a.intent_assessment,a.external_pin,a.require_feature_acceptance,a.mode)
    else:
        payload=loadj(a.json_file) if a.json_file else json.load(sys.stdin) if a.source=='-' else loadj(a.source); out=request(payload)
    print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out.get('status') in ('PASS','RELEASE','RELEASE_WITH_WARNINGS') else 1
if __name__=='__main__': raise SystemExit(main())
