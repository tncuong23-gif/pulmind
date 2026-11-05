"""Apply only the supplied patch files. Standard-library Python; no database access."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

PACKAGE=Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_path(root,relative):
    rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe patch path: '+relative)
    path=root/rel
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Path leaves project: '+relative)
    for item in (path,*path.parents):
        if item==root:break
        if item.is_symlink():raise ValueError('Symlink not supported: '+str(item))
    return path

def project_root(value):
    path=Path(value).expanduser().resolve()
    if not (path/'backend/app/direct_import/store.py').is_file() or not (path/'backend/app/kg_global/store.py').is_file():
        raise ValueError('Chon thu muc goc medical-ai-integrated co backend/app/direct_import va backend/app/kg_global.')
    return path

def atomic_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.kg-update-',dir=target.parent)
    os.close(fd)
    try:
        shutil.copy2(source,name)
        os.replace(name,target)
    finally:
        Path(name).unlink(missing_ok=True)

def apply(project,package=PACKAGE):
    project=project_root(project);package=Path(package).resolve()
    manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    pending=[]
    # Check every file BEFORE changing the first one. Local customizations stop the update.
    for record in manifest['files']:
        source=safe_path(package/'payload',record['path']);target=safe_path(project,record['path'])
        if not source.is_file() or digest(source)!=record['sha256']:raise ValueError('Goi cap nhat hong: '+record['path'])
        if target.exists() and not target.is_file():raise ValueError('Duong dan dich khong phai file: '+record['path'])
        current=digest(target) if target.is_file() else None
        if current==record['sha256']:continue
        accepted = [record.get('base_sha256'), *record.get('compatible_base_sha256', [])]
        if current not in accepted:
            raise ValueError('File dich khac ban goc da kiem tra; giu nguyen de tranh mat sua doi: '+record['path'])
        pending.append({**record,'base_sha256':current,'existed':target.is_file()})
    if not pending:
        print('Code da la ban cap nhat nay. Khong ghi de, khong tao backup moi.')
        return None
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    backup=project/'kg_patch_backups'/stamp;backup.mkdir(parents=True,exist_ok=False)
    receipt={'state':'preparing','project':str(project),'files':pending}
    receipt_file=backup/'receipt.json'
    receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    for record in pending:
        if record['existed']:atomic_copy(safe_path(project,record['path']),safe_path(backup/'files',record['path']))
    written=[]
    try:
        for record in pending:
            target=safe_path(project,record['path'])
            # A concurrent editor/writer must not be silently overwritten.
            current=digest(target) if target.is_file() else None
            if current!=record.get('base_sha256'):raise ValueError('File vua thay doi: '+record['path'])
            atomic_copy(safe_path(package/'payload',record['path']),target);written.append(record)
            if digest(target)!=record['sha256']:raise ValueError('Sai checksum sau ghi: '+record['path'])
        receipt['state']='applied';receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        for record in reversed(written):
            target=safe_path(project,record['path'])
            if record['existed']:atomic_copy(safe_path(backup/'files',record['path']),target)
            else:target.unlink(missing_ok=True)
        receipt['state']='rolled_back_after_error';receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    print('Da cap nhat '+str(len(pending))+' file. Backup: '+str(backup))
    print('Khong thay doi .env, model, du lieu hoac CSDL. Khoi dong lai medical-ai-integrated de dung code moi.')
    return backup

def rollback(project,backup=None):
    project=project_root(project)
    if backup is None:
        candidates=[]
        for p in (project/'kg_patch_backups').glob('*/receipt.json'):
            value=json.loads(p.read_text(encoding='utf-8'))
            if value.get('state')=='applied':candidates.append(p)
        if not candidates:raise ValueError('Khong co ban cap nhat nao de hoan tac.')
        backup=sorted(candidates)[-1].parent
    backup=Path(backup).resolve()
    if not backup.is_relative_to((project/'kg_patch_backups').resolve()):raise ValueError('Backup khong thuoc du an nay.')
    receipt_file=backup/'receipt.json';receipt=json.loads(receipt_file.read_text(encoding='utf-8'))
    if receipt.get('state')!='applied' or Path(receipt['project']).resolve()!=project:raise ValueError('Backup khong hop le hoac da hoan tac.')
    for record in receipt['files']:
        packaged=safe_path(PACKAGE/'payload',record['path'])
        if not packaged.is_file() or digest(packaged)!=record['sha256']:
            raise ValueError('Hay dung dung goi cap nhat da tao backup nay.')
        target=safe_path(project,record['path'])
        if not target.is_file() or digest(target)!=record['sha256']:
            raise ValueError('Code da thay doi sau cap nhat; khong tu dong ghi de: '+record['path'])
        if record['existed']:
            saved=safe_path(backup/'files',record['path'])
            if not saved.is_file() or digest(saved)!=record['base_sha256']:raise ValueError('Backup hong: '+record['path'])
    restored=[]
    try:
        for record in reversed(receipt['files']):
            target=safe_path(project,record['path'])
            if record['existed']:atomic_copy(safe_path(backup/'files',record['path']),target)
            else:target.unlink()
            restored.append(record)
    except Exception:
        # Recover the applied version if rollback stops part-way through.
        for record in restored:atomic_copy(safe_path(PACKAGE/'payload',record['path']),safe_path(project,record['path']))
        raise
    receipt['state']='rolled_back';receipt_file.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Da hoan tac code tu: '+str(backup))
    print('Khong hoan tac du lieu CSDL. Khoi dong lai ung dung sau khi hoan tac.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['apply','rollback']);parser.add_argument('--project',required=True);parser.add_argument('--backup')
    args=parser.parse_args()
    try:
        if args.action=='apply':apply(args.project)
        else:rollback(args.project,args.backup)
    except Exception as exc:
        print('[LOI] '+str(exc),file=sys.stderr);sys.exit(1)
