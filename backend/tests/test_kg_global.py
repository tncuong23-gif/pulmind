import copy,json
import pytest
from tests.upstream.kg.helpers import load_payload,load_ontology
from app.modules.kg_import.config import Limits
from app.kg_global.store import GlobalStore
from app.modules.kg_query.models import Fact,EntityRef
@pytest.fixture
def s(tmp_path):return GlobalStore(tmp_path/'global.sqlite3',load_ontology(),Limits())
def payload(doc='DOC_A'):
 p=load_payload();p['document']['document_id']=doc;return p
def merge_all(s):
 while True:
  v=s.review()
  if not v['pairs']:break
  ids=v['pairs'][0]['ids'];e=v['entities'][ids[0]]
  s.decide({'revision':v['revision'],'action':'merge','ids':ids,'target_id':ids[0],'name':e['canonical_name'],'type':e['type']})
def seal(s):
 s.review(semantic=True);return s.seal(s.revision(),True)['id']
def test_local_ids_do_not_identify_concepts(s):
 a=payload();b=payload('DOC_B');b['entities'][0]['canonical_name']='Different concept';b['entities'][0]['aliases']=[]
 s.ingest(a);s.ingest(b);d=s.materialize();local=a['entities'][0]['id']
 assert d['entity_mapping']['DOC_A']['ids'][local]!=d['entity_mapping']['DOC_B']['ids'][local]
 assert s.ingest(a)['status']=='unchanged'
def test_batch_merge_unique_triples_preserves_sources_and_restore(s,tmp_path):
 s.ingest(payload());s.ingest(payload('DOC_B'));merge_all(s);d=s.materialize()
 assert len(d['entities'])==len(payload()['entities'])
 assert len(d['relations'])==len(payload()['relations'])
 assert all(len(r['assertion_ids'])==2 for r in d['relations'].values())
 export=s.snapshot(seal(s));r=GlobalStore(tmp_path/'restore.sqlite3',load_ontology(),Limits());r.restore(export)
 for key in ('entities','entity_mapping','relations','assertions','evidence'):assert r.materialize()[key]==export[key]
def test_revision_guard_and_snapshot_immutability(s):
 s.ingest(payload());sid=seal(s);old=copy.deepcopy(s.snapshot(sid));s.ingest(payload('DOC_B'))
 with pytest.raises(ValueError):s.seal(old['revision'])
 assert s.snapshot(sid)==old
 with pytest.raises(ValueError):s.activate(sid)
 from tests.test_direct_import import mark_verified
 mark_verified(s,sid);s.activate(sid);assert s.active()['id']==sid
def test_withdraw_one_source_keeps_other(s):
 s.ingest(payload());s.ingest(payload('DOC_B'));merge_all(s);before=s.materialize();s.withdraw('DOC_A',s.revision());after=s.materialize()
 assert set(after['relations'])==set(before['relations'])
 assert all(len(r['assertion_ids'])==1 for r in after['relations'].values())
 assert len(after['document_history'])==1
def test_changed_document_version_and_history_restore(s,tmp_path):
 p=payload();s.ingest(p);p['document']['title']='Changed title';s.ingest(p)
 assert s.materialize()['documents']['DOC_A']['version']==2
 export=s.snapshot(seal(s));r=GlobalStore(tmp_path/'restore.sqlite3',load_ontology(),Limits());r.restore(export)
 assert r.materialize()['document_history']==export['document_history']
def test_seal_requires_current_scan_and_review(s):
 s.ingest(payload())
 with pytest.raises(ValueError,match='đối chiếu'):s.seal(s.revision())
 s.ingest(payload('DOC_B'));s.review(semantic=True)
 with pytest.raises(ValueError,match='nhóm'):s.seal(s.revision())
def test_distinct_pairs_not_merged_transitively(s):
 s.ingest(payload());s.ingest(payload('DOC_B'));v=s.review();ids=v['pairs'][0]['ids']
 s.decide({'revision':v['revision'],'action':'distinct','ids':ids})
 assert not any(set(p['ids'])==set(ids) for p in s.review()['pairs'])
 assert len(s.materialize()['entities'])==len(payload()['entities'])*2
def test_invalid_merge_does_not_mutate(s):
 s.ingest(payload());s.ingest(payload('DOC_B'));before=s.materialize();pair=next(p for p in s.review()['pairs'] if before['entities'][p['ids'][0]]['type']=='Disease');ids=pair['ids']
 with pytest.raises(ValueError):s.decide({'revision':s.revision(),'action':'merge','ids':ids,'target_id':ids[0],'type':'Medication','name':'Wrong type'})
 assert s.materialize()==before
def test_global_fact_keeps_assertion_properties():
 f=Fact(EntityRef('a','A','Disease'),'HAS_SYMPTOM',EntityRef('b','B','Symptom'),'a')
 f.add_row({'global_assertions':json.dumps([{'rel_id':'R','doc_id':'D1','properties_json':'{"negated":true}','evidence_ids':['E1']},{'rel_id':'R','doc_id':'D2','properties_json':'{"negated":false}','evidence_ids':['E2']}])})
 assert len(f.assertions)==2 and set(f.doc_ids)=={'D1','D2'}
 assert f.assertions[0]['properties']['negated'] is True
def test_tampered_restore_rolls_back(s,tmp_path):
 s.ingest(payload());export=s.snapshot(seal(s));export['relations'].clear();r=GlobalStore(tmp_path/'restore.sqlite3',load_ontology(),Limits())
 with pytest.raises(ValueError):r.restore(export)
 assert not r.materialize()['documents']

def test_http_global_workflow_and_confirmation(s,monkeypatch):
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 import app.kg_global.api as api
 monkeypatch.setattr(api,'_INSTANCE',s)
 app=FastAPI();app.include_router(api.create_router());client=TestClient(app)
 assert client.get('/kg-global').status_code==200
 assert client.post('/api/v1/kg-global/upload',json=payload()).status_code==200
 revision=client.get('/api/v1/kg-global').json()['revision']
 assert client.post('/api/v1/kg-global/seal',json={'revision':revision}).status_code==409
 s.review(semantic=True)
 response=client.post('/api/v1/kg-global/seal',json={'revision':revision,'confirmed':True})
 assert response.status_code==200
 sid=response.json()['id']
 assert client.get('/api/v1/kg-global/snapshots/'+sid).json()['schema_version']=='kg-global/1'
 assert client.post('/api/v1/kg-global/activate/'+sid,json={'confirmed':True}).status_code==409

def test_snapshot_query_isolation_and_no_legacy_fulltext():
 from app.modules.kg_query.service import KGQueryService
 from app.modules.kg_query import cypher
 from unittest.mock import Mock,MagicMock
 driver=Mock();session=MagicMock();driver.session.return_value=session
 tx=Mock();tx.run.return_value=[];session.__enter__.return_value.execute_read.side_effect=lambda fn:fn(tx)
 service=KGQueryService(driver,load_ontology());service.global_label='KGGlobal_S_'+('a'*32)
 service._read(cypher.RESOLVE_EXACT,q='x',types=None,limit=5)
 assert ':Entity' not in tx.run.call_args.args[0] and service.global_label in tx.run.call_args.args[0]
 tx.reset_mock();assert service._read(cypher.RESOLVE_FULLTEXT)==[];tx.run.assert_not_called()

def test_scan_cannot_be_silently_lost_after_decision(s):
 s.ingest(payload());s.ingest(payload('DOC_B'));s.review(semantic=True);pair=s.review()['pairs'][0]
 s.decide({'revision':s.revision(),'action':'distinct','ids':pair['ids']})
 with pytest.raises(ValueError,match='đối chiếu'):s.seal(s.revision())

@pytest.mark.parametrize("multipart_dataset",[False,True])
def test_publisher_failure_retry_and_activation_are_separate(s,monkeypatch,multipart_dataset):
 import sys,types
 from app.kg_global.publish import Publisher
 from app.modules.kg_import.config import Settings
 s.ingest(payload());sid=seal(s)
 if multipart_dataset:
  snapshot=s.snapshot
  monkeypatch.setattr(s,'snapshot',lambda sid:{**snapshot(sid),'multipart_dataset':'V71B'})
 calls=[];fail={'graph':True,'drop_edges':False,'mongo':False};nodes={};edges={}
 class Result:
  def __init__(self,rows=()):self.rows=list(rows)
  def consume(self):pass
  def __iter__(self):return iter(self.rows)
  def single(self):return self.rows[0]
 class Session:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def run(self,q,**params):
   calls.append((q,params))
   if fail['graph'] and q.startswith('UNWIND'):raise RuntimeError('injected graph failure')
   if 'SET e += row' in q:
    nodes.update({r['id']:dict(r) for r in params['rows']})
   if 'SET r.global_assertions' in q and not fail['drop_edges']:
    edges.update({r['id']:dict(r) for r in params['rows']})
   if 'properties(n) AS node' in q:return Result([{'node':n} for n in nodes.values()])
   if 'r.global_assertions AS assertions' in q:return Result(edges.values())
   if 'RETURN count(' in q:return Result([{'count':0}])
   return Result()
  def execute_write(self,fn):return fn(self)
 class Driver:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def session(self,**kwargs):return Session()
 class Collection:
  def __init__(self):self.rows={}
  def create_index(self,*args,**kwargs):pass
  def bulk_write(self,operations,**kwargs):
   for query,row in operations:self.rows[tuple(query.items())]=row
  def count_documents(self,query):return sum(r['snapshot']==query['snapshot'] for r in self.rows.values())
  def find(self,query,projection):
   key=next(k for k in query if k!='snapshot')
   for r in self.rows.values():
    if r['snapshot']==query['snapshot'] and r[key] in query[key]['$in']:
     yield {**r,'damaged':True} if fail['mongo'] else r
 class DB:
  def __init__(self):self.collections={}
  def __getitem__(self,name):return self.collections.setdefault(name,Collection())
 class Mongo:
  def __init__(self,*args,**kwargs):pass
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def __getitem__(self,name):return DB()
 monkeypatch.setitem(sys.modules,'pymongo',types.SimpleNamespace(MongoClient=Mongo,ReplaceOne=lambda *a,**k:a))
 monkeypatch.setitem(sys.modules,'neo4j',types.SimpleNamespace(GraphDatabase=types.SimpleNamespace(driver=lambda *a,**k:Driver())))
 publisher=Publisher(s,Settings())
 if multipart_dataset:
  fail['mongo']=True
  with pytest.raises(ValueError,match='VERIFY_MONGO_CONTENT'):publisher.sync(sid)
  assert s.active() is None and not calls
  fail['mongo']=False
 with pytest.raises(RuntimeError):publisher.sync(sid)
 assert s.active() is None
 with pytest.raises(ValueError):s.activate(sid)
 fail['graph']=False;fail['drop_edges']=True
 with pytest.raises(ValueError,match='VERIFY_RELATIONS'):publisher.sync(sid)
 assert s.active() is None
 with pytest.raises(ValueError):s.activate(sid)
 fail['drop_edges']=False;assert publisher.sync(sid)['state']=='ready';assert s.active() is None
 if multipart_dataset:assert publisher.sync(sid)['progress']['mongo_verified'] is True
 assert all(':Entity' not in q for q,_ in calls)
 edge_rows=[p['rows'] for q,p in calls if 'SET r.global_assertions' in q];assert edge_rows
 before=len(calls);publisher.sync(sid);assert len(calls)==before
 s.activate(sid);assert s.active()['id']==sid
