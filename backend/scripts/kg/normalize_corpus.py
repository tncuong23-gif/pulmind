"""Normalize a corpus ZIP offline; preserve all statements and source text."""
import argparse,json,zipfile
from collections import defaultdict
from pathlib import Path
from app.modules.kg_import.concept_identity import normalize_concepts,policy
from app.modules.kg_import.models import parse_import
from app.modules.kg_import.validation import validate
from app.modules.kg_import.ontology import Ontology
from app.modules.kg_import.config import Limits,BACKEND_ROOT
from app.modules.kg_import.utils import fold

def convert(source,output,ontology_path=None):
    source,output=Path(source),Path(output)
    if source.resolve()==output.resolve():raise ValueError('Output must differ from original ZIP')
    ontology=Ontology.load(ontology_path or BACKEND_ROOT/'examples/kg/kg_ontology.example.json')
    report={'policy':policy()['version'],'files':[],'pending_groups':[]};groups=defaultdict(dict);converted=[]
    with zipfile.ZipFile(source) as z:
        for name in z.namelist():
            if not name.endswith('.json'):continue
            raw=json.loads(z.read(name));new,mapping=normalize_concepts(raw)
            kg,issues=parse_import(new)
            if kg is not None:issues+=validate(kg,ontology,Limits())
            converted.append((('invalid/' if issues else 'documents/')+Path(name).name,new))
            report['files'].append({'file':name,'document_id':new['document']['document_id'],
                'remapped_ids':{a:b for a,b in mapping.items() if a!=b},'entities_before':len(raw['entities']),
                'entities_after':len(new['entities']),'relations':len(new['relations']),'propositions':len(new['propositions']),
                'validation_errors':[i.to_dict() for i in issues]})
            for e in new['entities']:groups[fold(e['canonical_name'])][e['id']]=e
    for name,members in sorted(groups.items()):
        if len({e['type'] for e in members.values()})>1:report['pending_groups'].append({'name':name,'entities':list(members.values())})
    report['summary']={'documents':len(converted),'valid_documents':sum(not f['validation_errors'] for f in report['files']),
        'normalized_groups':len(policy()['groups']),'remaining_cross_type_names':len(report['pending_groups']),
        'remapped_occurrences':sum(len(f['remapped_ids']) for f in report['files'])}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in converted:z.writestr(name,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        z.writestr('reports/normalization-report.json',json.dumps(report,ensure_ascii=False,indent=2))
        z.writestr('README.txt','Import only documents/*.json after updating backend and ontology.\nCross-type groups remain pending; see reports/normalization-report.json.\nDo not import invalid/ or reports/. No live database has been migrated.\n')
    output.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source');parser.add_argument('output');parser.add_argument('--ontology')
    args=parser.parse_args();report=convert(args.source,args.output,args.ontology);print(json.dumps(report['summary'],ensure_ascii=False))
    return 1 if any(f['validation_errors'] for f in report['files']) else 0
if __name__=='__main__':raise SystemExit(main())
