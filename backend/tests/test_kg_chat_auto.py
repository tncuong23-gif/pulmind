"""Synthetic graphs and mocked model responses, not medical claims."""
from unittest.mock import AsyncMock,Mock
import pytest
from app.modules.kg_query.auto_plan import AUTO_EXAMPLES,catalog,routing_hint
from app.modules.kg_query.intents import PRESET_CHAINS
from app.modules.kg_query.question_analysis import text_key
from app.modules.kg_query.retrieval_api import QueryRequest,retrieve,create_app
from app.services.modules import ModuleClient
from app.services.orchestrator import Orchestrator
from tests.test_kg_compact_queries import Graph,taxonomy

@pytest.mark.parametrize('preset',list(PRESET_CHAINS))
@pytest.mark.parametrize('unaccented',[False,True])
def test_all_presets(preset,unaccented):
 g=Graph();g.node('A');q=AUTO_EXAMPLES[preset].format(name='Test A')
 if unaccented:q=text_key(q,accents=False)
 r=retrieve(g.service(),QueryRequest(question=q)).model_dump()
 assert r['query']['mode']=='multi_hop' and r['query']['preset']==preset,r
 assert r['status']=='no_facts' and routing_hint(q)

@pytest.mark.parametrize('question,preset',[
 ('Xét nghiệm cho Test A lấy mẫu gì?','diagnostic_specimens'),('Thứ tự điều trị Test A trong phác đồ?','treatment_sequence'),
 ('Phòng ngừa Test A áp dụng trong bối cảnh nào?','prevention_settings'),('Khuyến nghị về Test A áp dụng cho ai?','recommendation_conditions'),
 ('Vi khuẩn gây Test A kháng kháng sinh nào?','pathogen_resistance')])
def test_paraphrases(question,preset):
 g=Graph();g.node('A');assert retrieve(g.service(),QueryRequest(question=question)).query['preset']==preset

@pytest.mark.parametrize('question',[
 'Thuốc trong phác đồ Test A có liều dùng và tác dụng phụ nào?','Xét nghiệm Test A cần bệnh phẩm và đo đại lượng nào?',
 'Suy luận nguyên nhân của Test A','Suy luận phân loại và bộ phận giải phẫu cho Test A','Thuốc điều trị Test A không gây tác dụng phụ nào?'])
def test_ambiguity_asks_before_edge_reads(question):
 s=taxonomy().service();r=retrieve(s,QueryRequest(question=question)).model_dump()
 assert r['status']=='needs_clarification' and r['clarification']['reason']=='query_scope'
 assert not r['llm_context']['facts'] and not r['clarification']['can_confirm'] and len(s.driver.log)==1

@pytest.mark.parametrize('name',['Bệnh phác đồ suy luận phân loại','Bệnh tương đồng thử nghiệm'])
def test_name_is_not_operation(name):
 g=Graph();g.node('A');g.entities['A'].update(canonical_name=name,normalized_name=name.lower())
 r=retrieve(g.service(),QueryRequest(question=name+' có triệu chứng gì?')).model_dump()
 assert r['query']['mode']=='one_hop' and r['query']['intents']==['symptom']

def setup_chat(g,label='GENERAL_MEDICAL_QUERY'):
 m=ModuleClient(context_url='http://c',clinical_url='http://ie',kg_url='http://kg',rag_url='http://r',timeout=5,embedded_apps={'http://kg':create_app(g.service())})
 m.context_resolve=AsyncMock(return_value={'resolution_status':'resolved','active_topic':{'canonical_name':'Test A'}});m.rag_search=AsyncMock(return_value={'results':[]})
 classifier=Mock();classifier.predict.return_value={'label':label,'class_id':'original'}
 llm=AsyncMock();llm.generate.return_value='Kết quả thử [1].'
 return Orchestrator(classifier,m,llm),m,llm
async def chat(o,q):return await o.answer(question=q,conversation_id='c',message_id='m',timestamp='now',attachments=[])

@pytest.mark.asyncio
async def test_inference_ui_matches_llm():
 o,m,llm=setup_chat(taxonomy());r=await chat(o,'Suy luận phân loại cho Test A')
 assert r['classifier']['original_label']=='GENERAL_MEDICAL_QUERY' and r['classifier']['routing_override']=='kg_inference_cue'
 assert r['kg_query']['mode']=='inference'
 p=r['kg_evidence']['inferences'][0];assert len(p['premises'])==2 and p['kind']=='inferred'
 assert all(set(x['source_refs'])<={s['number'] for s in r['sources']} for x in p['premises'])
 assert r['kg_evidence']==llm.generate.call_args.args[1]['module_results']['kg'];m.rag_search.assert_not_awaited()

@pytest.mark.asyncio
async def test_chain_routing():
 g=Graph();g.node('A');g.node('B','TreatmentRegimen');g.node('C','Medication');g.edge('A','HAS_REGIMEN','B');g.edge('B','USES_MEDICATION','C')
 o,m,llm=setup_chat(g);r=await chat(o,'Phác đồ của Test A gồm những thuốc nào?')
 assert r['kg_query']['preset']=='regimen_medications' and r['kg_evidence']['chains'][0]['fact_indices']==[0,1];m.rag_search.assert_not_awaited()

@pytest.mark.asyncio
async def test_empty_inference_rag_is_separate():
 g=Graph();g.node('A');o,m,llm=setup_chat(g);m.rag_search.return_value={'results':[{'text':'Nguồn bổ sung thử nghiệm','document_id':'RAG'}]}
 r=await chat(o,'Suy luận phân loại cho Test A');assert r['kg_evidence'] is None and r['retrieval_routing']['kg_evidence']=='empty'
 assert any('không thay thế' in w for w in r['warnings']) and 'kg' not in llm.generate.call_args.args[1]['module_results']

@pytest.mark.asyncio
async def test_ambiguous_no_llm():
 o,m,llm=setup_chat(taxonomy());r=await chat(o,'Suy luận phân loại và giải phẫu cho Test A')
 assert r['route']=='NEEDS_CLARIFICATION' and r['kg_clarification']['suggestions'];llm.generate.assert_not_awaited();m.rag_search.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('label',['DIAGNOSTIC_ASSESSMENT','OUT_OF_SCOPE'])
async def test_preserves_gates(label):
 o,m,llm=setup_chat(taxonomy(),label);r=await chat(o,'Suy luận phân loại cho Test A');assert r['route']==label;llm.generate.assert_not_awaited();m.rag_search.assert_not_awaited()

@pytest.mark.asyncio
async def test_explanation_uses_both():
 o,m,llm=setup_chat(taxonomy());r=await chat(o,'Giải thích suy luận phân loại cho Test A')
 assert r['classifier']['label']=='CLINICAL_EXPLANATION_MANAGEMENT' and r['kg_evidence']['inferences'];m.rag_search.assert_awaited_once()

def test_catalog():
 assert {r['preset'] for r in catalog()}==set(PRESET_CHAINS) and routing_hint('Test A là gì?') is None

@pytest.mark.asyncio
async def test_missing_entity_asks():
 o,m,llm=setup_chat(Graph());r=await chat(o,'Suy luận phân loại cho UNKNOWN')
 assert r['route']=='NEEDS_CLARIFICATION';m.rag_search.assert_not_awaited();llm.generate.assert_not_awaited()

def test_meta():
 from fastapi.testclient import TestClient
 with TestClient(create_app(taxonomy().service())) as c:
  r=c.get('/api/v1/kg/meta').json();assert len(r['automatic_presets'])==19 and r['planner']=='dictionary_and_rules_v2'
