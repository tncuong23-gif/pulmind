"""Read-only source audit. Run from backend: python scripts/kg/audit_kg_source.py FILE."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.modules.kg_import.utils import fold
from app.modules.kg_import.models import parse_import
from app.modules.kg_import.validation import validate
from app.modules.kg_import.config import Limits,Settings
from app.modules.kg_import.ontology import Ontology


def audit(raw,ontology):
    kg,issues=parse_import(raw)
    if kg is not None:issues+=validate(kg,ontology,Limits())
    entities={e['id']:e for e in raw['entities']}
    endpoints={r[k] for r in raw['relations'] for k in ('source','target')}
    terms=defaultdict(set)
    for eid,e in entities.items():
        for n in [e['canonical_name'],*e.get('aliases',[])]:terms[(e['type'],fold(n))].add(eid)
    return {'counts':{k:len(raw[k]) for k in ('entities','relations','propositions')},
            'unique_triples':len({(r['source'],r['type'],r['target']) for r in raw['relations']}),
            'referenced_entities':len(endpoints & entities.keys()),'isolated_entities':len(entities.keys()-endpoints),
            'missing_endpoints':sorted(endpoints-entities.keys()),
            'declared_aliases':sum(len(e.get('aliases',[])) for e in entities.values()),
            'ambiguous_terms':[{'type':kind,'term':term,'entity_ids':sorted(ids)} for (kind,term),ids in sorted(terms.items()) if len(ids)>1],
            'validation_issues':[{'code':i.code,'path':i.path,'message':i.message} for i in issues]}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('--ontology',default=Settings().ontology_path)
    args=parser.parse_args()
    print(json.dumps(audit(json.loads(Path(args.source).read_text(encoding='utf-8-sig')),Ontology.load(args.ontology)),ensure_ascii=False,indent=2))
