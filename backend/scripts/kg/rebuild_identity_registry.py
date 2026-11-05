"""Rebuild a NEW offline registry from active source documents, without old merges.

The source database is read-only. No network, publication, activation or deletion.
Keep the original database for historical snapshots, decisions and rollback.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.direct_import.store import ExactStore
from app.modules.kg_import.config import Limits,Settings
from app.modules.kg_import.ontology import Ontology


def rebuild(source,destination,ontology):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or not source.is_file():raise ValueError('Chọn kho nguồn có sẵn và đường dẫn đích mới.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation prevents accidental replacement of a working registry.
    with destination.open('xb'):pass
    old=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);old.row_factory=sqlite3.Row
    new=ExactStore(destination,ontology,Limits())
    try:
        old.execute('BEGIN')
        has_provenance=old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_provenance'").fetchone()
        for doc in old.execute('SELECT * FROM documents WHERE active=1 ORDER BY doc'):
            provenance={}
            if has_provenance:
                row=old.execute('SELECT data FROM source_provenance WHERE doc=? AND version=?',(doc['doc'],doc['version'])).fetchone()
                if row:provenance=json.loads(row[0])
            new.ingest(json.loads(doc['payload']),provenance=provenance)
        sid=new.seal_direct();data=new.snapshot(sid)
        from app.kg_global.projection import build_projection
        return {'destination':str(destination),'snapshot_id':sid,'state':'sealed','active':new.active(),
                'counts':build_projection(data)['counts'],'ambiguous_terms':len(data['ambiguous_terms']),
                'note':'Kho cũ không đổi; lịch sử và quyết định cũ vẫn ở kho nguồn. Cần duyệt lại identity trước khi sử dụng kho mới.'}
    finally:
        old.close();new.db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--destination',required=True)
    parser.add_argument('--ontology',default=Settings().ontology_path);args=parser.parse_args()
    print(json.dumps(rebuild(args.source,args.destination,Ontology.load(args.ontology)),ensure_ascii=False,indent=2))
