import json
import sqlite3
from unittest.mock import MagicMock, Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.kg_global import query
from app.modules.kg_import.ontology import Ontology
from app.modules.kg_query.service import KGQueryService
from app.modules.kg_query.browse import register_browse


def test_source_ids_bound_to_the_active_snapshot_and_node(tmp_path, monkeypatch):
    monkeypatch.setattr(query, 'root', lambda: tmp_path)
    sid_a, sid_b = ('S_' + letter * 32 for letter in 'ab')
    ontology = {'entity_types': ['Disease'], 'relation_types': {'RELATED': {'domain': ['Disease'], 'range': ['Disease']}}}
    with sqlite3.connect(tmp_path / 'global.sqlite3') as db:
        db.execute('CREATE TABLE meta(key TEXT, value TEXT)')
        db.execute('CREATE TABLE snapshots(id TEXT, payload TEXT)')
        db.execute("INSERT INTO meta VALUES('active', ?)", (json.dumps({'id': sid_a}),))
        for sid, mapping in [
            (sid_a, {
                'DOC_900001': {'ids': {'ENT_000001': 'GE_1', 'ENT_000002': 'GE_2'}},
                'DOC_900002': {'ids': {'ENT_000001': 'GE_1', 'ENT_000003': 'GE_1'}},
            }),
            (sid_b, {'DOC_OTHER': {'ids': {'ENT_000099': 'GE_1'}}}),
        ]:
            data = {'ontology': ontology,
                    'documents': {}, 'entity_mapping': mapping}
            db.execute('INSERT INTO snapshots VALUES(?, ?)', (sid, json.dumps(data)))
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    tx = Mock()
    session.execute_read.side_effect = lambda callback: callback(tx)
    tx.run.side_effect = lambda statement, **params: (
        [{'node': {'id': params['id'], 'name': 'Test', 'type': 'Disease'}, 'aliases': [], 'attributes': None}]
        if 'AS node' in statement else []
    )
    base = KGQueryService(driver, Ontology.from_dict(ontology))
    app = FastAPI()
    register_browse(app, lambda: query.select_service(base))
    client = TestClient(app)

    def get(label, gid='GE_1'):
        return client.get('/api/browse/node', params={'id': gid, 'snapshot': label})

    first = get('KGGlobal_' + sid_a)
    assert first.status_code == 200
    assert first.json()['source_ids'] == [
        {'id': 'ENT_000001', 'document_id': 'DOC_900001'},
        {'id': 'ENT_000001', 'document_id': 'DOC_900002'},
        {'id': 'ENT_000003', 'document_id': 'DOC_900002'},
    ]
    assert get('KGGlobal_' + sid_a, 'GE_2').json()['source_ids'] == [
        {'id': 'ENT_000002', 'document_id': 'DOC_900001'},
    ]
    with sqlite3.connect(tmp_path / 'global.sqlite3') as db:
        db.execute("UPDATE meta SET value=? WHERE key='active'", (json.dumps({'id': sid_b}),))
    assert get('KGGlobal_' + sid_a).status_code == 409
    assert get('KGGlobal_' + sid_b).json()['source_ids'] == [
        {'id': 'ENT_000099', 'document_id': 'DOC_OTHER'},
    ]
    with sqlite3.connect(tmp_path / 'global.sqlite3') as db:
        db.execute("DELETE FROM meta WHERE key='active'")
    assert get('Entity').json()['source_ids'] == []
