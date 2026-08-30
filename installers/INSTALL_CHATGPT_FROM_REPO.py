#!/usr/bin/env python3
"""Install Chat Local Runtime tools into a ChatGPT code sandbox from this repo checkout/unpacked archive."""
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path

VERSION = "0.1.0-public"
TOOLS = {
    "workerhub.pyz": "df16e41eb749b1fec1c360a51a8f36131b44c7bfe0f425d3c0864b8f162d82c2",
    "verificationrunner.pyz": "e205e651faf3f40c20a5d577916e9c5cf127ccc902d462073aa35c6594fd79db",
    "workspaceinspector.pyz": "1c91a206c69c469098f717d6fef9446e41a8c0f8afea7d4989defb80eb0b91c3",
    "smartdiff.pyz": "40f4a392b25ea69a99f64ba1e543baac430cb0fdd5663977d65276792762c2cd",
}
DIRS = ["code","programs","tests","fixtures","benchmarks","artifacts","cache","runtime","logs","scratch"]

def sha256(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def repo_root():
    return Path(__file__).resolve().parent.parent

def verify(root):
    root=Path(root).resolve(); out={}; ok_all=True
    for name,expected in TOOLS.items():
        p=root/"programs"/name
        ok=p.is_file() and sha256(p)==expected
        test=None
        if ok:
            cp=subprocess.run([sys.executable,str(p),"self-test"],capture_output=True,text=True,timeout=30,shell=False)
            try: parsed=json.loads(cp.stdout)
            except Exception: parsed={"raw":cp.stdout[:2000]}
            test={"returncode":cp.returncode,"result":parsed,"stderr":cp.stderr[:1000]}
            ok=cp.returncode==0 and parsed.get("status")=="PASS"
        out[name]={"ok":bool(ok),"path":str(p),"self_test":test}
        ok_all &= bool(ok)
    return {"schema":"chat-local-runtime/install-result-0.1","installer_version":VERSION,"status":"PASS" if ok_all else "FAIL","root":str(root),"tools":out}

def install(root):
    root=Path(root).resolve(); src=repo_root()/"dist"
    root.mkdir(parents=True,exist_ok=True)
    for d in DIRS: (root/d).mkdir(parents=True,exist_ok=True)
    for name,expected in TOOLS.items():
        s=src/name
        if not s.is_file(): raise FileNotFoundError(f"missing repo artifact: {s}")
        if sha256(s)!=expected: raise RuntimeError(f"source checksum mismatch: {name}")
        shutil.copy2(s,root/"programs"/name)
    (root/"programs"/"registry.json").write_text(json.dumps({"schema":"chat-local-runtime/registry-0.1","installer_version":VERSION,"tools":TOOLS},indent=2),encoding="utf-8")
    return verify(root)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",nargs="?",default="install",choices=["install","verify"])
    ap.add_argument("--root",default="/mnt/data/ai_program_lab")
    a=ap.parse_args()
    result=install(a.root) if a.command=="install" else verify(a.root)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__": raise SystemExit(main())
