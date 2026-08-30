#!/usr/bin/env python3
from pathlib import Path
import hashlib, zipfile, json
ROOT=Path(__file__).resolve().parents[1]
DT=(2026,1,1,0,0,0)

def build(srcdir:Path,out:Path, module_files):
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for arc,src in module_files:
            zi=zipfile.ZipInfo(arc,DT); zi.compress_type=zipfile.ZIP_DEFLATED; zi.external_attr=(0o644&0xffff)<<16
            z.writestr(zi,(srcdir/src).read_bytes())
    return hashlib.sha256(out.read_bytes()).hexdigest()

def main():
    vr=build(ROOT/'src/verification_runner',ROOT/'dist/active/verificationrunner-0.3.0.pyz',[("__main__.py",Path('__main__.py')),("verification_runner.py",Path('verification_runner.py'))])
    ab=build(ROOT/'src/artifact_builder',ROOT/'dist/active/artifactbuilder-0.1.2.pyz',[("__main__.py",Path('__main__.py')),("artifact_builder.py",Path('artifact_builder.py'))])
    print(json.dumps({'verificationrunner-0.3.0.pyz':vr,'artifactbuilder-0.1.2.pyz':ab},indent=2))
if __name__=='__main__': main()
