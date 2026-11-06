"""Import the two verified V71B archives into a fresh KG registry."""
import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from app.kg_global.projection import build_projection
from app.kg_global.publish import Publisher
from app.kg_global.store import dumps, ident
from app.modules.kg_import.config import Settings
from app.modules.kg_import.utils import sha256_of, utcnow_iso

from .package import load_package
from .service import operation_lock, verify_ontology
from .store import ExactStore

PARTS = {
    1: ('DOC_900001', '530a15a717464337b606ff78bc49e3796283d840df9413673480416aa143c7ad'),
    2: ('DOC_900002', '08823b27a8c023bfe854e86768a299dd25d82cb8654979b8db30e2cc70d1fac7'),
}
ARCHIVE_HASHES = {digest for _, digest in PARTS.values()}
EXPECTED = dict(source_entities=6505, graph_entities=5635, isolated_source_entities=870, relations=7688,
                assertions=8205, propositions=5044, sentences=41946, shared_entities=790, shared_relations=517)


def clean_registry(store):
    if store.active() or store.db.execute('SELECT 1 FROM documents LIMIT 1').fetchone():
        raise ValueError('Nhập hai phần V71B yêu cầu kho KG sạch. Kho hiện tại đã có dữ liệu.')


def validate_dataset(dataset):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', dataset):
        raise ValueError('Mã bộ KG cần từ 1 đến 80 ký tự, gồm chữ ASCII, số, dấu gạch ngang hoặc gạch dưới.')
@contextmanager
def workspace(dataset):
    validate_dataset(dataset)
    with operation_lock():
        yield


def status(store, dataset):
    validate_dataset(dataset)
    parts = [{'part_number':row['part'], 'archive_sha256':row['archive_sha'], 'document_id':PARTS[row['part']][0]}
             for row in store.db.execute('SELECT part,archive_sha FROM multipart_parts WHERE dataset=? ORDER BY part',(dataset,))]
    preview = store.db.execute('SELECT * FROM multipart_previews WHERE dataset=?',(dataset,)).fetchone()
    result = {'dataset_id':dataset, 'total_parts':len(PARTS), 'parts':parts, 'state':'staged'}
    if not preview and len(parts)==len(PARTS):
        result['state']='preview_pending'
    if preview:
        sid = preview['snapshot']
        row = store.db.execute('SELECT state,progress FROM snapshots WHERE id=?',(sid,)).fetchone()
        active = store.active()
        result.update(snapshot_id=sid, counts=json.loads(preview['summary']),
                      state='active' if active and active['id']==sid else row['state'],
                      progress=json.loads(row['progress']))
    return result


def build_preview(store, dataset):
    rows = list(store.db.execute('SELECT * FROM multipart_parts WHERE dataset=? ORDER BY part',(dataset,)))
    raw = [json.loads(row['payload']) for row in rows]
    provenance = [json.loads(row['provenance']) for row in rows]
    records = [{entity['id']:entity for entity in part['entities']} for part in raw]
    shared = records[0].keys() & records[1].keys()
    for local in sorted(shared):
        if records[0][local]!=records[1][local]:
            raise ValueError('DATASET_IDENTITY_CONFLICT: '+local)
    ids = {local:'GE_'+sha256_of(['kg-global-id/v1',dataset,local])
           for local in records[0].keys() | records[1].keys()}
    if len(set(ids.values()))!=len(ids):
        raise ValueError('Trùng mã GE_ giữa các ID nguồn.')
    with TemporaryDirectory() as directory:
        staging = ExactStore(Path(directory)/'preview.sqlite3',store.ontology,store.limits)
        try:
            for part, origin in zip(raw,provenance):
                verify_ontology(staging,origin)
                staging.ingest(part, provenance=origin, dataset_entity_ids=ids)
            data = staging.materialize()
        finally:
            staging.db.close()
    if data['conflicts']:
        raise ValueError('Dữ liệu V71B có xung đột: '+dumps(data['conflicts'][:5]))
    counts = {**build_projection(data)['counts'],
              'assertions':len(data['assertions']),
              'propositions':sum(len(part['propositions']) for part in raw),
              'sentences':sum(len(origin['sentences']) for origin in provenance),
              'shared_entities':len(shared),
              'shared_relations':len({r['id'] for r in raw[0]['relations']} & {r['id'] for r in raw[1]['relations']})}
    if counts!=EXPECTED:
        raise ValueError('Số liệu V71B khác đường cơ sở: '+dumps(counts))
    sid = ident('S_')
    with store.write():
        clean_registry(store)
        revision = store.revision()
        data.update(revision=revision+1, multipart_dataset=dataset)
        store.db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?)',(sid,-1,dumps(data),sha256_of(data),'sealed','{}'))
        store.db.execute('INSERT INTO multipart_previews VALUES(?,?,?,?)',(dataset,sid,revision,dumps(counts)))


def stage(store, dataset, part, total, content, filename):
    with workspace(dataset):
        digest = hashlib.sha256(content).hexdigest()
        if total!=len(PARTS) or part not in PARTS or digest!=PARTS[part][1]:
            raise ValueError('SHA-256 hoặc số thứ tự không khớp hai ZIP V71B đã kiểm chứng.')
        current = status(store,dataset)
        if 'snapshot_id' in current:
            return current
        clean_registry(store)
        if not any(item['part_number']==part for item in current['parts']):
            raw, provenance = load_package(content,filename)
            if raw['document']['document_id']!=PARTS[part][0] or 'ontology' not in provenance:
                raise ValueError('Mã tài liệu hoặc ontology không khớp gói V71B.')
            verify_ontology(store,provenance)
            store.check(raw)
            provenance = {k:v for k,v in provenance.items() if k not in ('filename','selected_file')}
            provenance.update(archive_sha256=digest,dataset_id=dataset,part_number=part,
                              total_parts=total,staged_at=utcnow_iso())
            with store.write():
                store.db.execute('INSERT INTO multipart_parts VALUES(?,?,?,?,?)',
                                 (dataset,part,digest,dumps(raw),dumps(provenance)))
        if len(status(store,dataset)['parts'])==total:
            build_preview(store,dataset)
        return status(store,dataset)


def confirm(store, dataset, sid, action, publisher_factory=Publisher):
    if action not in ('publish','activate'):
        raise ValueError('Thao tác không hợp lệ.')
    with workspace(dataset):
        preview = store.db.execute('SELECT * FROM multipart_previews WHERE dataset=?',(dataset,)).fetchone()
        if not preview or preview['snapshot']!=sid:
            raise ValueError('Bản xem trước đã thay đổi hoặc chưa đủ hai phần.')
        current = status(store,dataset)
        if current['state']=='active':
            return current
        clean_registry(store)
        if preview['revision']!=store.revision():
            raise ValueError('Registry đã thay đổi kể từ lúc xem trước.')
        if action=='publish':
            settings = Settings.from_env()
            settings = replace(settings,entity_embedding=replace(settings.entity_embedding,enabled=False))
            publisher_factory(store,settings).sync(sid)
        else:
            if current['state']!='ready':
                raise ValueError('Snapshot chưa đồng bộ và xác minh đầy đủ.')
            store.restore(store.snapshot(sid),activate_snapshot=sid,expected_revision=preview['revision'])
        return status(store,dataset)
