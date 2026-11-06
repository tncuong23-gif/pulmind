from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.kg_query.concept_groups import catalog, snapshot_groups
from app.modules.kg_query.retrieval_api import create_app
from app.services.modules import ModuleClient
from app.services.orchestrator import Orchestrator
from tests.test_kg_chat_query import fixture_service, query


@pytest.fixture
def grouped():
    service = fixture_service()
    graph = service.driver.g
    graph.entities['D4'].update(canonical_name='COPD', normalized_name='copd', entity_type='DiseaseSubtype', aliases=['Thể COPD thử'])
    graph.rels.append({**graph.rels[1], 'id':'R-subtype', 'source':'D4'})
    members = [{'id':i, 'name':'COPD', 'type':graph.entities[i]['entity_type']} for i in ('D1','D4')]
    service.concept_groups = {row['id']:members for row in members}
    return service


def test_snapshot_policy_requires_document_identity_and_all_members():
    policy = catalog()
    entry = next(row for row in policy['groups'] if row['name']=='Lao phổi')
    doc = next(iter(policy['documents']))
    mapping = {local:f'GE_{local}' for local in entry['members']}
    snapshot = {'documents':{k:{'hash':v} for k,v in policy['documents'].items()},
                'entity_mapping':{doc:{'ids':mapping}},
                'entities':{mapping[i]:{'type':kind,'canonical_name':entry['name']} for i,kind in entry['members'].items()},
                'relations':{'r':dict(zip(('source','target'),mapping.values()))}}
    assert len(snapshot_groups(snapshot)) == 2
    snapshot['documents'][doc]['hash'] = 'other dataset'
    assert snapshot_groups(snapshot) == {}


def test_grouped_lookup_includes_sources_and_confirmation(grouped):
    for request in ({}, {'entity_ids':['D4']}):
        result = query(grouped,'COPD có triệu chứng gì?', **request)
        assert result['status']=='ok' and result['clarification'] is None
        facts = result['llm_context']['facts']
        assert {row['subject']['id'] for row in facts} == {'D1','D4'}
        assert {ev['evidence_id'] for row in facts for ev in row['evidence']} == {'E1','E2'}
    result = query(grouped,'Bệnh đó có những triệu chứng nào?',context_mentions=['COPD'])
    assert result['status']=='ok' and len(result['llm_context']['facts'])==2


def test_other_candidate_keeps_ambiguity(grouped):
    grouped.driver.g.entities['D2']['aliases'].append('COPD')
    result = query(grouped,'COPD có triệu chứng gì?')
    assert result['status']=='needs_clarification'
    assert {row['id'] for row in result['clarification']['groups'][0]['candidates']}=={'D1','D2','D4'}


def test_comparison_preserves_both_sides_and_rejects_same_concept(grouped):
    result = query(grouped,'So sánh triệu chứng COPD và Viêm phổi')
    comparison = result['llm_context']['comparison']
    assert len(comparison['entities'])==2
    assert {f['subject']['id'] for f in result['llm_context']['facts']}=={'D1','D2','D4'}
    result = query(grouped,'So sánh triệu chứng COPD và Thể COPD thử',
                   mentions=['COPD','Thể COPD thử'])
    assert result['status']=='needs_clarification'
    assert result['clarification']['reason']=='query_scope'


@pytest.mark.asyncio
async def test_chat_keeps_group_and_citations_through_http_and_evidence(grouped):
    modules = ModuleClient(context_url='http://c',clinical_url='http://ie',kg_url='http://kg',rag_url='http://r',
                           timeout=5,embedded_apps={'http://kg':create_app(grouped)})
    modules.context_resolve = AsyncMock(return_value={'resolution_status':'resolved',
                                                       'normalized_question':'COPD có triệu chứng nào?'})
    modules.rag_search = AsyncMock()
    classifier = Mock()
    classifier.predict.return_value = {'label':'RELATIONAL_QUERY'}
    llm = AsyncMock()
    llm.generate.return_value = 'Thông tin thử [1] [2].'
    result = await Orchestrator(classifier, modules, llm).answer(
        conversation_id='demo',message_id='demo',question='Bệnh đó có triệu chứng nào?',timestamp='now',attachments=[])
    assert result['route']=='RELATIONAL_QUERY'
    assert len(result['kg_query']['concept_groups'][0]['members'])==2
    evidence = llm.generate.call_args.args[1]['module_results']['kg']
    assert evidence['concept_groups']==[{'name':'COPD','member_types':['Disease','DiseaseSubtype']}]
    assert len(evidence['facts'])==1
    assert {ref for f in evidence['facts'] for ref in f['source_refs']}=={1,2}
    assert '[1] [2]' in result['content']
    modules.rag_search.assert_not_awaited()
