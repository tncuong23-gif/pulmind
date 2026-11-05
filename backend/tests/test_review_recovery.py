import asyncio,json,copy
import pytest
from app.modules.kg_import.manual_merge import manager,resolve_redirects
from app.bulk_import.kg import KGAdapter
from app.bulk_import.manager import BatchManager
from tests import test_manual_merge as fixture

@pytest.fixture
def c():
    c=fixture.MergeTests();c.setUp();return c

def test_merge_preserves_unrelated_decisions_and_redirect_is_idempotent(c):
    p=c.merge_payload();p['entities'].append({'id':'C','type':'Disease','canonical_name':'Other'})
    p['entity_link_decisions']={'A':'new','C':'new'};p['entity_type_decisions']={'A':'distinct','C':'distinct'}
    m=manager(c.svc);q=m.preview(p,c.choice());out=m.apply(p,q['token'])['payload']
    assert out['entity_link_decisions']=={'C':'new'}
    assert out['entity_type_decisions']=={'C':'distinct'}
    resolved=resolve_redirects(p,c.graph)
    assert resolved['entity_link_decisions']=={'C':'new'}
    assert resolve_redirects(resolved,c.graph)==resolved

def test_redirect_link_destination_preserves_decision(c):
    p=c.merge_payload();m=manager(c.svc);q=m.preview(p,c.choice());m.apply(p,q['token'])
    other=c.merge_payload();other['entities']=[{'id':'C','type':'Disease','canonical_name':'Other name'}]
    other['entity_link_decisions']={'C':'B'}
    out=resolve_redirects(other,c.graph)
    assert out['entity_link_decisions']=={'C':'A'}
    assert [e['id'] for e in out['entities']]==['C']

@pytest.mark.asyncio
async def test_graph_changes_after_review_requires_only_supplemental_review(c,tmp_path):
    m=BatchManager('kg',KGAdapter(lambda:c.svc),tmp_path/'in',tmp_path/'reports')
    async def finish(**kw):
        j=m.start(**kw);await asyncio.wait_for(m.task,5);return m.get(j['job_id'])
    try:
        p=c.merge_payload();p['entities']=p['entities'][:1]
        m.upload('one.json',json.dumps(p).encode());j=await finish()
        await m.decisions(j['job_id'],0,{})
        assert (await m.review(j['job_id'],0))['review_status']=='reviewed'
        # A prior document in a sequential import adds a cross-type candidate.
        new=copy.deepcopy(p);new['document']['document_id']='D_OTHER';new['entities']=[{'id':'B','type':'RiskFactor','canonical_name':'Same'}]
        assert c.svc.import_kg(new).status=='completed'
        blocked=await finish(mode='commit',previous_job_id=j['job_id'],confirmed=True)
        row=blocked['items'][0]
        assert row['status']=='needs_review' and row['review_status']=='needs_review'
        assert row['reviewed_at'] is None and 'Same' in row['error'] and row['candidate_count']==1
        assert not c.docs.document_exists(p['document']['document_id'])
        extra=await finish(mode='preview',source='files',files=['one.json'])
        review=await m.review(extra['job_id'],0)
        assert set(review['plan']['entity_candidates'])=={'A'}
        await m.decisions(extra['job_id'],0,{'A':'new'})
        done=await finish(mode='commit',previous_job_id=extra['job_id'],confirmed=True)
        assert done['completed']==1
    finally:await m.close()
