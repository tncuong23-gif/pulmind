"""End-to-end OFFLINE regression using a real source file and a temporary registry."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.direct_import.store import ExactStore
from app.kg_global.projection import build_projection
from app.modules.kg_import.config import Limits,Settings
from app.modules.kg_import.ontology import Ontology

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('--ontology',default=Settings().ontology_path);args=parser.parse_args()
    raw=json.loads(Path(args.source).read_text(encoding='utf-8-sig'))
    with tempfile.TemporaryDirectory(prefix='kg-fixture-') as directory:
        store=ExactStore(Path(directory)/'global.sqlite',Ontology.load(args.ontology),Limits())
        try:
            store.ingest(raw);sid=store.seal_direct();data=store.snapshot(sid);projection=build_projection(data)
            mapping=data['entity_mapping'][raw['document']['document_id']]['ids']
            expected={(mapping[r['source']],r['type'],mapping[r['target']]) for r in raw['relations']}
            actual={(r['s'],r['type'],r['t']) for r in projection['edges'].values()}
            if actual!=expected:raise ValueError('Sai bộ ba so với nguồn.')
            if len(data['entities'])!=len(raw['entities']) or data['redirects']:raise ValueError('Có gộp định danh ngoài ý muốn.')
            for aid,a in data['assertions'].items():
                original=next(r for r in raw['relations'] if r['id']==a['original_relation_id'])
                if a['proposition_ids']!=original['proposition_ids']:raise ValueError('Mất liên kết proposition: '+aid)
            repeated=store.ingest(raw)
            if repeated['status']!='unchanged' or store.seal_direct()!=sid:raise ValueError('Import lặp không ổn định.')
            print(json.dumps({'scope':'offline SQLite, snapshot and projection; no live database writes',
                  'source_counts':{k:len(raw[k]) for k in ('entities','relations','propositions')},
                  'projection_counts':projection['counts'],'exact_triples_match':True,'same_snapshot_on_repeat':True,
                  'assertions':len(data['assertions']),'evidence':len(data['evidence']),
                  'ambiguous_terms':len(data['ambiguous_terms']),'redirects':len(data['redirects'])},ensure_ascii=False,indent=2))
        finally:store.db.close()
