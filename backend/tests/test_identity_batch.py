import pytest

from app.direct_import import identity_batch
from app.direct_import.store import ExactStore
from app.modules.kg_import.config import Limits
from app.modules.kg_import.ontology import Ontology
from tests.test_direct_import import ONTOLOGY, entity, mark_verified, payload


@pytest.fixture
def store(tmp_path):
    registry = ExactStore(tmp_path/'kg.sqlite', Ontology.from_dict(ONTOLOGY), Limits())
    try:
        yield registry
    finally:
        registry.db.close()


def test_batch_merge_keeps_evidence_and_active_snapshot(store):
    store.ingest(payload('D1', relation=True))
    store.ingest(payload('D2', relation=True))
    sid = store.seal_direct()
    mark_verified(store,sid)
    store.activate(sid)
    before = store.snapshot(sid)
    preview = identity_batch.preview(store)
    assert len(preview['eligible']) == 2
    assert store.materialize()['redirects'] == {}
    with pytest.raises(ValueError, match='xem trước'):
        identity_batch.confirm(store, preview['revision'], 'invalid')
    result = identity_batch.confirm(store, preview['revision'], preview['token'])
    draft = store.materialize()
    assert result['retired_entities'] == 2
    assert len(draft['relations']) == 1
    assert len(draft['assertions']) == 2
    assert draft['evidence'] == before['evidence']
    assert store.active()['id'] == sid
    assert store.snapshot(sid) == before
    assert not identity_batch.preview(store)['eligible']
    with pytest.raises(ValueError, match='Bản nháp đã đổi'):
        identity_batch.confirm(store, preview['revision'], preview['token'])


def test_batch_skips_alias_case_and_type_and_reports_conflicts(store):
    raw = payload(entities=[
        entity('Edge',eid='A'), entity('Edge',eid='B'),
        entity('Prop',eid='C',props={'rxnorm':'1'}), entity('Prop',eid='D',props={'rxnorm':'2'}),
        entity('Distinct',eid='E'), entity('Distinct',eid='F'),
        entity('Alpha',['Alias'],eid='G'), entity('Beta',['Alias'],eid='H'),
        entity('Same',eid='I'), entity('Same',eid='J',kind='G'), entity('same',eid='K')
    ])
    raw['relations'] = [{'id':'R','type':'RELATED','source':'A','target':'B','proposition_ids':['P']}]
    raw['propositions'] = [{'id':'P','text':'Original sentence.','evidence':[{'sentence_id':'S1'}]}]
    store.ingest(raw)
    mapping = store.materialize()['entity_mapping']['D1']['ids']
    store.decide({'revision':store.revision(),'action':'distinct','ids':[mapping['E'],mapping['F']]})
    preview = identity_batch.preview(store)
    assert preview['eligible'] == []
    reasons = {row['name']:row['reason'] for row in preview['blocked']}
    assert set(reasons) == {'Edge','Prop','Distinct'}
    assert 'tự nối' in reasons['Edge']
    assert 'rxnorm' in reasons['Prop']
    assert 'khác nhau' in reasons['Distinct']


def test_batch_is_atomic_when_a_group_fails(store, monkeypatch):
    store.ingest(payload('D1', relation=True))
    store.ingest(payload('D2', relation=True))
    before = store.materialize()
    preview = identity_batch.preview(store)
    apply = store.apply_merge

    def fail_second(ids, result):
        if result['type'] == 'G':
            raise RuntimeError('injected')
        apply(ids,result)

    monkeypatch.setattr(store,'apply_merge',fail_second)
    with pytest.raises(RuntimeError, match='injected'):
        identity_batch.confirm(store,preview['revision'],preview['token'])
    assert store.materialize() == before


def test_http_batch_requires_explicit_confirmation(store, monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.direct_import import api

    store.ingest(payload('D1'))
    store.ingest(payload('D2'))
    monkeypatch.setenv('BATCH_DATA_ROOT', str(tmp_path))
    monkeypatch.setattr(api, 'configured_store', lambda: ExactStore(store.path,store.ontology,store.limits))
    app = FastAPI()
    app.include_router(api.create_router())
    client = TestClient(app)
    path = '/api/v1/direct-import/identity/batch'
    preview = client.get(path).json()
    body = {key:preview[key] for key in ('revision','token')}
    assert client.post(path,json=body).status_code == 422
    response = client.post(path,json={**body,'confirmed':True})
    assert response.status_code == 200
    assert response.json()['merged_groups'] == 1
