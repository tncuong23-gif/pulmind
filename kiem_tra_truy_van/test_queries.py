"""Standalone diagnostic runner for medical-ai-integrated. No source-code patching."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from urllib import request,error
import uuid
import zipfile

HERE=Path(__file__).resolve().parent
KG='/modules/kg/api/v1/kg'
CHAT_CASES=[
 ('general','GENERAL_MEDICAL_QUERY','COPD là bệnh gì?'),
 ('general-prevention','GENERAL_MEDICAL_QUERY','Làm thế nào để phòng ngừa bệnh phổi?'),
 ('outside','OUT_OF_SCOPE','Hướng dẫn tôi giải phương trình bậc hai.'),
 ('diagnostic','DIAGNOSTIC_ASSESSMENT','Tôi bị ho kéo dài và khó thở, tôi cần đánh giá bệnh gì?'),
 ('symptom','RELATIONAL_QUERY','COPD có những triệu chứng nào?'),
 ('diagnosis','RELATIONAL_QUERY','COPD được chẩn đoán bằng xét nghiệm nào?'),
 ('treatment','RELATIONAL_QUERY','COPD được điều trị bằng thuốc nào?'),
 ('adverse-effect','RELATIONAL_QUERY','Salbutamol có tác dụng phụ gì?'),
 ('contraindication','RELATIONAL_QUERY','Salbutamol có chống chỉ định nào?'),
 ('risk','RELATIONAL_QUERY','Yếu tố nguy cơ của COPD là gì?'),
 ('explanation','CLINICAL_EXPLANATION_MANAGEMENT','Giải thích vì sao hút thuốc gây COPD và cách quản lý bệnh.'),
 ('compare','RELATIONAL_QUERY','So sánh triệu chứng của COPD và hen phế quản.'),
 ('common','RELATIONAL_QUERY','COPD và hen phế quản có triệu chứng chung nào?'),
 ('difference','RELATIONAL_QUERY','Triệu chứng khác nhau giữa COPD và hen phế quản là gì?'),
 ('path','RELATIONAL_QUERY','COPD có liên hệ với Salbutamol qua những quan hệ nào?'),
 ('multi-hop','RELATIONAL_QUERY','Thuốc điều trị COPD có tác dụng phụ gì?'),
 ('inference','RELATIONAL_QUERY','Suy luận phân loại bắc cầu của COPD.'),
 ('alias','RELATIONAL_QUERY','BPTNMT có những triệu chứng nào?'),
 ('ambiguous','RELATIONAL_QUERY','SABA là thuốc gì?'),
 ('unknown','RELATIONAL_QUERY','TEST_UNKNOWN_CONCEPT_917 có triệu chứng gì?'),
]

def redact(text):
    text=re.sub(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@',r'\1[REDACTED]@',text)
    text=re.sub(r'(?i)(authorization[\s\"\x27:=>]+)(?:bearer\s+)?[^\s,\"\x27]+',r'\1[REDACTED]',text)
    return re.sub(r'(?i)((?:password|api_key|access_token|secret)[\s\"\x27:=>]+)[^\s,\"\x27]+',r'\1[REDACTED]',text)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write_json(path,data):path.write_text(redact(json.dumps(data,ensure_ascii=False,indent=2)),encoding='utf-8')

def setup_project(project):
    root=Path(project).resolve();backend=root/'backend'
    if not (backend/'app/main.py').is_file():raise ValueError('Chon thu muc co backend/app/main.py.')
    os.chdir(backend);sys.path.insert(0,str(backend))
    from dotenv import load_dotenv
    load_dotenv(backend/'.env',override=False)
    return root,backend

class TracebackFilter(logging.Filter):
    def filter(self,record):
        if 'chat.failed' in str(record.msg) and not record.exc_info and sys.exc_info()[0]:
            record.exc_info=sys.exc_info()
        return True

def internal(args):
    root,backend=setup_project(args.project)
    if args.internal=='server':
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s',force=True)
        logging.getLogger('uvicorn.error').addFilter(TracebackFilter())
        from app.main import app
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=args.port,log_config=None,access_log=True)
        return 0
    report={'python':sys.version,'executable':sys.executable,'platform':sys.platform,'packages':{},'device_request':os.getenv('CLASSIFIER_DEVICE','auto')}
    for package in ('torch','transformers','sentence-transformers','scikit-learn','numpy','joblib','neo4j','pymongo','fastapi','uvicorn'):
        try:report['packages'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:report['packages'][package]='MISSING'
    write_json(Path(args.output)/'environment.json',report)
    # Read immutable active KG metadata without opening/migrating the working registry.
    from app.modules.kg_import.config import Settings as KGSettings
    from app.modules.kg_query.intents import describe_intents,PRESET_CHAINS
    settings=KGSettings.from_env()
    ontology=json.loads(Path(settings.ontology_path).read_text(encoding='utf-8-sig'))
    catalog={'intents':[{'id':i,'description':d} for i,d in describe_intents()],
             'presets':list(PRESET_CHAINS),'ontology':{'relations':list(ontology['relation_types']),'entity_types':ontology['entity_types']},
             'relation_specs':ontology['relation_types'],'samples':{},'inference_rules':[{'id':'is_a_transitive'},{'id':'part_of_transitive'}]}
    database=Path(os.getenv('BATCH_DATA_ROOT',str(backend/'data')))/'kg_global/global.sqlite3'
    if database.is_file():
        try:
            with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as db:
                row=db.execute("SELECT value FROM meta WHERE key='active'").fetchone()
                if row:
                    sid=json.loads(row[0])['id'];snapshot=db.execute('SELECT payload FROM snapshots WHERE id=?',(sid,)).fetchone()
                    if snapshot:
                        data=json.loads(snapshot[0]);catalog['active_snapshot']=sid
                        if data.get('ontology'):
                            active=data['ontology'];catalog['ontology']={'relations':list(active['relation_types']),'entity_types':active['entity_types']};catalog['relation_specs']=active['relation_types']
                        endpoints={r[k] for r in data['relations'].values() for k in ('source','target')}
                        for eid,e in data['entities'].items():
                            group=catalog['samples'].setdefault(e['type'],[])
                            if eid in endpoints and len(group)<2:group.append({'id':eid,'name':e['canonical_name'],'type':e['type']})
        except Exception:traceback.print_exc()
    write_json(Path(args.output)/'catalog.json',catalog)
    failures=0
    if os.getenv('DIAGNOSTIC_SKIP_CLASSIFIER')=='1':
        print('Heavy classifier probe skipped in existing-server mode.',flush=True)
        return 0
    try:
        import torch
        print('TORCH',torch.__version__,'CUDA_BUILD',torch.version.cuda,'CUDA_AVAILABLE',torch.cuda.is_available(),flush=True)
        if torch.cuda.is_available():print('GPU',torch.cuda.get_device_name(0),flush=True)
    except Exception:
        failures+=1;traceback.print_exc()
    try:
        from app.config import Settings
        from app.services.classifier import E5SVMClassifier
        s=Settings.from_env()
        classifier=E5SVMClassifier(s.classifier_path,s.embedding_model,s.id2label,s.embedding_prefix,s.normalize_embeddings,
              device=os.getenv('CLASSIFIER_DEVICE','auto'),revision=os.getenv('CLASSIFIER_EMBEDDING_REVISION','d13f1b27baf31030b7fd040960d60d909913633f'))
        for name,expected,question in CHAT_CASES[:5]:
            started=time.monotonic()
            try:print('CLASSIFIER',name,json.dumps(classifier.predict(question),ensure_ascii=False),'seconds',round(time.monotonic()-started,2),flush=True)
            except Exception:
                failures+=1;print('CLASSIFIER_FAILED',name,flush=True);traceback.print_exc()
                break
    except Exception:
        failures+=1;traceback.print_exc()
    return 1 if failures else 0

class Runner:
    def __init__(self,base,output,timeout):self.base=base.rstrip('/');self.output=output;self.timeout=timeout;self.records=[]
    def call(self,name,path,body=None,expected=(200,),timeout=None,group='kg',routing_hint=None):
        started=time.monotonic();record={'case':name,'group':group,'path':path,'request':body,'expected_http':list(expected),'started_at':datetime.now(timezone.utc).isoformat()}
        try:
            data=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None
            req=request.Request(self.base+path,data=data,headers={'Content-Type':'application/json'},method='POST' if body is not None else 'GET')
            try:
                with request.urlopen(req,timeout=timeout or self.timeout) as response:code=response.status;raw=response.read().decode('utf-8','replace')
            except error.HTTPError as exc:code=exc.code;raw=exc.read().decode('utf-8','replace')
            try:value=json.loads(raw)
            except ValueError:value={'non_json_body':raw}
            record.update(http_status=code,response=value,outcome='HTTP_OK' if code in expected else 'HTTP_ERROR')
            if code in expected and isinstance(value,dict):
                if value.get('status') in ('no_facts','no_entity','needs_clarification'):record['outcome']=value['status'].upper()
                if 200<=code<300 and value.get('error'):record['outcome']='RESPONSE_ERROR'
                meta=(value.get('message') or {}).get('metadata',{}) if isinstance(value.get('message'),dict) else {}
                record['observed_route']=meta.get('route');record['observed_classifier']=meta.get('classifier')
                if routing_hint:record['routing_reference']=routing_hint # Observational reference, not a clinical gold label.
                record['semantic_status']=value.get('status')
                record['fact_count']=len((value.get('llm_context') or {}).get('facts',[]))
            elif code in expected:record['outcome']='UNEXPECTED_RESPONSE_SHAPE'
        except Exception as exc:
            value={};record.update(outcome='CONNECTION_ERROR',error_type=type(exc).__name__,error=redact(str(exc)),traceback=traceback.format_exc())
        record['seconds']=round(time.monotonic()-started,3);self.records.append(record)
        with (self.output/'requests.jsonl').open('a',encoding='utf-8') as stream:stream.write(redact(json.dumps(record,ensure_ascii=False))+'\n')
        print(name,record['outcome'],'HTTP',record.get('http_status','-'),record['seconds'],'s',flush=True)
        return value

    def query(self,name,**body):return self.call(name,KG+'/query',{'question':'Thông tin y khoa về COPD','limit':10,'include_evidence':True,**body})

def suite(r,catalog,quick=False,chat=True):
    r.call('health','/health/live',group='health');r.call('system-status','/api/v1/status',group='health')
    r.call('kg-ready','/modules/kg/health/ready',group='health');r.call('rag-health','/modules/rag/api/v1/rag/health',group='health')
    live=r.call('kg-catalog',KG+'/meta',group='catalog')
    if isinstance(live,dict) and 'intents' in live:
        catalog={**catalog,**live};write_json(r.output/'live-catalog.json',live)
    r.coverage={'catalog_available':bool(catalog.get('intents')),'intents_discovered':len(catalog.get('intents',[])),
                'presets_discovered':len(catalog.get('presets',[])),
                'ontology_relations_discovered':len(catalog.get('ontology',{}).get('relations',[])),
                'quick_mode':quick,'chat_enabled':chat}
    diseases=catalog.get('samples',{}).get('Disease',[])
    anchors={'entity_ids':[diseases[0]['id']]} if diseases else {'mentions':['COPD']}
    pair={'entity_ids':[d['id'] for d in diseases[:2]]} if len(diseases)>=2 else {'mentions':['COPD','Hen phế quản']}
    for mention in ['COPD','BPTNMT','Bệnh phổi tắc nghẽn mạn tính','SABA','TEST_UNKNOWN_CONCEPT_917']:
        r.query('lookup:'+mention,question=mention+' có triệu chứng gì?',mentions=[mention],intents=['symptom'],mode='one_hop')
    intents=catalog.get('intents',[])
    for intent in (intents[:4] if quick else intents):
        key=intent['id'] if isinstance(intent,dict) else intent
        r.query('intent:'+key,mode='one_hop',intents=[key],**anchors)
    presets=catalog.get('presets',[])
    for item in (presets[:3] if quick else presets):
        key=item['id'] if isinstance(item,dict) else item
        r.query('preset:'+key,mode='multi_hop',preset=key,**anchors)
    for mode in ('auto','one_hop','path','compare','common','difference'):
        body={'mode':mode,**(pair if mode in ('path','compare','common','difference') else anchors)}
        if mode in ('compare','common','difference','one_hop'):body['intents']=['symptom']
        r.query('mode:'+mode,**body)
    for direction in ('auto','out','in','any'):
        r.query('direction:'+direction,mode='one_hop',intents=['related'],direction=direction,**anchors)
    for rule in ('is_a_transitive','part_of_transitive'):
        families=('AnatomicalStructure','Organ','OrganSystem') if rule=='part_of_transitive' else ('DiseaseSubtype','Disease','Pathogen','DrugClass')
        sample=next((e for t in families for e in catalog.get('samples',{}).get(t,[])),None)
        selected={'entity_ids':[sample['id']]} if sample else {'mentions':['Phổi' if rule=='part_of_transitive' else 'COPD']}
        for scope in ('same_document','cross_document'):
            r.query('inference:'+rule+':'+scope,mode='inference',inference_rule=rule,evidence_scope=scope,**selected)
    r.query('custom-steps',mode='multi_hop',steps=[{'intent':'related','direction':'out'},{'intent':'related','direction':'any'}],**anchors)
    r.query('without-evidence',mode='one_hop',intents=['symptom'],include_evidence=False,**anchors)
    relations=catalog.get('ontology',{}).get('relations',[])
    if not quick:
        for rel in relations:
            spec=catalog.get('relation_specs',{}).get(rel,{})
            domain=spec.get('domain',[]);sample=next((e for t in domain for e in catalog.get('samples',{}).get(t,[])),None)
            selected={'entity_ids':[sample['id']]} if sample else anchors
            r.query('relation:'+rel,mode='one_hop',rel_types=[rel],direction='out',**selected)
    r.call('assessment:coverage',KG+'/assessment/coverage',{'page_size':5},group='assessment')
    r.call('assessment:mapping',KG+'/assessment/map',{'mentions':['COPD','SABA','TEST_UNKNOWN_CONCEPT_917']},group='assessment')
    symptoms=catalog.get('samples',{}).get('Symptom',[])
    if symptoms:
        r.call('assessment:synthetic-followups',KG+'/assessment/followups',{
            'patient_id':'diag-fictional-'+uuid.uuid4().hex,'assessment_id':'diag-fixture',
            'facts':[{'fact_id':'diag-fact','kg_entity_id':symptoms[0]['id'],'presence':'unknown',
                      'confirmation_status':'user_confirmed','confirmed_at':datetime.now(timezone.utc).isoformat(),
                      'source_id':'SYNTHETIC_TEST_NOT_A_REAL_PATIENT','timeframe':'current'}],
            'max_questions':2},group='assessment')
    for kind in ('all','chunk','proposition'):

        r.call('rag:'+kind,'/modules/rag/api/v1/rag/search',{'query':'COPD là gì?','kind':kind,'top_k':3,'filters':{}},group='rag')
    for name,body in [('blank',{'question':' '}),('bad-mode',{'question':'COPD','mode':'invalid'}),('bad-limit',{'question':'COPD','limit':0}),('bad-hops',{'question':'COPD','max_hops':9}),('conflicting-ids',{'question':'COPD','entity_ids':['FAKE'],'mentions':['COPD']}),('missing-chain',{'question':'COPD','mode':'multi_hop'}),('unknown-preset',{'question':'COPD','preset':'DOES_NOT_EXIST'})]:
        r.call('invalid:'+name,KG+'/query',body,expected=(422,),group='validation')
    if not chat:return
    cases=CHAT_CASES[:6] if quick else CHAT_CASES
    for name,reference,question in cases:
        body={'conversationId':'diag-'+uuid.uuid4().hex,'message':{'id':str(uuid.uuid4()),'role':'user','content':question,'attachments':[]}}
        r.call('chat:'+name,'/api/v1/chat/message',body,group='chat',routing_hint=reference)
    conversation='diag-context-'+uuid.uuid4().hex
    for n,question in enumerate(('COPD có triệu chứng gì?','Bệnh đó được điều trị thế nào?','Còn hen phế quản thì sao?'),1):
        r.call('context-turn:'+str(n),'/api/v1/chat/message',{'conversationId':conversation,'message':{'id':str(uuid.uuid4()),'role':'user','content':question,'attachments':[]}},group='context')

def pump(process,path):
    with path.open('w',encoding='utf-8') as log:
        for line in process.stdout:
            log.write(redact(line));log.flush()

def child_args(args,internal_name,output):return [sys.executable,str(Path(__file__).resolve()),'--internal',internal_name,'--project',str(Path(args.project).resolve()),'--output',str(output),'--port',str(args.port)]

def main(args):
    project=Path(args.project).resolve()
    if not (project/'backend/app/main.py').is_file():raise ValueError('Khong tim thay backend/app/main.py canh BAT.')
    output=HERE/'query_test_logs'/datetime.now().strftime('%Y%m%d-%H%M%S')/uuid.uuid4().hex[:6];output.mkdir(parents=True)
    env=os.environ.copy();env['PYTHONUNBUFFERED']='1';env['PYTHONUTF8']='1';env['PYTHONIOENCODING']='utf-8'
    if args.device:env['CLASSIFIER_DEVICE']=args.device
    if args.existing:env['DIAGNOSTIC_SKIP_CLASSIFIER']='1'
    env['DATABASE_PATH']=str(output/'diagnostic-assistant.sqlite3');env['UPLOAD_DIR']=str(output/'synthetic-uploads')
    process=None;thread=None;runner=None;interrupted=False;fatal=None;probe_exit=None
    try:
        print('Output:',output,flush=True)
        try:
            with (output/'classifier-probe.log').open('w',encoding='utf-8') as log:
                probe=subprocess.run(child_args(args,'probe',output),env=env,cwd=project/'backend',stdout=log,stderr=subprocess.STDOUT,timeout=args.probe_timeout)
            probe_exit=probe.returncode;print('Classifier probe exit:',probe_exit,flush=True)
        except subprocess.TimeoutExpired:print('Classifier probe timed out; continuing HTTP tests.',flush=True)
        # Redact the completed diagnostic probe before it enters the shared archive.
        probe_log=output/'classifier-probe.log'
        if probe_log.exists():probe_log.write_text(redact(probe_log.read_text(encoding='utf-8',errors='replace')),encoding='utf-8')
        catalog=read_json(output/'catalog.json') if (output/'catalog.json').is_file() else {}
        if not args.existing:
            with socket.socket() as sock:sock.bind(('127.0.0.1',args.port))
            process=subprocess.Popen(child_args(args,'server',output),cwd=project/'backend',env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            thread=threading.Thread(target=pump,args=(process,output/'backend.log'),daemon=True);thread.start()
            base='http://127.0.0.1:'+str(args.port);deadline=time.monotonic()+args.startup_timeout
            while time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError('Diagnostic backend exited; see backend.log')
                try:
                    with request.urlopen(base+'/health/live',timeout=2) as response:
                        if response.status==200:break
                except (OSError,error.URLError):time.sleep(1)
            else:raise TimeoutError('Backend startup timed out; see backend.log')
        else:base=args.existing
        runner=Runner(base,output,args.timeout);suite(runner,catalog,args.quick,not args.no_chat)
    except KeyboardInterrupt:interrupted=True;print('Interrupted; saving partial logs.',flush=True)
    except Exception as exc:
        fatal=redact(traceback.format_exc());(output/'runner-error.log').write_text(fatal,encoding='utf-8');print('ERROR:',redact(str(exc)),flush=True)
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
            if thread:thread.join(timeout=5)
        records=runner.records if runner else []
        counts=dict(Counter(r['outcome'] for r in records));failures=[r['case'] for r in records if r['outcome'] in ('HTTP_ERROR','CONNECTION_ERROR','UNEXPECTED_RESPONSE_SHAPE','RESPONSE_ERROR')]
        summary={'project':'medical-ai-integrated','started_backend':not bool(args.existing),'device_override':args.device,
                 'catalog_coverage':getattr(runner,'coverage',{}),'classifier_probe_skipped':bool(args.existing),'classifier_probe_exit':probe_exit,'cases':len(records),'outcomes':counts,'failed_cases':failures,'interrupted':interrupted,'fatal_error':fatal,
                 'coverage_note':'HTTP_OK is transport/schema success, not proof of correct routing or medical content. NO_FACTS/NO_ENTITY/NEEDS_CLARIFICATION mean the full retrieval branch may not have executed.',
                 'scope':'text chat, classifier probe, KG modes/intents/presets/ontology relations, RAG search and synthetic multi-turn context; excludes voice, uploads and interactive assessment actions',
                 'existing_backend_note':'Backend traceback cannot be collected remotely in --existing mode.' if args.existing else 'Traceback filter enabled only in this diagnostic backend; project source unchanged.'}
        write_json(output/'summary.json',summary)
        (output/'summary.txt').write_text('MEDICAL AI QUERY DIAGNOSTICS\n'+json.dumps(counts,ensure_ascii=False,indent=2)+'\nFAILED CASES:\n'+'\n'.join(failures)+'\n\n'+summary['coverage_note'],encoding='utf-8')
        archive=output.parent/(output.name+'-query-logs.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in output.iterdir():
                if p.suffix in ('.log','.txt','.json','.jsonl'):z.write(p,p.name)
        print('SEND THIS ZIP:',archive,flush=True)
    return 2 if fatal or interrupted or failures or probe_exit!=0 else 0

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--internal',choices=['server','probe'],help=argparse.SUPPRESS)
    parser.add_argument('--output');parser.add_argument('--port',type=int,default=8111);parser.add_argument('--existing');parser.add_argument('--device',choices=['auto','cpu','cuda'])
    parser.add_argument('--quick',action='store_true');parser.add_argument('--no-chat',action='store_true');parser.add_argument('--timeout',type=float,default=180)
    parser.add_argument('--startup-timeout',type=float,default=180);parser.add_argument('--probe-timeout',type=float,default=180)
    parsed=parser.parse_args();sys.exit(internal(parsed) if parsed.internal else main(parsed))
