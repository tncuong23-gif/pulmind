import asyncio,json
import pytest
from fastapi.testclient import TestClient
from app.modules.kg_query.web_app import create_app
from app.bulk_import.kg import KGAdapter
from app.bulk_import.manager import BatchManager
from tests import test_manual_merge as merge_tests

@pytest.fixture
def case():
    c=merge_tests.MergeTests();c.setUp();return c

def test_http_preview_confirmation_and_replay(case):
    client=TestClient(create_app(import_service=case.svc))
    p=case.merge_payload()
    assert 'Disease' in client.get('/api/review/merge/types').json()['types']
    q=client.post('/api/review/merge',json={'operation':'preview','payload':p,'choice':case.choice()})
    assert q.status_code==200 and q.json()['can_apply']
    assert not case.graph.entities
    body={'operation':'apply','payload':p,'token':q.json()['token']}
    assert client.post('/api/review/merge',json=body).status_code==409
    body['confirmed']=True
    out=client.post('/api/review/merge',json=body)
    assert out.status_code==200 and out.json()['canonical_id']=='A'
    assert client.post('/api/review/merge',json=body).status_code==409

@pytest.mark.asyncio
async def test_batch_merge_review_commit_and_old_file(case,tmp_path):
    m=BatchManager('kg',KGAdapter(lambda:case.svc),tmp_path/'input',tmp_path/'reports')
    try:
        p=case.merge_payload();m.upload('one.json',json.dumps(p).encode())
        job=m.start();await asyncio.wait_for(m.task,5);jid=job['job_id']
        q=await m.merge_concepts(jid,0,{'operation':'preview','choice':case.choice('ClinicalFinding')})
        assert q['can_apply'] and not case.graph.entities
        await m.merge_concepts(jid,0,{'operation':'apply','token':q['token'],'confirmed':True})
        review=await m.review(jid,0)
        assert len(review['entities'])==1 and review['entities'][0]['type']=='ClinicalFinding'
        await m.decisions(jid,0,{})
        commit=m.start(mode='commit',previous_job_id=jid,confirmed=True)
        await asyncio.wait_for(m.task,5)
        assert m.get(commit['job_id'])['completed']==1
        # Original uploaded IDs must resolve to the chosen type on later imports.
        p['document']['document_id']='D_NEW'
        result=case.svc.import_kg(p)
        assert result.status=='completed',result.errors
        assert set(case.graph.entities)=={'A'}
        assert case.graph.entities['A']['entity_type']=='ClinicalFinding'
    finally:await m.close()
