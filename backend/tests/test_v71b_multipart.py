import hashlib

import pytest

from app.direct_import import multipart
from app.direct_import.store import ExactStore
from app.modules.kg_import.config import Limits
from app.modules.kg_import.ontology import Ontology
from tests.test_direct_import import ONTOLOGY, entity, mark_verified, payload


@pytest.fixture
def batch(tmp_path, monkeypatch):
    monkeypatch.setenv('BATCH_DATA_ROOT', str(tmp_path))
    archives = {1: b'part one', 2: b'part two'}
    monkeypatch.setattr(multipart, 'PARTS', {
        number: (f'D{number}', hashlib.sha256(content).hexdigest()) for number, content in archives.items()
    })

    def load(content, filename):
        number = 1 if content == archives[1] else 2
        raw = payload(f'D{number}', relation=True)
        raw['entities'].append(entity('A', eid=f'ORPHAN{number}'))
        return raw, {'ontology': ONTOLOGY, 'sentences': {'S1': {}}}

    monkeypatch.setattr(multipart, 'load_package', load)
    monkeypatch.setattr(multipart, 'EXPECTED', dict(
        source_entities=4, graph_entities=2, isolated_source_entities=2, relations=1,
        assertions=2, propositions=2, sentences=2, shared_entities=2, shared_relations=1))
    store = ExactStore(tmp_path/'global.sqlite3', Ontology.from_dict(ONTOLOGY), Limits())
    try:
        yield store, archives
    finally:
        store.db.close()


def stage(batch, number, dataset='V71B'):
    store, archives = batch
    return multipart.stage(store, dataset, number, 2, archives[number], f'part-{number}.zip')


def test_stage_order_idempotency_and_namespaced_identity(batch):
    store, archives = batch
    assert stage(batch, 2)['state'] == 'staged'
    assert store.materialize()['entities'] == {}
    with pytest.raises(ValueError, match='SHA-256'):
        multipart.stage(store, 'V71B', 1, 2, archives[2], 'wrong.zip')
    preview = stage(batch, 1)
    sid = preview['snapshot_id']
    assert stage(batch, 1)['snapshot_id'] == sid
    assert store.active() is None
    data = store.snapshot(sid)
    ids = data['entity_mapping']
    assert ids['D1']['ids']['E1'] == ids['D2']['ids']['E1']
    assert ids['D1']['ids']['ORPHAN1'] != ids['D2']['ids']['ORPHAN2']
    relation, = data['relations'].values()
    assert len(relation['assertion_ids']) == 2
    assert {data['assertions'][aid]['document_id'] for aid in relation['assertion_ids']} == {'D1', 'D2'}
    stage(batch, 1, 'other')
    other = stage(batch, 2, 'other')
    assert other['counts'] == preview['counts']
    assert store.snapshot(other['snapshot_id'])['entity_mapping']['D1']['ids']['E1'] != ids['D1']['ids']['E1']


def test_activation_requires_mongo_verification_and_promotes_atomically(batch):
    store, _ = batch
    stage(batch, 1)
    sid = stage(batch, 2)['snapshot_id']
    with pytest.raises(ValueError, match='Bản xem trước'):
        multipart.confirm(store, 'V71B', 'S_wrong', 'publish')
    with pytest.raises(ValueError, match='chưa đồng bộ'):
        multipart.confirm(store, 'V71B', sid, 'activate')

    class Publisher:
        def __init__(self, registry, settings):
            self.registry = registry

        def sync(self, snapshot):
            mark_verified(self.registry, snapshot)

    assert multipart.confirm(store, 'V71B', sid, 'publish', Publisher)['state'] == 'ready'
    with pytest.raises(ValueError, match='MongoDB'):
        multipart.confirm(store, 'V71B', sid, 'activate')
    assert store.active() is None
    assert store.materialize()['documents'] == {}
    progress = multipart.status(store, 'V71B')['progress']
    store.progress(sid, 'ready', {**progress, 'mongo_verified': True})
    assert multipart.confirm(store, 'V71B', sid, 'activate')['state'] == 'active'
    assert multipart.confirm(store, 'V71B', sid, 'activate')['state'] == 'active'
    assert store.materialize()['entity_mapping'] == store.snapshot(sid)['entity_mapping']
    with pytest.raises(ValueError, match='kho KG sạch'):
        stage(batch, 1, 'other')
