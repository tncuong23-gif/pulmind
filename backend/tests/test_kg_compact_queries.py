"""Synthetic graph checks only; examples do not assert medical facts."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.modules.kg_import.ontology import Ontology
from app.modules.kg_import.utils import fold
from app.modules.kg_query.service import KGQueryService,QueryLimits
from app.modules.kg_query.models import QuerySpec,Step,EntityRef,Anchor
from app.modules.kg_query.intents import PRESET_CHAINS,PRESET_START_TYPES,preset_steps,uncovered_relations,build_intents
from app.modules.kg_query.retrieval_api import create_app,QueryRequest,retrieve
from app.modules.kg_query.web_app import create_app as explorer_app
from app.modules.kg_query.question_analysis import detect_intents
from tests.upstream.kg.fake_neo4j import FakeDriver,FakeEvidenceStore

ONTOLOGY=Path(__file__).parents[1]/'examples/kg/kg_ontology.compact.json'
class Graph:
    def __init__(self):self.entities={};self.rels=[];self.evidence={}
    def node(self,i,kind='Disease'):
        self.entities[i]={'id':i,'canonical_name':'Test '+i,'normalized_name':fold('Test '+i),'entity_type':kind,'aliases':[]}
        return i
    def edge(self,a,r,b,doc='SRC',props=None,origin=None):
        i='R'+str(len(self.rels));e='EV'+i
        self.rels.append({'id':i,'source':a,'target':b,'type':r,'doc':doc,'evidence_ids':[e],'props':['P'+i], 'confidence':.9,'properties_json':json.dumps(props or {})})
        self.evidence[(doc,e)]={'evidence_id':e,'text':'Synthetic evidence '+i,'sentence_id':'S'+i,'source_origin':{'source_document_id':origin or doc}}
    def service(self,**kw):return KGQueryService(FakeDriver(self),Ontology.load(ONTOLOGY),evidence_store=FakeEvidenceStore(self),merge_alias_siblings=False,**kw)

def ask(g,**kw):return retrieve(g.service(),QueryRequest(question='Test A',entity_ids=['A'],**kw)).model_dump()

def taxonomy(props=None,doc='SRC',origin=None):
    g=Graph()
    for i in ('A','B','C'):g.node(i)
    g.edge('A','IS_A','B');g.edge('B','IS_A','C',doc=doc,props=props,origin=origin);return g

def test_all_compact_relations_covered():
    o=Ontology.load(ONTOLOGY);assert len(o.entity_types)==74 and len(o.relations)==76
    assert uncovered_relations(o)==[]
    assert all(v.relations for v in build_intents(o).values())

@pytest.mark.parametrize('preset',list(PRESET_CHAINS))
def test_every_preset_executes_ontology_valid_complete_chain(preset):
    g=Graph();s=g.service();o=s.ontology;steps=preset_steps(preset,o)
    current='A';kind=next(t for t in PRESET_START_TYPES[preset] if o.has_entity_type(t));g.node(current,kind)
    def route(kind,index):
        if index==len(steps):return []
        step=steps[index];options=[]
        for rel in step.rel_types:
            spec=o.relations[rel]
            if step.direction in ('auto','out','any') and kind in spec.domain:
                options += [(rel,t,False) for t in sorted(spec.range) if not step.target_types or t in step.target_types]
            if step.direction in ('auto','in','any') and kind in spec.range:
                options += [(rel,t,True) for t in sorted(spec.domain) if not step.target_types or t in step.target_types]
        for rel,target,reverse in options:
            rest=route(target,index+1)
            if rest is not None:return [(rel,target,reverse)]+rest
        if step.include_previous:
            rest=route(kind,index+1)
            if rest is not None:return [None]+rest
        return None
    plan=route(kind,0);assert plan is not None
    for n,item in enumerate(plan,1):
        if item is None:continue
        rel,target,reverse=item;new='N'+str(n);g.node(new,target)
        g.edge(new if reverse else current,rel,current if reverse else new);current=new
    r=ask(g,mode='multi_hop',preset=preset)
    assert r['status']=='ok',r
    assert r['llm_context']['chains']
    assert all(len(c['fact_indices'])>=sum(not step.include_previous for step in steps) for c in r['llm_context']['chains'])
    assert all(f['evidence'] for f in r['llm_context']['facts'])

@pytest.mark.parametrize('cue,intent', [('tầm soát','screening'),('tỷ lệ mắc','epidemiology'),('điều kiện áp dụng','applicability'),('phân loại cha','taxonomy'),('tần suất','dosage')])
def test_new_question_cues(cue,intent):assert intent in detect_intents('Test A '+cue,['Test A'])

def test_regimen_auto_planner():
    g=Graph();g.node('A');g.node('B','TreatmentRegimen');g.node('C','Medication');g.edge('A','HAS_REGIMEN','B');g.edge('B','USES_MEDICATION','C')
    r=retrieve(g.service(),QueryRequest(question='Test A có thuốc trong phác đồ nào?',entity_ids=['A'])).model_dump()
    assert r['query']['preset']=='regimen_medications';assert r['status']=='ok'

def test_structural_inference_keeps_premises_and_no_new_graph_edges():
    g=taxonomy();n=len(g.rels);r=ask(g,mode='inference',inference_rule='is_a_transitive')
    p=r['llm_context']['inferences'][0];assert p['subject']['id']=='A' and p['object']['id']=='C'
    assert p['predicate']=='IS_A' and p['kind']=='inferred' and not p['persisted'];assert len(p['premises'])==2
    assert all(x['support_by_source']['SRC'][0]['evidence']['text'] for x in p['premises']);assert len(g.rels)==n

@pytest.mark.parametrize('props',[{'negated':True},{'negated':'false'},{'population':'adults'},{'condition':'X'},{'status':'hypothesis'}])
def test_no_inference_from_conditional_or_negated_assertions(props):
    r=ask(taxonomy(props=props),mode='inference',inference_rule='is_a_transitive');assert r['status']=='no_facts';assert not r['llm_context']['inferences']

def test_conflicting_assertions_block_inference():
    g=taxonomy();g.edge('B','IS_A','C',props={'negated':True})
    assert ask(g,mode='inference',inference_rule='is_a_transitive')['status']=='no_facts'

def test_different_original_sources_in_merged_document_do_not_count_as_same_source():
    g=taxonomy(origin='OTHER')
    assert ask(g,mode='inference',inference_rule='is_a_transitive')['status']=='no_facts'
    r=ask(g,mode='inference',inference_rule='is_a_transitive',evidence_scope='cross_document')
    assert r['status']=='ok';assert r['llm_context']['inferences'][0]['source_document_ids']==['OTHER','SRC']

def test_missing_source_text_blocks_inference():
    g=taxonomy();g.evidence.clear();assert ask(g,mode='inference',inference_rule='is_a_transitive')['status']=='no_facts'

def test_mixed_taxonomic_families_blocked():
    g=taxonomy();g.entities['C']['entity_type']='DrugClass'
    assert ask(g,mode='inference',inference_rule='is_a_transitive')['status']=='no_facts'

def test_part_of_inference_and_cycle_termination():
    g=Graph()
    for i in ('A','B','C'):g.node(i,'Organ')
    g.edge('A','PART_OF','B');g.edge('B','PART_OF','C');g.edge('C','PART_OF','A')
    r=ask(g,mode='inference',inference_rule='part_of_transitive',max_hops=4)
    assert r['status']=='ok';assert all(p['subject']['id']!=p['object']['id'] for p in r['llm_context']['inferences'])

def test_fact_budget_never_cuts_inference_premises():
    r=ask(taxonomy(),mode='inference',inference_rule='is_a_transitive',limit=1)
    assert r['status']=='no_facts' and r['retrieval']['truncated'];assert not r['llm_context']['inferences']

def test_exact_four_steps_and_incoming_direction():
    g=Graph()
    for i in ('A','B','C','D','E'):g.node(i)
    for a,b in zip('ABCD','BCDE'):g.edge(b,'IS_A',a)
    steps=[{'rel_types':['IS_A'],'direction':'in'}]*4
    r=ask(g,mode='multi_hop',steps=steps);assert r['status']=='ok'
    assert len(r['llm_context']['chains'][0]['fact_indices'])==4
    assert r['llm_context']['facts'][0]['subject']['id']=='B'

def test_missing_required_terminal_step_returns_no_partial_chain():
    g=taxonomy()
    r=ask(g,mode='multi_hop',steps=[{'rel_types':['IS_A'],'direction':'out'}]*3)
    assert r['status']=='no_facts';assert r['llm_context']['chains']==[]

def test_diamond_does_not_splice_branches():
    g=taxonomy();g.node('X');g.node('D');g.edge('A','IS_A','X');g.edge('X','IS_A','D')
    r=ask(g,mode='multi_hop',steps=[{'rel_types':['IS_A'],'direction':'out'}]*2)
    fs=r['llm_context']['facts'];paths=[[fs[i] for i in p['fact_indices']] for p in r['llm_context']['chains']]
    assert len(paths)==2
    assert all(p[0]['object']['id']==p[1]['subject']['id'] for p in paths)

def test_limits_mark_truncation():
    g=taxonomy();g.node('X');g.node('D');g.edge('A','IS_A','X');g.edge('X','IS_A','D')
    s=g.service(limits=QueryLimits(max_chains=1))
    r=retrieve(s,QueryRequest(question='Test A',entity_ids=['A'],mode='multi_hop',steps=[{'rel_types':['IS_A'],'direction':'out'}]*2)).model_dump()
    assert r['retrieval']['truncated'];assert len(r['llm_context']['chains'])==1

@pytest.mark.parametrize('extra',[
 {'mode':'multi_hop','steps':[{'rel_types':['IS_A']}]*5},
 {'mode':'multi_hop','steps':[{'rel_types':['IS_A'],'direction':'evil'}]},
 {'mode':'multi_hop','steps':[{'rel_types':['IS_A` DELETE n']} ]},
 {'mode':'multi_hop','steps':[{'rel_types':['IS_A'],'target_types':['Unknown']}]},
 {'mode':'multi_hop','steps':[{'rel_types':['IS_A']}],'preset':'regimen_medications'},
 {'mode':'inference','inference_rule':'causal_transitive'},
 {'mode':'inference','inference_rule':'is_a_transitive','include_evidence':False},
 {'mode':'inference','inference_rule':'is_a_transitive','max_hops':1},
 {'mode':'path','rel_types':['BOGUS']},
 {'mode':'one_hop','target_types':['BOGUS']},
])
def test_invalid_plans_never_silently_broaden(extra):
    g=taxonomy()
    with TestClient(create_app(g.service())) as c:
        r=c.post('/api/v1/kg/query',json={'question':'Test A','entity_ids':['A','C'] if extra['mode']=='path' else ['A'],**extra})
        assert r.status_code==422,r.text

def test_causal_chain_is_traversal_only():
    g=Graph()
    for i in ('A','B','C'):g.node(i)
    g.edge('A','CAUSES','B');g.edge('B','CAUSES','C')
    r=ask(g,mode='multi_hop',steps=[{'rel_types':['CAUSES'],'direction':'out'}]*2)
    assert r['status']=='ok';assert not r['llm_context'].get('inferences')
    assert not any(f['subject']['id']=='A' and f['object']['id']=='C' for f in r['llm_context']['facts'])

def test_explorer_new_endpoint_and_catalog():
    with TestClient(explorer_app(taxonomy().service())) as c:
        meta=c.get('/api/meta').json();assert len(meta['preset_details'])==19;assert meta['uncovered_relations']==[]
        r=c.post('/api/query-plan',json={'question':'Test A','entity_ids':['A'],'mode':'inference','inference_rule':'is_a_transitive'})
        assert r.status_code==200 and r.json()['status']=='ok'
        page=c.get('/').text
        for mode in ('custom','inference','compare','common','difference'):assert 'data-mode="'+mode+'"' in page


def test_chat_inference_retains_atomic_premises_and_numbered_sources():
    from app.services.retrieval_quality import select_kg_evidence
    from app.services.evidence import prepare_evidence
    r=ask(taxonomy(),mode='inference',inference_rule='is_a_transitive')
    selected,state,_=select_kg_evidence(r)
    assert state=='sufficient'
    pack=prepare_evidence({'module_results':{'kg':selected}})
    kg=pack.payload['module_results']['kg'];proof=kg['inferences'][0]
    assert proof['fact_indices']==[0,1]
    assert all(p['source_refs'] for p in proof['premises'])
    assert len(pack.sources)==2 and proof['kind']=='inferred'
    tiny=prepare_evidence({'module_results':{'kg':selected}},max_bytes=700)
    assert 'kg' not in tiny.payload['module_results'] and not tiny.sources


def test_chat_drops_inference_when_one_premise_loses_evidence():
    from app.services.retrieval_quality import select_kg_evidence
    r=ask(taxonomy(),mode='inference',inference_rule='is_a_transitive')
    r['llm_context']['facts'][1]['evidence']=[]
    selected,state,_=select_kg_evidence(r)
    assert selected is None and state=='empty'


def test_chat_rejects_stale_inference_fact_indices():
    from app.services.evidence import prepare_evidence
    r=ask(taxonomy(),mode='inference',inference_rule='is_a_transitive')
    r['llm_context']['inferences'][0]['fact_indices']=[1,0]
    pack=prepare_evidence({'module_results':{'kg':r}})
    assert 'kg' not in pack.payload['module_results'] and not pack.sources


def test_auto_structural_inference_question():
    r=retrieve(taxonomy().service(),QueryRequest(question='Suy luận phân loại Test A',entity_ids=['A'])).model_dump()
    assert r['query']['mode']=='inference' and r['llm_context']['inferences']


def test_explicit_filter_overrides_automatic_inference_cue():
    r=retrieve(taxonomy().service(),QueryRequest(question='Suy luận phân loại Test A',entity_ids=['A'],target_types=['Disease'])).model_dump()
    assert r['query']['mode']=='one_hop' and not r['llm_context'].get('inferences')


def test_explicit_inference_rule_not_overridden_by_question():
    r=retrieve(taxonomy().service(),QueryRequest(question='Suy luận phân loại Test A',entity_ids=['A'],inference_rule='part_of_transitive')).model_dump()
    assert r['status']=='no_facts' and r['query']['inference_rule']=='part_of_transitive'
