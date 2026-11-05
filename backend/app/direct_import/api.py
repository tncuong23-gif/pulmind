import json, logging, uuid, threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from .service import configured_store, process, operation_lock
from .package import load_package, MAX_ZIP
from app.kg_global.store import dumps
WEB=Path(__file__).parent/'web';POOL=ThreadPoolExecutor(max_workers=1);LOCK=threading.Lock();PENDING=set();log=logging.getLogger(__name__)

def write_job(jid,state,data):
    s=configured_store()
    try:
        with s.write():
            old=s.db.execute('SELECT data FROM direct_jobs WHERE id=?',(jid,)).fetchone()
            previous=json.loads(old[0]) if old else {}
            stamp=datetime.now(timezone.utc).isoformat()
            value={**previous,**data,'id':jid,'status':state,'updated_at':stamp,'started_at':previous.get('started_at',stamp)}
            s.db.execute('INSERT OR REPLACE INTO direct_jobs VALUES(?,?,?)',(jid,state,dumps(value)))
    finally:s.db.close()

def jobs(jid=None):
    s=configured_store()
    try:
        with s.lock:
            rows=list(s.db.execute('SELECT * FROM direct_jobs WHERE id=?',(jid,))) if jid else list(s.db.execute('SELECT * FROM direct_jobs ORDER BY rowid DESC LIMIT 30'))
        out=[]
        for row in rows:
            v=json.loads(row['data'])
            if v['status'] in ('queued','running') and row['id'] not in PENDING:
                try:
                    with operation_lock():v.update(status='interrupted',message='Tiến trình trước đã dừng. Chọn lại file để tiếp tục; dữ liệu đã lưu sẽ được dùng lại.')
                except ValueError:pass
            out.append(v)
        return out
    finally:s.db.close()

class LegacyImportGuard:
    """Retired identity-writing routes cannot bypass the canonical registry."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']=='http':
            path=scope['path'];method=scope['method']
            if path.endswith('/duplicates') or path=='/imports' and b'module=context' not in scope.get('query_string',b''):
                return await RedirectResponse('/direct-import?target=kg',status_code=307)(scope,receive,send)
            old=('/api/v1/kg-global/' in path or '/api/review/' in path or '/api/v1/imports/kg/' in path or '/api/v1/kg/import' in path)
            if old and (method not in ('GET','HEAD','OPTIONS') or '/api/review/' in path):
                return await JSONResponse({'detail':'Luồng duyệt/import KG cũ đã tắt. Dùng /direct-import hoặc /api/v1/direct-import.'},status_code=410)(scope,receive,send)
        await self.app(scope,receive,send)

def create_router():
    api=APIRouter()
    @api.get('/direct-import')
    @api.get('/kg-global')
    async def page():return FileResponse(WEB/'index.html',headers={'Cache-Control':'no-store'})
    @api.get('/direct-import-assets/app.js')
    async def script():return FileResponse(WEB/'app.js',headers={'Cache-Control':'no-cache'})
    @api.get('/api/v1/direct-import/jobs')
    def history():return jobs()
    @api.get('/api/v1/direct-import/jobs/{jid}')
    def job(jid:str):
        values=jobs(jid)
        if not values:raise HTTPException(404,'Không tìm thấy lượt nhập.')
        return values[0]
    @api.get('/api/v1/direct-import/snapshots/{sid}')
    def snapshot(sid:str):
        s=configured_store()
        try:
            data=s.snapshot(sid)
            return Response(dumps(data),media_type='application/json',headers={'Content-Disposition':'attachment; filename="kg_snapshot.json"'})
        except ValueError as exc:raise HTTPException(404,str(exc))
        finally:s.db.close()
    @api.get('/api/v1/direct-import/source/{doc_id}/{entity_id}')
    def mapping(doc_id:str,entity_id:str):
        s=configured_store()
        try:
            active=s.active()
            if not active:return []
            data=s.snapshot(active['id']);result=[]
            current=data['entity_mapping'].get(doc_id)
            if current and entity_id in current['ids']:
                result.append({'document_id':doc_id,'version':current['version'],'original_entity_id':entity_id,'canonical_entity_id':current['ids'][entity_id],'active_source':True})
            for h in data.get('document_history',[]):
                if h['document_id']==doc_id and entity_id in h.get('canonical_mapping',{}):
                    result.append({'document_id':doc_id,'version':h['version'],'original_entity_id':entity_id,'canonical_entity_id':h['canonical_mapping'][entity_id],'active_source':False})
            result += [r for r in data.get('source_entity_mapping',[]) if r['source_document_id']==doc_id and r['source_entity_id']==entity_id]
            return result
        finally:s.db.close()
    @api.post('/api/v1/direct-import',status_code=202)
    async def upload(request:Request,filename:str,target:str='kg',selection:str='merged'):
        if target not in ('kg','rag','both'):raise HTTPException(422,'Đích nhập không hợp lệ.')
        content=bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content)>MAX_ZIP:raise HTTPException(413,'File tối đa 64 MiB.')
        try:raw,provenance=load_package(bytes(content),filename,selection)
        except (ValueError,KeyError,TypeError) as exc:raise HTTPException(422,str(exc))
        jid=uuid.uuid4().hex
        with LOCK:
            if PENDING:raise HTTPException(409,'Đang nhập dữ liệu. Chờ lượt hiện tại hoàn tất.')
            PENDING.add(jid)
        try:write_job(jid,'queued',{'filename':filename,'target':target,'stage':'queued'})
        except Exception:
            PENDING.discard(jid);raise
        app=request.app
        def work():
            progress=lambda stage,data:write_job(jid,'running',{'filename':filename,'target':target,'stage':stage,**data})
            try:
                modules=getattr(app.state,'embedded_apps',{})
                rag=getattr(modules.get('rag').state,'service',None) if modules.get('rag') else None
                result=process(raw,provenance,target,rag,progress)
                write_job(jid,result['status'],{'filename':filename,'target':target,**result})
            except Exception as exc:
                log.exception('direct import failed')
                write_job(jid,'failed',{'filename':filename,'target':target,'error':str(exc) if isinstance(exc,ValueError) else 'Ghi dữ liệu thất bại; xem log backend. Chọn lại file để thử tiếp.'})
            finally:PENDING.discard(jid)
        POOL.submit(work)
        return {'id':jid,'status':'queued'}
    return api
