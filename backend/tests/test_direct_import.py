import copy, io, json, zipfile, threading, tempfile, pathlib, unittest
from unittest.mock import patch
from app.direct_import.store import ExactStore
from app.direct_import.package import load_package,rag_payload
from app.direct_import.service import process,verify_ontology
from app.modules.kg_import.ontology import Ontology
from app.modules.kg_import.config import Limits

ONTOLOGY={'entity_types':['F','G'],'relation_types':{'RELATED':{'domain':['F'],'range':['F']},'HAS':{'domain':['F'],'range':['G']}}}
def entity(name,aliases=(),kind='F',eid='E1',props=None):return {'id':eid,'type':kind,'canonical_name':name,'aliases':list(aliases),'properties':props or {}}
def payload(doc='D1',entities=None,relation=False):
    es=entities or [entity('A',['B','C'])]
    p={'schema_version':'1.0','document':{'document_id':doc,'title':doc,'document_type':'guideline','language':'vi','sections':[{'section_id':'SEC1','title':'Section','paragraphs':[{'paragraph_id':'PAR1','sentences':[{'sentence_id':'S1','text':'Original sentence.'}]}]}]},'entities':es,'relations':[],'propositions':[]}
    if relation:
        p['entities']=es+[entity('X',kind='G',eid='E2')]
        p['relations']=[{'id':'R1','type':'HAS','source':es[0]['id'],'target':'E2','proposition_ids':['P1']}]
        p['propositions']=[{'id':'P1','text':'Original sentence.','evidence':[{'sentence_id':'S1'}]}]
    return p

def mark_verified(store,sid):
    from app.kg_global.projection import build_projection,PROJECTION_VERSION
    store.progress(sid,'ready',{'verification':{**build_projection(store.snapshot(sid))['counts'],'version':PROJECTION_VERSION,'verified':True}})

class ExactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.s=ExactStore(pathlib.Path(self.tmp.name)/'global.sqlite3',Ontology.from_dict(ONTOLOGY),Limits());self.addCleanup(self.s.db.close)
    def test_alias_chain_does_not_merge(self):
        a=payload();self.s.ingest(a)
        for i,e in enumerate([entity('B'),entity('C'),entity('D',['B']),entity('E',['D'])],2):self.s.ingest(payload('D'+str(i),[e]))
        d=self.s.materialize();self.assertEqual(len(d['entities']),5);self.assertFalse(d['redirects'])
        self.assertTrue(self.s.lookup_term('B','F')['ambiguous'])
        self.assertEqual(d['documents']['D1']['payload'],a)

    def test_bridge_keeps_entities_and_evidence_separate(self):
        self.s.ingest(payload('D1',[entity('A',['B'])],True));self.s.ingest(payload('D2',[entity('D',['C'])],True))
        old=self.s.materialize()
        self.s.ingest(payload('D3',[entity('E',['B','C'])]));d=self.s.materialize()
        self.assertEqual(d['entity_mapping']['D1'],old['entity_mapping']['D1'])
        self.assertEqual(d['entity_mapping']['D2'],old['entity_mapping']['D2'])
        self.assertFalse(d['redirects']);self.assertEqual(len(d['relations']),2)
        self.assertEqual({e['document_id'] for e in d['evidence'].values()},{'D1','D2'})

    def test_different_types_separate(self):
        self.s.ingest(payload(entities=[entity('A',['B']),entity('B',kind='G',eid='E2')]))
        self.assertEqual(len(self.s.materialize()['entities']),2)
    def test_local_id_collision_not_identity(self):
        self.s.ingest(payload('D1',[entity('A')]));self.s.ingest(payload('D2',[entity('Z')]))
        self.assertEqual(len(self.s.materialize()['entities']),2)
    def test_reimport_no_new_snapshot_or_versions(self):
        p=payload();self.s.ingest(p);sid=self.s.seal_direct();self.assertEqual(self.s.ingest(p)['status'],'unchanged');self.assertEqual(self.s.seal_direct(),sid)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM documents').fetchone()[0],1)
    def test_alias_only_update_is_not_lost(self):
        p=payload();self.s.ingest(p);p['entities'][0]['aliases'].append('Z');self.s.ingest(p)
        self.assertIn('Z',next(iter(self.s.materialize()['entities'].values()))['aliases']);self.assertEqual(len(self.s.materialize()['document_history']),1)
    def test_cumulative_source_mappings_survive_versions_and_merge(self):
        p=payload();prov={'source_document_ids':['SRC'],'entity_mapping':{'entity_mappings':[{'merged_id':'E1','sources':[{'document_id':'SRC','entity_id':'LOCAL','canonical_name':'A'}]}]},'alias_evidence':[{'alias':'B','source_line':5}]}
        self.s.ingest(p,provenance=prov);p['entities'][0]['aliases'].append('D');self.s.ingest(p,provenance=prov)
        d=self.s.materialize();rows=d['source_entity_mapping'];gid=d['entity_mapping']['D1']['ids']['E1']
        self.assertEqual(len(rows),2);self.assertEqual({r['import_version'] for r in rows},{1,2})
        self.assertTrue(all(r['canonical_entity_id']==gid and r['source_entity_id']=='LOCAL' for r in rows))
        self.assertEqual(d['document_history'][0]['provenance'],prov)
        self.assertEqual(d['document_history'][0]['canonical_mapping']['E1'],gid)
    def test_conflicting_alias_properties_stay_separate_and_review_rejects_merge(self):
        self.s.ingest(payload('D1',[entity('A',['B'],props={'strength':'10'})]))
        self.s.ingest(payload('D2',[entity('B',props={'strength':'20'})]));before=self.s.materialize();ids=list(before['entities'])
        with self.assertRaisesRegex(ValueError,'mâu thuẫn'):
            self.s.decide({'revision':self.s.revision(),'action':'merge','ids':ids,'target_id':ids[0],'type':'F','name':'Approved'})
        self.assertEqual(self.s.materialize(),before)

    def test_alias_edge_is_preserved_and_review_self_loop_rolls_back(self):
        p=payload(entities=[entity('A',['B']),entity('B',eid='E2')]);p['relations']=[{'id':'R','type':'RELATED','source':'E1','target':'E2','proposition_ids':['P']}];p['propositions']=[{'id':'P','text':'Original sentence.','evidence':[{'sentence_id':'S1'}]}]
        self.s.ingest(p);before=self.s.materialize();ids=list(before['entities'])
        self.assertEqual(len(before['relations']),1)
        with self.assertRaisesRegex(ValueError,'tự nối'):
            self.s.decide({'revision':self.s.revision(),'action':'merge','ids':ids,'target_id':ids[0],'type':'F','name':'Approved'})
        self.assertEqual(self.s.materialize(),before)

    def test_preserve_polarity_and_source_properties(self):
        a=payload('D1',relation=True);b=payload('D2',relation=True);b['relations'][0]['properties']={'negated':True}
        self.s.ingest(a);self.s.ingest(b)
        for kind in ('F','G'):
            d=self.s.materialize();ids=[i for i,e in d['entities'].items() if e['type']==kind]
            self.s.decide({'revision':self.s.revision(),'action':'merge','ids':ids,'target_id':ids[0],'type':kind,'name':d['entities'][ids[0]]['canonical_name']})
        d=self.s.snapshot(self.s.seal_direct())
        self.assertEqual(len(d['relations']),1);self.assertEqual(len(d['assertions']),2);self.assertTrue(d['conflicts'])
    def test_source_overlap_rejected(self):
        self.s.ingest(payload(),provenance={'source_document_ids':['S1','S2']})
        with self.assertRaisesRegex(ValueError,'SOURCE_OVERLAP'):self.s.ingest(payload('D2'),provenance={'source_document_ids':['S2']})
    def test_normalization_preserves_accents_numbers(self):
        self.s.ingest(payload(entities=[entity('  Á  A ',eid='E1'),entity('á a',eid='E2'),entity('a a',eid='E3'),entity('A 2023',eid='E4'),entity('A 2024',eid='E5')]))
        self.assertEqual(len(self.s.materialize()['entities']),5)
        self.assertTrue(self.s.lookup_term('á   a','F')['ambiguous'])
        self.assertFalse(self.s.lookup_term('a a','F')['ambiguous'])
    def test_source_names_preserved_independent_of_declaration_order(self):
        es=[entity('C',['B'],eid='E3'),entity('B',['A'],eid='E2'),entity('A',eid='E1')]
        self.s.ingest(payload(entities=es));d=self.s.materialize()
        self.assertEqual({local:d['entities'][gid]['canonical_name'] for local,gid in d['entity_mapping']['D1']['ids'].items()},{'E1':'A','E2':'B','E3':'C'})

    def test_missing_sentence_rejected_before_mutation(self):
        p=payload(relation=True);p['propositions'][0]['evidence'][0]['sentence_id']='MISSING'
        with self.assertRaises(ValueError):self.s.ingest(p)
        self.assertFalse(self.s.materialize()['documents'])
    def test_unique_terms_constraint(self):
        import sqlite3
        self.s.ingest(payload());row=self.s.db.execute('SELECT * FROM exact_terms LIMIT 1').fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.s.write():self.s.db.execute('INSERT INTO exact_terms VALUES(?,?,?)',tuple(row))
    def test_concurrent_connections_keep_source_identities_separate(self):
        barrier=threading.Barrier(2);errors=[]
        def f(doc):
            s=ExactStore(self.s.path,Ontology.from_dict(ONTOLOGY),Limits())
            try:barrier.wait();s.ingest(payload(doc))
            except Exception as e:errors.append(e)
            finally:s.db.close()
        ts=[threading.Thread(target=f,args=(d,)) for d in ('D1','D2')]
        for t in ts:t.start()
        for t in ts:t.join(10)
        self.assertFalse(errors);self.assertFalse(any(t.is_alive() for t in ts));self.assertEqual(len(self.s.materialize()['entities']),2)
    def test_failure_does_not_activate_then_retry(self):
        class Failing:
            def __init__(self,store,settings):self.s=store;assert settings.entity_embedding.enabled is False
            def sync(self,sid):self.s.progress(sid,'failed',{});raise RuntimeError('injected')
        class Passing(Failing):
            def sync(self,sid):mark_verified(self.s,sid)
        with self.assertRaises(RuntimeError):process(payload(),{},'kg',store=self.s,publisher_factory=Failing)
        self.assertIsNone(self.s.active())
        result=process(payload(),{},'kg',store=self.s,publisher_factory=Passing)
        self.assertEqual(result['status'],'completed');self.assertIsNotNone(self.s.active());self.assertEqual(self.s.db.execute('SELECT count(*) FROM documents').fetchone()[0],1)
    def test_rag_failure_does_not_undo_completed_kg(self):
        class Passing:
            def __init__(self,s,settings):self.s=s
            def sync(self,sid):mark_verified(self.s,sid)
        result=process(payload(),{},'both',store=self.s,publisher_factory=Passing)
        self.assertEqual(result['status'],'partial');self.assertIsNotNone(self.s.active())
    def test_ontology_mismatch(self):
        with self.assertRaises(ValueError):verify_ontology(self.s,{'ontology':{'entity_types':['Other'],'relation_types':{'X':{}}}})
    def test_source_provenance_not_invented(self):
        p=payload(relation=True);prov={'sentences':{'S1':{'source_document_id':'SOURCE','source_line':5}}}
        self.s.ingest(p,provenance=prov);d=self.s.materialize()
        self.assertEqual(next(iter(d['evidence'].values()))['source_origin']['source_line'],5)
        self.assertTrue(all(a['declaration_only'] for a in d['alias_sources']))

class PackageTests(unittest.TestCase):
    def zip(self,files):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            for n,v in files.items():z.writestr(n,json.dumps(v) if not isinstance(v,str) else v)
        return b.getvalue()
    def test_review_file_rejected(self):
        with self.assertRaises(ValueError):load_package(b'{}','kg_review.json')
    def test_zip_traversal_rejected(self):
        with self.assertRaises(ValueError):load_package(self.zip({'../kg_import.json':payload()}),'x.zip','single')
    def test_missing_merged_mapping_rejected(self):
        with self.assertRaises(ValueError):load_package(self.zip({'kg_merged.json':payload()}),'x.zip','merged')
    def merged_files(self):
        return {'kg_merged.json':payload(),'cumulative_source_mapping.json':{'merged_document_id':'D1','sources':[{'document_id':'SRC'}],'sentences':[{'merged_sentence_id':'S1','source_document_id':'SRC','source_sentence_id':'ORIGINAL'}]},'entity_mapping.json':{'merged_document_id':'D1','entity_mappings':[{'merged_id':'E1','sources':[{'document_id':'SRC','entity_id':'LOCAL'}]}]},'alias_evidence.json':[{'alias':'B','source_line':5}]}
    def test_merged_package_preserves_entity_and_alias_sources(self):
        files=self.merged_files();raw,prov=load_package(self.zip(files),'x.zip','merged')
        self.assertEqual(prov['entity_mapping'],files['entity_mapping.json']);self.assertEqual(prov['alias_evidence'],files['alias_evidence.json'])
    def test_missing_entity_mapping_coverage_rejected(self):
        files=self.merged_files();files['entity_mapping.json']['entity_mappings']=[]
        with self.assertRaisesRegex(ValueError,'bao phủ'):load_package(self.zip(files),'x.zip','merged')
    def test_source_entity_cannot_map_to_two_targets(self):
        files=self.merged_files();files['kg_merged.json']['entities'].append(entity('X',eid='E2'))
        files['entity_mapping.json']['entity_mappings'].append({'merged_id':'E2','sources':[{'document_id':'SRC','entity_id':'LOCAL'}]})
        with self.assertRaisesRegex(ValueError,'nhiều ánh xạ'):load_package(self.zip(files),'x.zip','merged')
    def test_zip_does_not_execute_scripts_or_read_review(self):
        raw,prov=load_package(self.zip({'x/kg_import.json':payload(),'x/build.py':'raise Exception()','x/kg_review.json':{'bad':True}}),'x.zip','single')
        self.assertEqual(raw,payload())
    def test_rag_origin_copy_preserves_input(self):
        p=payload();original=copy.deepcopy(p);out=rag_payload(p,{'sentences':{'S1':{'source_document_id':'D','source_line':4}}})
        self.assertEqual(p,original);self.assertEqual(out['document']['sections'][0]['paragraphs'][0]['sentences'][0]['source_origin']['source_line'],4)
    def test_line_hash_contract(self):
        import hashlib
        text='Original sentence.';h=hashlib.sha256(text.encode()).hexdigest()
        rows=[{'document_id':'D1','sentence_id':'S1','source_file':'D1.md','source_line':2,'source_sha256':h}]
        b=self.zip({'kg_import.json':payload(),'source_mapping.json':rows,'D1.md':'title\n'+text+'\n'})
        raw,p=load_package(b,'x.zip','single');self.assertEqual(p['sentences']['S1']['source_hash_scope'],'line')
    def test_wrong_source_line_hash_rejected(self):
        rows=[{'document_id':'D1','sentence_id':'S1','source_file':'D1.md','source_line':1,'source_sha256':'wrong'}]
        with self.assertRaises(ValueError):load_package(self.zip({'kg_import.json':payload(),'source_mapping.json':rows,'D1.md':'text'}),'x.zip','single')
    def test_missing_declared_source_file_rejected(self):
        rows=[{'document_id':'D1','sentence_id':'S1','source_file':'missing.md','source_line':1}]
        with self.assertRaisesRegex(ValueError,'Thiếu file nguồn'):load_package(self.zip({'kg_import.json':payload(),'source_mapping.json':rows}),'x.zip','single')

class RagTests(unittest.TestCase):
    def setUp(self):
        from app.modules.rag.core import DemoEncoder,ChunkConfig
        from app.modules.rag.storage import DemoStore
        from app.modules.rag.service import Service
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.rag=Service(DemoStore(str(pathlib.Path(self.tmp.name)/'rag.db')),DemoEncoder(),ChunkConfig(target=100,overlap=10,method='token'),'demo');self.addCleanup(self.rag.store.close)
    def test_rag_all_sentences_and_source_origin_preserved(self):
        p=payload(relation=True);p['document']['sections'][0]['paragraphs'][0]['sentences'].append({'sentence_id':'S2','text':'Not extracted into a proposition.'})
        out=rag_payload(p,{'source_document_ids':['SRC'],'sentences':{'S1':{'source_document_id':'SRC','source_sentence_id':'ORIG','source_line':99}}})
        result=self.rag.import_data(out);self.assertTrue(result['ok']);d=self.rag.store.get('D1');rows=self.rag.store.records(d['active_revision'])
        chunks=[r for r in rows if r['kind']=='chunk'];self.assertIn('Not extracted',chunks[0]['text']);self.assertEqual(chunks[0]['source_origins'][0]['source_line'],99)
        self.assertEqual(self.rag.import_data(out)['status'],'skipped')
    def test_long_proposition_split_preserves_full_text(self):
        p=payload(relation=True);text=' '.join(['word']*700)
        p['propositions'][0]['text']=text;p['document']['sections'][0]['paragraphs'][0]['sentences'][0]['text']=text
        self.rag.import_data(p);d=self.rag.store.get('D1')
        rows=[r for r in self.rag.store.records(d['active_revision']) if r['kind']=='proposition']
        self.assertGreater(len(rows),1)
        self.assertTrue(all(r['proposition_id']=='P1' for r in rows))
        coverage=set()
        for row in rows:
            a,b=row['proposition_start_char'],row['proposition_end_char'];self.assertEqual(text[a:b],row['text']);coverage.update(range(a,b))
        self.assertEqual(coverage,set(range(len(text))))
    def test_rag_source_overlap_blocked(self):
        self.rag.import_data(rag_payload(payload(),{'source_document_ids':['SOURCE']}))
        with self.assertRaisesRegex(ValueError,'SOURCE_OVERLAP'):self.rag.import_data(rag_payload(payload('D2'),{'source_document_ids':['SOURCE']}))
    def test_rag_embedding_failure_keeps_previous_active(self):
        p=payload();self.rag.import_data(p);old=self.rag.store.get('D1')['active_revision'];p['document']['title']='Changed'
        with patch.object(self.rag.encoder,'encode',side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):self.rag.import_data(p)
        self.assertEqual(self.rag.store.get('D1')['active_revision'],old)

class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import app.direct_import.api as api
        self.api=api;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=pathlib.Path(self.tmp.name)/'g.sqlite'
        def factory():return ExactStore(self.path,Ontology.from_dict(ONTOLOGY),Limits())
        p=patch.object(api,'configured_store',factory);p.start();self.addCleanup(p.stop)
        app=FastAPI();app.include_router(api.create_router());app.add_middleware(api.LegacyImportGuard)
        self.client=TestClient(app)
    def test_new_ui_and_retired_routes(self):
        self.assertEqual(self.client.get('/direct-import').status_code,200)
        for path in ('/modules/kg/api/v1/kg/import-json','/api/v1/kg-global/scan','/modules/kg-explorer/api/review/import'):
            self.assertEqual(self.client.post(path,json=payload()).status_code,410)
    def test_invalid_upload_reports_json_error(self):
        r=self.client.post('/api/v1/direct-import?filename=x.json',content=b'{bad');self.assertEqual(r.status_code,422)
    def test_job_progress_is_durable(self):
        self.api.write_job('job','running',{'stage':'databases','snapshot_id':'S_X'});self.api.write_job('job','failed',{'error':'Test'})
        r=self.client.get('/api/v1/direct-import/jobs/job').json();self.assertEqual(r['snapshot_id'],'S_X');self.assertEqual(r['status'],'failed');self.assertIn('started_at',r)
    def test_source_lookup_only_published_snapshot(self):
        s=self.api.configured_store()
        try:
            s.ingest(payload());sid=s.seal_direct()
            self.assertEqual(self.client.get('/api/v1/direct-import/source/D1/E1').json(),[])
            mark_verified(s,sid);s.activate(sid)
            before=self.client.get('/api/v1/direct-import/source/D1/E1').json()
            s.ingest(payload(entities=[entity('Different')]))
            self.assertEqual(self.client.get('/api/v1/direct-import/source/D1/E1').json(),before)
            self.assertEqual(before[0]['version'],1)
        finally:s.db.close()
    def test_identity_api_is_revision_guarded_and_keeps_active_snapshot_immutable(self):
        s=self.api.configured_store()
        try:
            s.ingest(payload(entities=[entity('A',['Shared']),entity('B',['Shared'],eid='E2')]))
            sid=s.seal_direct();mark_verified(s,sid);s.activate(sid);published=s.snapshot(sid)
            data=self.client.get('/api/v1/direct-import/identity').json()
            self.assertEqual(len(data['ambiguous_terms']),1)
            gid=published['entity_mapping']['D1']['ids']['E1']
            body={'action':'alias','revision':data['revision'],'entity_id':gid,'term':'Shared','status':'rejected','reason':'Reviewed'}
            self.assertEqual(self.client.post('/api/v1/direct-import/identity',json=body).status_code,200)
            self.assertEqual(self.client.post('/api/v1/direct-import/identity',json=body).status_code,409)
            self.assertEqual(s.snapshot(sid),published);self.assertEqual(s.active()['id'],sid)
        finally:s.db.close()
    def test_http_upload_end_to_end_without_live_databases(self):
        api=self.api
        def run(raw,prov,target,rag,progress):
            progress('identity',{});return {'status':'completed','results':{'kg':{'status':'completed'}}}
        with patch.object(api,'process',run):
            r=self.client.post('/api/v1/direct-import?filename=x.json&target=kg',content=json.dumps(payload()));self.assertEqual(r.status_code,202)
            api.POOL.submit(lambda:None).result(timeout=10)
            result=self.client.get('/api/v1/direct-import/jobs/'+r.json()['id']).json();self.assertEqual(result['status'],'completed')

if __name__=='__main__':unittest.main()
