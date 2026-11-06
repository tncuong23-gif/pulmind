"""Isolated immutable projections. Active pointer changes only after all stores succeed."""
import re,json,threading
from dataclasses import replace
from .projection import build_projection, verify_projection
LOCK=threading.Lock()
def label(sid):
    if not re.fullmatch(r'S_[0-9a-f]{32}',sid):raise ValueError('ID phiên bản không hợp lệ.')
    return 'KGGlobal_'+sid

class Publisher:
    def __init__(self,store,settings):self.store,self.settings=store,settings
    def sync(self,sid):
        if not LOCK.acquire(blocking=False):raise ValueError('Đang đồng bộ một phiên bản khác.')
        try:
            data=self.store.snapshot(sid);kind=label(sid)
            projection=build_projection(data)
            with self.store.lock:
                row=self.store.db.execute('SELECT state,progress FROM snapshots WHERE id=?',(sid,)).fetchone()
            if row['state']=='ready':return {'state':'ready','progress':json.loads(row['progress']),'message':'Phiên bản đã đồng bộ; không ghi lại.'}
            from neo4j import GraphDatabase
            from pymongo import MongoClient,ReplaceOne
            settings=self.settings
            progress={};self.store.progress(sid,'syncing',progress)
            with MongoClient(settings.mongodb_uri,serverSelectionTimeoutMS=5000) as mongo, GraphDatabase.driver(settings.neo4j_uri,auth=(settings.neo4j_username,settings.neo4j_password)) as driver:
                db=mongo[settings.mongodb_database]
                for collection,key,rows in [
                    ('global_documents','document_id',[{'document_id':i,**d} for i,d in data['documents'].items()]),
                    ('global_evidence','evidence_id',list(data['evidence'].values())),
                    ('global_assertions','id',list(data['assertions'].values())),
                    ('global_entity_mappings','document_id',[{'document_id':doc,**m} for doc,m in data['entity_mapping'].items()]),
                    ('global_alias_sources','id',data.get('alias_sources',[])),
                    ('global_source_entity_mapping','id',data.get('source_entity_mapping',[])),
                    ('global_redirects','id',[{'id':old,'target':target} for old,target in data.get('redirects',{}).items()]),
                    ('global_history','history_id',[{'history_id':str(h['document_id'])+':'+str(h['version']),**h} for h in data.get('document_history',[])])]:
                    db[collection].create_index([('snapshot',1),(key,1)],unique=True)
                    for start in range(0,len(rows),500):
                        ops=[ReplaceOne({'snapshot':sid,key:r[key]},{**r,'snapshot':sid},upsert=True) for r in rows[start:start+500]]
                        if ops:db[collection].bulk_write(ops,ordered=True)
                    if data.get('multipart_dataset'):
                        coll=db[collection]
                        if coll.count_documents({'snapshot':sid})!=len(rows):
                            raise ValueError('VERIFY_MONGO_COUNT: '+collection)
                        for start in range(0,len(rows),500):
                            expected={r[key]:{**r,'snapshot':sid} for r in rows[start:start+500]}
                            actual={r[key]:r for r in coll.find(
                                {'snapshot':sid,key:{'$in':list(expected)}},{'_id':0})}
                            if actual!=expected:
                                raise ValueError('VERIFY_MONGO_CONTENT: '+collection)
                if data.get('multipart_dataset'):
                    progress['mongo_verified']=True
                progress['mongo']='ready';self.store.progress(sid,'syncing',progress)
                # Each snapshot has its own label; legacy :Entity graph is untouched.
                with driver.session(database=settings.neo4j_database) as session:
                    session.run(f'CREATE CONSTRAINT {kind}_id IF NOT EXISTS FOR (n:{kind}) REQUIRE n.id IS UNIQUE').consume()
                    def write(tx):
                        nodes=list(projection['nodes'].values())
                        for start in range(0,len(nodes),500):tx.run(f'UNWIND $rows AS row MERGE (e:{kind} {{id:row.id}}) SET e += row',rows=nodes[start:start+500]).consume()
                        bytype={}
                        for edge in projection['edges'].values():
                            bytype.setdefault(edge['type'],[]).append(edge)
                        for rel,rows in bytype.items():
                            for start in range(0,len(rows),300):tx.run(f'UNWIND $rows AS row MATCH (s:{kind} {{id:row.s}}),(t:{kind} {{id:row.t}}) MERGE (s)-[r:`{rel}` {{id:row.id}}]->(t) SET r.global_assertions=row.assertions',rows=rows[start:start+300]).consume()
                        return verify_projection(tx,kind,projection)
                    progress['verification']=session.execute_write(write)
                progress['neo4j']='ready';self.store.progress(sid,'syncing',progress)
                if settings.entity_embedding.enabled:
                    from app.modules.kg_import.entity_vector import QdrantEntityIndex
                    index=QdrantEntityIndex(replace(settings.entity_embedding,collection=settings.entity_embedding.collection+'_'+sid))
                    try:
                        index.begin_build()
                        rows=[{'id':i,'canonical_name':e['canonical_name'],'entity_type':e['entity_type'],'aliases':e['aliases']} for i,e in projection['nodes'].items()]
                        for start in range(0,len(rows),100):index.upsert_entities(rows[start:start+100])
                        index.finish_build();progress['qdrant']='ready'
                    finally:index.close()
                else:progress['qdrant']='disabled_by_configuration'
            self.store.progress(sid,'ready',progress)
            return {'state':'ready','progress':progress,'message':'Đã đồng bộ. Chọn kích hoạt để phục vụ truy vấn.'}
        except Exception as exc:
            self.store.progress(sid,'failed',{'completed':locals().get('progress',{}),'error':type(exc).__name__})
            raise
        finally:LOCK.release()
