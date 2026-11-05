from __future__ import annotations
import json, threading
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from app.kg_global.store import root, dumps
from app.kg_global.publish import Publisher
from app.modules.kg_import.config import Settings
from app.modules.kg_import.ontology import Ontology
from .store import ExactStore
from .package import rag_payload
_LOCK=threading.RLock()

@contextmanager
def operation_lock():
    """One writer across threads/processes, released by the OS on crashes."""
    with _LOCK:
        path=root()/'direct.lock';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a+b') as f:
            if f.tell()==0:f.write(b'0');f.flush()
            f.seek(0)
            import os
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise ValueError('Một lượt import khác đang chạy; chờ hoàn tất rồi thử lại.')
            try:yield
            finally:
                f.seek(0)
                if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def configured_store():
    settings=Settings.from_env()
    return ExactStore(root()/'global.sqlite3',Ontology.load(settings.ontology_path),settings.limits)

def verify_ontology(store,provenance):
    if 'ontology' not in provenance:return
    supplied=Ontology.from_dict(provenance['ontology'])
    if supplied!=store.ontology:raise ValueError('Ontology trong gói khác ontology đang cấu hình. Chọn đúng ontology trước khi nhập; không tự đổi ontology từ ZIP.')

def process(raw,provenance,target,rag_service=None,progress=lambda stage,data:None,store=None,publisher_factory=Publisher):
    if target not in ('kg','rag','both'):raise ValueError('Đích nhập không hợp lệ.')
    with operation_lock():
        own=store is None;s=store or configured_store()
        results={};sid=None
        try:
            progress('validation',{})
            verify_ontology(s,provenance);s.check(raw)
            if target in ('kg','both'):
                progress('identity',{})
                stored_provenance={k:v for k,v in provenance.items() if k not in ('filename','selected_file')}
                stats=s.ingest(raw,provenance.get('filename',''),stored_provenance)
                sid=s.seal_direct();progress('databases',{'snapshot_id':sid,'kg':stats})
                settings=Settings.from_env()
                settings=replace(settings,entity_embedding=replace(settings.entity_embedding,enabled=False))
                publisher_factory(s,settings).sync(sid)
                # No confirmation/review stage. The previous active snapshot survives any failed write.
                s.activate(sid)
                data=s.snapshot(sid)
                from app.kg_global.projection import build_projection
                projection=build_projection(data)
                results['kg']={'status':'completed','snapshot_id':sid,**stats,
                    'counts':{k:len(data[k]) for k in ('entities','relations','assertions','evidence')},
                    'graph_counts':projection['counts'],'ambiguous_terms':len(data.get('ambiguous_terms',[])),
                    'warnings':data.get('identity_warnings',[])}
                results['kg']['status']='completed'
                progress('kg_completed',results)
            if target in ('rag','both'):
                progress('rag_embedding',results)
                try:
                    if rag_service is None:raise ValueError('RAG chưa sẵn sàng; mở module RAG rồi thử lại. KG đã nhập không cần nhập lại.')
                    result=rag_service.import_data(rag_payload(raw,provenance))
                    if not result.get('ok'):raise ValueError('; '.join(result.get('errors',[])) or 'RAG không hợp lệ.')
                    results['rag']=result
                except Exception as exc:
                    results['rag']={'status':'failed','error':str(exc) if isinstance(exc,ValueError) else 'Ghi RAG thất bại; xem log và chạy lại RAG.'}
                    return {'status':'partial' if 'kg' in results else 'failed','results':results}
            return {'status':'completed','results':results}
        finally:
            if own:s.db.close()
