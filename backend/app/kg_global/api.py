from __future__ import annotations
import json,threading,uuid,logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import FileResponse,Response
from starlette.concurrency import run_in_threadpool
from .store import GlobalStore,root,dumps
from .publish import Publisher
from app.modules.kg_import.config import Settings
from app.modules.kg_import.ontology import Ontology
WEB=Path(__file__).parent/'web';log=logging.getLogger('kg_global')
_INSTANCE=None;LOCK=threading.RLock();POOL=ThreadPoolExecutor(max_workers=1);JOBS={}
def store():
    global _INSTANCE
    with LOCK:
        if _INSTANCE is None:
            settings=Settings.from_env();_INSTANCE=GlobalStore(root()/'global.sqlite3',Ontology.load(settings.ontology_path),settings.limits)
        return _INSTANCE

def busy():
    if any(j['state']=='running' for j in JOBS.values()):raise ValueError('Đang xử lý. Chờ lượt hiện tại hoàn tất.')
def start(fn):
    with LOCK:
        busy();jid=uuid.uuid4().hex;JOBS[jid]={'id':jid,'state':'running'}
        def work():
            try:result=fn();JOBS[jid]={'id':jid,'state':'completed','result':result}
            except Exception as exc:
                log.exception('global.job_failed');JOBS[jid]={'id':jid,'state':'failed','error':str(exc) if isinstance(exc,ValueError) else 'Dịch vụ chưa sẵn sàng; kiểm tra log backend và thử lại.'}
        POOL.submit(work);return JOBS[jid]
async def body(request,limit=20*1024*1024):
    buf=bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf)>limit:raise HTTPException(413,'File vượt giới hạn dung lượng.')
    try:
        value=json.loads(buf.decode('utf-8-sig'))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,UnicodeError):raise HTTPException(422,'JSON phải là một đối tượng hợp lệ.')
async def call(fn):
    try:return await run_in_threadpool(fn)
    except (ValueError,KeyError,TypeError) as exc:raise HTTPException(409,str(exc))
    except Exception:
        log.exception('global.api_failed');raise HTTPException(503,'Không thể thực hiện; kiểm tra log backend.')
def mutate(fn):
    with LOCK:busy();return fn()
def create_router():
    api=APIRouter()
    @api.get('/kg-global')
    async def page():return FileResponse(WEB/'index.html',headers={'Cache-Control':'no-store'})
    @api.get('/kg-global-assets/app.js')
    async def script():return FileResponse(WEB/'app.js',headers={'Cache-Control':'no-cache'})
    @api.get('/api/v1/kg-global')
    async def overview():return await call(lambda:{**store().review(),'types':sorted(store().ontology.entity_types)})
    @api.post('/api/v1/kg-global/upload')
    async def upload(request:Request):
        p=await body(request);return await call(lambda:mutate(lambda:store().ingest(p)))
    @api.post('/api/v1/kg-global/folder')
    async def folder():
        def ingest():
            rows=[];directory=root().parent/'import'/'kg'
            for path in sorted(p for p in directory.rglob('*') if p.is_file() and p.suffix.lower()=='.json'):
                if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):continue
                try:
                    if path.stat().st_size>20*1024*1024:raise ValueError('File quá 20 MB.')
                    result=store().ingest(json.loads(path.read_text(encoding='utf-8-sig')),path.name)
                    rows.append({'filename':str(path.relative_to(directory)),**result})
                except (ValueError,OSError) as exc:rows.append({'filename':str(path.relative_to(directory)),'status':'failed','error':str(exc)[:1000]})
            return rows
        return await call(lambda:start(ingest))
    @api.post('/api/v1/kg-global/scan')
    async def scan():
        def run():
            settings=Settings.from_env();encoder=None;index=None
            try:
                if settings.entity_embedding.enabled:
                    from app.modules.kg_import.entity_vector import QdrantEntityIndex
                    index=QdrantEntityIndex(settings.entity_embedding);encoder=index.encoder
                result=store().review(semantic=True,encoder=encoder)
                result['scan_mode']='embedding_and_names' if encoder else 'names_only_embedding_disabled'
                return result
            finally:
                if index:index.close()
        return await call(lambda:start(run))
    @api.get('/api/v1/kg-global/jobs/{jid}')
    async def job(jid:str):
        if jid not in JOBS:raise HTTPException(404,'Lượt xử lý không còn trong tiến trình; xem trạng thái phiên bản và thử lại nếu cần.')
        return JOBS[jid]
    @api.post('/api/v1/kg-global/decide')
    async def decide(request:Request):
        p=await body(request);return await call(lambda:mutate(lambda:store().decide(p)))
    @api.post('/api/v1/kg-global/withdraw')
    async def withdraw(request:Request):
        p=await body(request)
        if p.get('confirmed') is not True:raise HTTPException(409,'Cần xác nhận rút tài liệu.')
        return await call(lambda:mutate(lambda:store().withdraw(p['document_id'],p['revision'])))
    @api.post('/api/v1/kg-global/exclude')
    async def exclude(request:Request):
        p=await body(request);return await call(lambda:mutate(lambda:store().exclude(p['assertion_id'],p['reason'],p['revision'])))
    @api.get('/api/v1/kg-global/draft')
    async def draft():return await call(lambda:store().materialize())
    @api.get('/api/v1/kg-global/plan')
    async def plan():return await call(lambda:store().plan())

    @api.post('/api/v1/kg-global/seal')
    async def seal(request:Request):
        p=await body(request)
        if p.get('confirmed') is not True:raise HTTPException(409,'Cần xác nhận chốt phiên bản.')
        return await call(lambda:mutate(lambda:store().seal(p['revision'],p.get('ack_conflicts') is True)))
    @api.get('/api/v1/kg-global/snapshots/{sid}')
    async def download(sid:str):
        data=await call(lambda:store().snapshot(sid))
        return Response(dumps(data),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="global_{sid}.json"'})
    @api.post('/api/v1/kg-global/sync/{sid}')
    async def sync(sid:str,request:Request):
        p=await body(request)
        if p.get('confirmed') is not True:raise HTTPException(409,'Cần xác nhận đồng bộ.')
        return await call(lambda:start(lambda:Publisher(store(),Settings.from_env()).sync(sid)))
    @api.post('/api/v1/kg-global/activate/{sid}')
    async def activate(sid:str,request:Request):
        p=await body(request)
        if p.get('confirmed') is not True:raise HTTPException(409,'Cần xác nhận chuyển phiên bản truy vấn.')
        return await call(lambda:mutate(lambda:store().activate(sid)))
    @api.post('/api/v1/kg-global/migration')
    async def migration():
        def compare():
            from neo4j import GraphDatabase
            from app.modules.kg_import.utils import fold
            settings=Settings.from_env();data=store().materialize();names={}
            for gid,e in data['entities'].items():
                for name in [e['canonical_name'],*e['aliases']]:names.setdefault((fold(name),e['type']),set()).add(gid)
            rows=[]
            with GraphDatabase.driver(settings.neo4j_uri,auth=(settings.neo4j_username,settings.neo4j_password)) as driver:
                with driver.session(database=settings.neo4j_database) as session:
                    for r in session.run('MATCH (e:Entity) RETURN e.id AS id,e.canonical_name AS name,e.entity_type AS type,e.aliases AS aliases'):
                        matches=set()
                        for name in [r['name'],*(r['aliases'] or [])]:matches.update(names.get((fold(name),r['type']),set()))
                        rows.append({'legacy_id':r['id'],'name':r['name'],'type':r['type'],'global_candidates':sorted(matches),
                                     'status':'unique_candidate' if len(matches)==1 else 'ambiguous' if matches else 'missing_in_draft'})
            return {'read_only':True,'revision':data['revision'],'rows':rows}
        return await call(lambda:start(compare))

    @api.post('/api/v1/kg-global/legacy')
    async def legacy(request:Request):
        p=await body(request)
        if p.get('confirmed') is not True:raise HTTPException(409,'Cần xác nhận quay về KG cũ.')
        def action():
            with store().write():store().db.execute("DELETE FROM meta WHERE key='active'")
        return await call(lambda:mutate(action))
    @api.post('/api/v1/kg-global/restore')
    async def restore(request:Request):
        p=await body(request,512*1024*1024);return await call(lambda:mutate(lambda:store().restore(p)))
    return api
