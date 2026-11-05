"""Regression tests for reviewed identity and fail-closed triple publication."""
import copy
import json
import pytest
from app.direct_import.store import ExactStore
from app.kg_global.projection import build_projection, verify_projection
from app.modules.kg_import.config import Limits
from app.modules.kg_import.ontology import Ontology
from tests.test_direct_import import payload,entity,ONTOLOGY,mark_verified

@pytest.fixture
def store(tmp_path):
    s=ExactStore(tmp_path/'g.sqlite',Ontology.from_dict(ONTOLOGY),Limits())
    yield s
    s.db.close()

class Result(list):
    def single(self):return self[0]

class ProjectionReader:
    def __init__(self,projection):
        self.nodes=copy.deepcopy(projection['nodes']);self.edges=copy.deepcopy(projection['edges']);self.terms=0;self.foreign=0;self.isolated=0
    def run(self,q):
        if 'properties(n)' in q:return Result({'node':r} for r in self.nodes.values())
        if 'r.global_assertions AS assertions' in q:return Result(self.edges.values())
        if 'RETURN count(r)' in q:return Result([{'count':self.foreign}])
        if 'WHERE NOT (n)--()' in q:return Result([{'count':self.isolated}])
        if 'RETURN count(n)' in q:return Result([{'count':self.terms}])
        raise AssertionError(q)

def fixture_projection(store):
    raw=payload(relation=True);raw['entities'].append(entity('Orphan',eid='E3'))
    store.ingest(raw)
    return build_projection(store.snapshot(store.seal_direct()))

def test_projection_filters_only_nodes_keeps_source_and_assertions(store):
    projection=fixture_projection(store);data=store.materialize()
    assert len(data['entities'])==3 and len(projection['nodes'])==2
    assert projection['counts']['isolated_source_entities']==1
    edge=next(iter(projection['edges'].values()));assertions=json.loads(edge['assertions'])
    assert assertions[0]['assertion_id'] in data['assertions']
    assert assertions[0]['document_version']==1
    assert assertions[0]['proposition_ids']==['P1']
    assert assertions[0]['evidence_ids']==next(iter(data['assertions'].values()))['evidence_ids']
    assert verify_projection(ProjectionReader(projection),'KGGlobal_S_'+'a'*32,projection)['verified']

@pytest.mark.parametrize('damage',['missing_edge','wrong_endpoint','wrong_type','lost_evidence','extra_node','duplicate_edge','term','wrong_name','wrong_alias','foreign_endpoint','isolated_node'])
def test_verify_rejects_missing_or_corrupt_graph(store,damage):
    p=fixture_projection(store);tx=ProjectionReader(p);edge=next(iter(tx.edges.values()));node=next(iter(tx.nodes.values()))
    if damage=='missing_edge':tx.edges.clear()
    if damage=='wrong_endpoint':edge['t']='MISSING'
    if damage=='wrong_type':edge['type']='DENOTES'
    if damage=='lost_evidence':edge['assertions']='[]'
    if damage=='extra_node':tx.nodes['orphan']={'id':'orphan'}
    if damage=='duplicate_edge':tx.edges['copy']=dict(edge)
    if damage=='term':tx.terms=1
    if damage=='foreign_endpoint':tx.foreign=1
    if damage=='isolated_node':tx.isolated=1
    if damage=='wrong_name':node['canonical_name']='Wrong'
    if damage=='wrong_alias':node['aliases']=['Wrong']
    with pytest.raises(ValueError,match='VERIFY_'):verify_projection(tx,'KGGlobal_S_'+'a'*32,p)

@pytest.mark.parametrize('damage',['endpoint','ontology','assertion','evidence','self_loop'])
def test_invalid_snapshot_fails_before_database_writes(store,damage):
    store.ingest(payload(relation=True));data=store.materialize();r=next(iter(data['relations'].values()))
    if damage=='endpoint':r['source']='missing'
    if damage=='ontology':r['type']='UNKNOWN'
    if damage=='assertion':r['assertion_ids']=[]
    if damage=='evidence':data['evidence'].clear()
    if damage=='self_loop':r['target']=r['source']
    with pytest.raises(ValueError,match='PROJECTION_'):build_projection(data)

def test_unverified_ready_cannot_replace_active_snapshot(store):
    store.ingest(payload(relation=True));old=store.seal_direct();mark_verified(store,old);store.activate(old)
    store.ingest(payload('D2',relation=True));new=store.seal_direct()
    store.progress(new,'ready',{})
    with pytest.raises(ValueError,match='xác minh'):store.activate(new)
    assert store.active()['id']==old

def test_source_update_removes_old_alias_but_retains_history_and_identity(store):
    raw=payload();store.ingest(raw);before=store.materialize();gid=before['entity_mapping']['D1']['ids']['E1']
    raw['entities'][0]['aliases']=['New'];store.ingest(raw);data=store.materialize()
    assert data['entity_mapping']['D1']['ids']['E1']==gid
    assert data['entities'][gid]['aliases']==['New']
    assert not store.lookup_term('B')['candidates']
    assert any(a['term']=='B' and a['status']=='inactive' for a in data['alias_sources'])

def test_reviewed_merge_keeps_original_mapping_and_name_across_update(store):
    store.ingest(payload('D1',[entity('A',['Shared'])]));store.ingest(payload('D2',[entity('B',['Shared'])]))
    data=store.materialize();ids=list(data['entities']);old=dict(store.db.execute("SELECT local,gid FROM mappings WHERE doc='D2'").fetchone())
    store.decide({'revision':store.revision(),'action':'merge','ids':ids,'target_id':ids[0],'name':'Reviewed','type':'F'})
    raw=payload('D1',[entity('A',['Changed'])]);store.ingest(raw);data=store.materialize()
    assert list(data['entities'].values())[0]['canonical_name']=='Reviewed'
    assert dict(store.db.execute("SELECT local,gid FROM mappings WHERE doc='D2'").fetchone())==old
    assert data['entity_mapping']['D1']['ids']['E1']==data['entity_mapping']['D2']['ids']['E1']
    assert 'Shared' in list(data['entities'].values())[0]['aliases'] # D2 still supports it
    store.withdraw('D2',store.revision())
    assert 'Shared' not in list(store.materialize()['entities'].values())[0]['aliases']

def test_distinct_blocks_bridge_merge(store):
    store.ingest(payload(entities=[entity('A',['B']),entity('B',eid='E2'),entity('C',['B'],eid='E3')]))
    ids=list(store.materialize()['entities'])
    store.decide({'revision':store.revision(),'action':'distinct','ids':ids[:2]})
    before=store.materialize()
    with pytest.raises(ValueError,match='khác nhau'):
        store.decide({'revision':store.revision(),'action':'merge','ids':ids,'target_id':ids[0],'name':'Reviewed','type':'F'})
    assert store.materialize()==before

def test_alias_rejection_and_acceptance_are_audited_and_do_not_merge(store):
    store.ingest(payload(entities=[entity('A',['Shared']),entity('B',['Shared'],eid='E2')]))
    data=store.materialize();gid=data['entity_mapping']['D1']['ids']['E1']
    assert store.lookup_term('Shared')['ambiguous']
    assert store.db.execute("SELECT count(*) FROM exact_term_candidates WHERE term='shared'").fetchone()[0]==2
    assert store.db.execute("SELECT count(*) FROM exact_terms WHERE term='shared'").fetchone()[0]==0
    store.decide_alias({'revision':store.revision(),'entity_id':gid,'term':'Shared','status':'rejected','reason':'Wrong abbreviation'})
    assert not store.lookup_term('Shared')['ambiguous']
    assert len(store.materialize()['entities'])==2
    assert any(a['entity_id']==gid and a['status']=='rejected' for a in store.materialize()['alias_sources'])
    store.decide_alias({'revision':store.revision(),'entity_id':gid,'term':'Shared','status':'accepted','reason':'Reviewed source'})
    assert store.lookup_term('Shared')['ambiguous']
    assert store.db.execute("SELECT count(*) FROM audit WHERE action='alias_decision'").fetchone()[0]==2

def test_direct_snapshot_restore_preserves_provenance_and_alias_decisions(store,tmp_path):
    store.ingest(payload(relation=True),provenance={'sentences':{'S1':{'source_line':7}}})
    gid=store.materialize()['entity_mapping']['D1']['ids']['E1']
    store.decide_alias({'revision':store.revision(),'entity_id':gid,'term':'B','status':'rejected','reason':'Wrong'})
    raw=payload(relation=True);raw['document']['title']='Updated';store.ingest(raw,provenance={'sentences':{'S1':{'source_line':7}}})
    export=store.snapshot(store.seal_direct())
    restored=ExactStore(tmp_path/'restored.sqlite',store.ontology,Limits())
    try:
        restored.restore(export);data=restored.materialize()
        for key in ('entities','entity_mapping','relations','assertions','evidence','alias_sources','alias_decisions','document_history'):
            assert data[key]==export[key],key
    finally:restored.db.close()

def test_rebuild_legacy_registry_is_offline_and_keeps_source_unchanged(store,tmp_path):
    import importlib.util
    from pathlib import Path
    script=Path(__file__).parents[1]/'scripts/kg/rebuild_identity_registry.py'
    spec=importlib.util.spec_from_file_location('rebuild_registry',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    store.ingest(payload(entities=[entity('A',['B']),entity('B',eid='E2')]))
    data=store.materialize();ids=list(data['entities'])
    store.decide({'revision':store.revision(),'action':'merge','ids':ids,'target_id':ids[0],'name':'Old merged','type':'F'})
    before=store.materialize();target=tmp_path/'new.sqlite'
    result=module.rebuild(store.path,target,store.ontology)
    assert result['active'] is None and result['counts']['source_entities']==2
    assert store.materialize()==before
    with pytest.raises(FileExistsError):module.rebuild(store.path,target,store.ontology)

def test_projection_alias_normalization_uses_import_fold(store):
    from app.modules.kg_import.utils import fold
    raw=payload(entities=[entity('A',['  A\u0301   B  '])],relation=True);store.ingest(raw)
    projection=build_projection(store.materialize());gid=store.materialize()['entity_mapping']['D1']['ids']['E1']
    assert projection['nodes'][gid]['normalized_aliases']==[fold('Á B')]

def test_query_resolution_does_not_expand_alias_siblings_by_default():
    from unittest.mock import Mock
    from app.modules.kg_query.service import KGQueryService
    from app.modules.kg_query import cypher
    service=KGQueryService(Mock(),Ontology.from_dict(ONTOLOGY))
    service._read=Mock(return_value=[{'id':'one','name':'A','type':'F','matched_by':'alias'},
                                    {'id':'two','name':'B','type':'F','matched_by':'exact_name'}])
    anchors=service.resolve('Shared')
    assert len(anchors)==2
    assert service._read.call_count==1
    assert service._read.call_args.args[0]==cypher.RESOLVE_EXACT
    assert 'normalized_aliases' in cypher.RESOLVE_EXACT

def test_distinct_decision_survives_a_merge_with_a_third_entity(store):
    store.ingest(payload(entities=[entity('A',['Shared']),entity('B',['Shared'],eid='E2'),entity('C',['Shared'],eid='E3')]))
    mapping=store.materialize()['entity_mapping']['D1']['ids'];a,b,c=(mapping[e] for e in ('E1','E2','E3'))
    store.decide({'revision':store.revision(),'action':'distinct','ids':[a,b]})
    store.decide({'revision':store.revision(),'action':'merge','ids':[a,c],'target_id':c,'name':'Reviewed AC','type':'F'})
    with pytest.raises(ValueError,match='khác nhau'):
        store.decide({'revision':store.revision(),'action':'merge','ids':[b,c],'target_id':c,'name':'Invalid ABC','type':'F'})
