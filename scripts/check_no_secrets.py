#!/usr/bin/env python3
from __future__ import annotations
import re, sys, zipfile
from pathlib import Path
BLOCKED_NAMES={'.env','id_rsa','id_ed25519'}
PATTERNS=[
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{20,}\b'),
]

def scan(path:Path):
    issues=[]
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                name=info.filename
                base=Path(name).name
                if base in BLOCKED_NAMES or base.endswith(('.db','.sqlite','.sqlite3')): issues.append(f'Nom interdit: {name}'); continue
                if info.file_size>5_000_000: continue
                data=z.read(info)
                if any(p.search(data) for p in PATTERNS): issues.append(f'Secret probable: {name}')
    else:
        for f in path.rglob('*'):
            if not f.is_file() or '.git' in f.parts: continue
            if f.name in BLOCKED_NAMES or f.suffix.lower() in {'.db','.sqlite','.sqlite3'}: issues.append(f'Nom interdit: {f.relative_to(path)}');continue
            if f.stat().st_size>5_000_000: continue
            data=f.read_bytes()
            if any(p.search(data) for p in PATTERNS): issues.append(f'Secret probable: {f.relative_to(path)}')
    return issues
if __name__=='__main__':
    target=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).resolve().parents[1])
    issues=scan(target)
    print('\n'.join(issues) if issues else 'OK — aucun secret évident détecté.')
    raise SystemExit(1 if issues else 0)
