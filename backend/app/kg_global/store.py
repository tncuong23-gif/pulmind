from __future__ import annotations
import json, sqlite3, threading, uuid, os
from pathlib import Path
from contextlib import contextmanager
from copy import deepcopy
from collections import defaultdict
from app.modules.kg_import.utils import sha256_of, fold, utcnow_iso
from app.modules.kg_import.models import parse_import
from app.modules.kg_import.validation import validate
from app.modules.kg_import.normalization import normalize

SCHEMA='kg-global/1'
def ident(prefix): return prefix+uuid.uuid4().hex
def root():
    from app.modules.kg_import.config import BACKEND_ROOT
    return Path(os.getenv('BATCH_DATA_ROOT',str(BACKEND_ROOT/'data')))/'kg_global'
def dumps(x): return json.dumps(x,ensure_ascii=False,sort_keys=True)

class GlobalStore:
    def __init__(self,path,ontology,limits):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.ontology,self.limits=ontology,limits;self.lock=threading.RLock()
        self.db=sqlite3.connect(self.path,timeout=30,check_same_thread=False);self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO meta VALUES('revision','0');
        CREATE TABLE IF NOT EXISTS documents(doc TEXT,version INTEGER,hash TEXT,payload TEXT,active INTEGER,PRIMARY KEY(doc,version));
        CREATE UNIQUE INDEX IF NOT EXISTS doc_active ON documents(doc) WHERE active=1;
        CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mappings(doc TEXT,version INTEGER,local TEXT,gid TEXT,PRIMARY KEY(doc,version,local));
        CREATE INDEX IF NOT EXISTS map_gid ON mappings(gid);
        CREATE TABLE IF NOT EXISTS redirects(old TEXT PRIMARY KEY,target TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS distinct_pairs(pair TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS dispositions(doc TEXT,version INTEGER,relation TEXT,reason TEXT,PRIMARY KEY(doc,version,relation));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,stamp TEXT,action TEXT,data TEXT);
        CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,revision INTEGER,payload TEXT,hash TEXT,state TEXT,progress TEXT);
        ''');self.db.commit()
    @contextmanager
    def write(self,expected=None):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if expected is not None and expected!=self.revision():raise ValueError('Bản nháp đã đổi; tải lại trước khi xác nhận.')
                yield
                self.db.commit()
            except Exception:self.db.rollback();raise
    def revision(self):return int(self.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
    def changed(self,action,data):
        self.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
        self.db.execute("DELETE FROM meta WHERE key='semantic_scan'")
        self.db.execute('INSERT INTO audit(stamp,action,data) VALUES(?,?,?)',(utcnow_iso(),action,dumps(data)))
    def ingest(self,payload,filename=''):
        kg,issues=parse_import(payload)
        if kg is not None:issues+=validate(kg,self.ontology,self.limits)
        if issues:raise ValueError('; '.join(i.code+': '+i.message for i in issues[:10]))
        doc=kg.document.document_id;h=sha256_of(payload)
        with self.write():
            previous=self.db.execute('SELECT * FROM documents WHERE doc=? AND active=1',(doc,)).fetchone()
            if previous and previous['hash']==h:return {'document_id':doc,'status':'unchanged','version':previous['version']}
            version=self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM documents WHERE doc=?',(doc,)).fetchone()[0]
            oldents={e['id']:e for e in json.loads(previous['payload'])['entities']} if previous else {}
            oldmap={r['local']:r['gid'] for r in self.db.execute('SELECT local,gid FROM mappings WHERE doc=? AND version=?',(doc,previous['version']))} if previous else {}
            self.db.execute('UPDATE documents SET active=0 WHERE doc=?',(doc,))
            self.db.execute('INSERT INTO documents VALUES(?,?,?,?,1)',(doc,version,h,dumps(payload)))
            for e in kg.entities:
                old=oldents.get(e.id,{})
                gid=oldmap.get(e.id) if old.get('canonical_name')==e.canonical_name and old.get('type')==e.type else None
                if not gid:
                    gid=ident('GE_');self.db.execute('INSERT INTO entities VALUES(?,?)',(gid,dumps({'id':gid,'canonical_name':e.canonical_name,'type':e.type,'aliases':list(e.aliases),'properties':e.properties})))
                self.db.execute('INSERT INTO mappings VALUES(?,?,?,?)',(doc,version,e.id,gid))
            self.changed('ingest',{'document_id':doc,'version':version,'filename':filename})
        return {'document_id':doc,'version':version,'status':'staged'}
    def resolve_gid(self, gid):
        return gid

    def materialize(self):
        with self.lock:
            docs=[dict(r) for r in self.db.execute('SELECT * FROM documents WHERE active=1 ORDER BY doc')]
            entities={r['id']:json.loads(r['data']) for r in self.db.execute('SELECT * FROM entities')}
            mappings={};relations={};assertions={};evidence={};conflicts=[];used=set();records={}
            excluded={(r['doc'],r['version'],r['relation']):r['reason'] for r in self.db.execute('SELECT * FROM dispositions')}
            for doc in docs:
                raw=json.loads(doc['payload']);kg,_=parse_import(raw);norm=normalize(kg)
                mapping={r['local']:self.resolve_gid(r['gid']) for r in self.db.execute('SELECT * FROM mappings WHERE doc=? AND version=?',(doc['doc'],doc['version']))}
                mappings[doc['doc']]={'version':doc['version'],'ids':mapping};used.update(mapping.values())
                records[doc['doc']]={'version':doc['version'],'hash':doc['hash'],'payload':raw}
                evmap={}
                for e in norm.mongo['evidence']:
                    eid='GV_'+sha256_of([doc['doc'],doc['version'],e['evidence_id']]);evmap[e['evidence_id']]=eid
                    evidence[eid]={**e,'evidence_id':eid,'original_evidence_id':e['evidence_id'],'document_version':doc['version']}
                for rel in norm.relations:
                    localid=rel['id'];source=mapping.get(rel['source_id']);target=mapping.get(rel['target_id'])
                    if not source or not target:raise ValueError('Thiếu ánh xạ đầu mút trong tài liệu '+doc['doc'])
                    rid='GR_'+sha256_of([source,rel['relation_type'],target]);aid='GA_'+sha256_of([doc['doc'],doc['version'],localid])
                    a={'id':aid,'relation_id':rid,'document_id':doc['doc'],'document_version':doc['version'],'original_relation_id':localid,
                       'properties':json.loads(rel['properties_json']),'confidence':rel['confidence'],'proposition_ids':rel['proposition_ids'],
                       'evidence_ids':[evmap[x] for x in rel['evidence_ids']], 'excluded_reason':excluded.get((doc['doc'],doc['version'],localid))}
                    assertions[aid]=a
                    if a['excluded_reason']:continue
                    r=relations.setdefault(rid,{'id':rid,'source':source,'type':rel['relation_type'],'target':target,'assertion_ids':[]});r['assertion_ids'].append(aid)
                    msg=self.ontology.domain_range_error(r['type'],entities[source]['type'],entities[target]['type'])
                    if source==target:msg='Quan hệ tự nối sau gộp.'
                    if msg:conflicts.append({'kind':'ontology','assertion_id':aid,'relation_id':rid,'document_id':doc['doc'],'message':msg})
                    if not a['evidence_ids']:conflicts.append({'kind':'evidence','assertion_id':aid,'message':'Thiếu bằng chứng nguồn.'})
            for r in relations.values():
                groups=defaultdict(set)
                for aid in r['assertion_ids']:
                    a=assertions[aid];props=dict(a['properties']);neg=props.pop('negated',False)
                    groups[dumps(props)].add(bool(neg))
                if any(len(v)>1 for v in groups.values()):conflicts.append({'kind':'polarity','relation_id':r['id'],'message':'Có phát biểu phủ định và khẳng định với cùng thuộc tính; giữ cả hai nguồn.'})
            return {'schema_version':SCHEMA,'revision':self.revision(),'documents':records,'entities':{i:entities[i] for i in sorted(used)},
                    'entity_mapping':mappings,'redirects':{r['old']:r['target'] for r in self.db.execute('SELECT * FROM redirects')},
                    'relations':relations,'assertions':assertions,'evidence':evidence,'conflicts':conflicts,
                    'document_history':[{'document_id':r['doc'],'version':r['version'],'hash':r['hash'],'payload':json.loads(r['payload']),
                        'mapping':{m['local']:m['gid'] for m in self.db.execute('SELECT * FROM mappings WHERE doc=? AND version=?',(r['doc'],r['version']))}}
                        for r in self.db.execute('SELECT * FROM documents WHERE active=0 ORDER BY doc,version')],
                    'ontology':{'entity_types':sorted(self.ontology.entity_types),'relation_types':{k:{'domain':sorted(v.domain),'range':sorted(v.range)} for k,v in self.ontology.relations.items()}}}
    @staticmethod
    def pairkey(a,b):return '|'.join(sorted([a,b]))
    def candidates(self,encoder=None):
        data=self.materialize();entities=data['entities'];pairs={};buckets=defaultdict(set)
        distinct={r[0] for r in self.db.execute('SELECT pair FROM distinct_pairs')}
        for i,e in entities.items():
            for n in [e['canonical_name'],*e['aliases']]:
                if fold(n):buckets[fold(n)].add(i)
        for ids in buckets.values():
            ids=sorted(ids)
            for j,a in enumerate(ids):
                for b in ids[j+1:]:pairs[self.pairkey(a,b)]={'ids':[a,b],'reason':'name_or_alias','score':1.0}
        if encoder:
            import numpy as np
            threshold=float(os.getenv('KG_GLOBAL_SIMILARITY_THRESHOLD','0.88'))
            if not 0.5<=threshold<=1:raise ValueError('KG_GLOBAL_SIMILARITY_THRESHOLD phải từ 0.5 đến 1.')
            ids=list(entities);names=[entities[i]['canonical_name'] for i in ids]
            if names:
                vectors=np.asarray(encoder.encode(names,batch_size=32,normalize_embeddings=True,show_progress_bar=False))
                for start in range(0,len(ids),128):
                    scores=vectors[start:start+128]@vectors.T
                    for j,row in enumerate(scores):
                        a=start+j
                        for b in np.flatnonzero(row>=threshold):
                            if b>a:pairs.setdefault(self.pairkey(ids[a],ids[b]),{'ids':[ids[a],ids[b]],'reason':'embedding','score':round(float(row[b]),4)})
        return data,[p for k,p in pairs.items() if k not in distinct]
    def review(self,semantic=False,encoder=None):
        with self.lock:
            data,pairs=self.candidates(encoder if semantic else None)
            if semantic:
                with self.write(data['revision']):self.db.execute("INSERT OR REPLACE INTO meta VALUES('semantic_scan',?)",(dumps({'revision':data['revision'],'pairs':pairs}),))
            else:
                scan=self.db.execute("SELECT value FROM meta WHERE key='semantic_scan'").fetchone()
                if scan:
                    saved=json.loads(scan[0]);pairs=saved['pairs'] if saved['revision']==data['revision'] else pairs
            sources=defaultdict(list)
            for doc,m in data['entity_mapping'].items():
                for gid in set(m['ids'].values()):sources[gid].append(doc)
            return {'revision':data['revision'],'entity_sources':dict(sources),'entities':data['entities'],'pairs':pairs,'conflicts':data['conflicts'],
                    'documents':[{'id':k,'version':v['version'],'title':v['payload']['document'].get('title','')} for k,v in data['documents'].items()],
                    'counts':{k:len(data[k]) for k in ('documents','entities','relations','assertions','evidence')},
                    'snapshots':[{'id':r['id'],'revision':r['revision'],'state':r['state'],'progress':json.loads(r['progress'])} for r in self.db.execute('SELECT id,revision,state,progress FROM snapshots ORDER BY rowid DESC')],
                    'active':self.active()}
    def active(self):
        r=self.db.execute("SELECT value FROM meta WHERE key='active'").fetchone();return json.loads(r[0]) if r else None
    def decide(self,body):
        with self.write(body['revision']):
            data=self.materialize();ids=body.get('ids',[])
            if not 2<=len(set(ids))<=1000 or any(i not in data['entities'] for i in ids):raise ValueError('Chọn 2–1000 thực thể hiện hành.')
            if body['action']=='distinct':
                for j,a in enumerate(ids):
                    for b in ids[j+1:]:self.db.execute('INSERT OR IGNORE INTO distinct_pairs VALUES(?)',(self.pairkey(a,b),))
            elif body['action']=='merge':
                tid=body.get('target_id');kind=body.get('type');name=body.get('name','').strip()
                if tid not in ids or kind not in self.ontology.entity_types or not name or len(name)>500:raise ValueError('ID, loại hoặc tên chuẩn không hợp lệ.')
                # Check every affected active relation before saving the group.
                for r in data['relations'].values():
                    if r['source'] not in ids and r['target'] not in ids:continue
                    s=tid if r['source'] in ids else r['source'];t=tid if r['target'] in ids else r['target']
                    st=kind if s==tid else data['entities'][s]['type'];tt=kind if t==tid else data['entities'][t]['type']
                    msg=self.ontology.domain_range_error(r['type'],st,tt)
                    if s==t or msg:raise ValueError(r['id']+': '+(msg or 'Gộp tạo quan hệ tự nối'))
                props={};aliases=[]
                for i in ids:
                    e=data['entities'][i];aliases.extend([e['canonical_name'],*e['aliases']])
                    for k,v in e['properties'].items():
                        if k in props and props[k]!=v:raise ValueError('Thuộc tính mâu thuẫn: '+k)
                        props[k]=v
                result={'id':tid,'canonical_name':name,'type':kind,'aliases':sorted(set(a for a in aliases if a!=name)),'properties':props}
                self.db.execute('UPDATE entities SET data=? WHERE id=?',(dumps(result),tid))
                for i in ids:
                    if i==tid:continue
                    self.db.execute('UPDATE mappings SET gid=? WHERE gid=?',(tid,i))
                    self.db.execute('UPDATE redirects SET target=? WHERE target=?',(tid,i))
                    self.db.execute('INSERT OR REPLACE INTO redirects VALUES(?,?)',(i,tid))
                    self.db.execute('DELETE FROM entities WHERE id=?',(i,))
                # Old "distinct" decisions involving altered members must be reviewed again.
                for row in self.db.execute('SELECT pair FROM distinct_pairs').fetchall():
                    if set(row[0].split('|'))&set(ids):self.db.execute('DELETE FROM distinct_pairs WHERE pair=?',(row[0],))
            else:raise ValueError('Thao tác không hợp lệ.')
            self.changed(body['action'],body)
        return self.review()
    def withdraw(self,doc,revision):
        with self.write(revision):
            self.db.execute('UPDATE documents SET active=0 WHERE doc=?',(doc,));self.changed('withdraw',{'document_id':doc})
    def exclude(self,aid,reason,revision):
        with self.write(revision):
            a=self.materialize()['assertions'].get(aid)
            if not a or not reason.strip():raise ValueError('Chọn phát biểu và nhập lý do loại khỏi bản xuất.')
            self.db.execute('INSERT OR REPLACE INTO dispositions VALUES(?,?,?,?)',(a['document_id'],a['document_version'],a['original_relation_id'],reason))
            self.changed('exclude',{'assertion_id':aid,'reason':reason})
    def plan(self):
        with self.lock:
            data=self.materialize();current=self.active();old=self.snapshot(current['id']) if current else {}
            changes={}
            for key in ('documents','entities','relations','assertions','evidence'):
                before=old.get(key,{});after=data[key]
                changes[key]={'added':len(set(after)-set(before)),'removed':len(set(before)-set(after)),
                    'changed':sum(after[k]!=before[k] for k in set(after)&set(before))}
            return {'revision':data['revision'],'base_snapshot':current,'changes':changes,
                    'publication_mode':'isolated_full_snapshot'}
    def seal(self,revision,ack_conflicts=False):
        with self.write(revision):
            scan=self.db.execute("SELECT value FROM meta WHERE key='semantic_scan'").fetchone()
            if not scan or json.loads(scan[0])['revision']!=revision:raise ValueError('Chạy đối chiếu toàn bộ bản nháp hiện tại trước khi chốt.')
            review=self.review();data=self.materialize()
            if not data['documents']:raise ValueError('Chưa có tài liệu.')
            if review['pairs']:raise ValueError('Còn nhóm thực thể cần duyệt.')
            if any(c['kind']!='polarity' for c in data['conflicts']):raise ValueError('Còn lỗi ontology/bằng chứng.')
            if data['conflicts'] and not ack_conflicts:raise ValueError('Cần xác nhận giữ các phát biểu trái chiều cùng nguồn.')
            data['change_plan']=self.plan()
            data['review']={'distinct_pairs':[r[0] for r in self.db.execute('SELECT pair FROM distinct_pairs')],
                'audit':[dict(r) for r in self.db.execute('SELECT * FROM audit')],'conflicts_acknowledged':ack_conflicts}
            sid=ident('S_');h=sha256_of(data)
            self.db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?)',(sid,revision,dumps(data),h,'sealed','{}'))
            return {'id':sid,'hash':h,'revision':revision}
    def snapshot(self,sid):
        with self.lock:
            r=self.db.execute('SELECT * FROM snapshots WHERE id=?',(sid,)).fetchone()
            if not r:raise ValueError('Không tìm thấy phiên bản.')
            data=json.loads(r['payload'])
            if sha256_of(data)!=r['hash']:raise ValueError('Hash phiên bản không hợp lệ.')
            return data
    def progress(self,sid,state,progress):
        with self.write():self.db.execute('UPDATE snapshots SET state=?,progress=? WHERE id=?',(state,dumps(progress),sid))
    def activate(self,sid):
        with self.write():
            row=self.db.execute('SELECT state FROM snapshots WHERE id=?',(sid,)).fetchone()
            if not row or row[0]!='ready':raise ValueError('Phiên bản chưa đồng bộ đầy đủ.')
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('active',?)",(dumps({'id':sid}),))
    def restore(self,data):
        # Restore into an empty workspace only; preserve IDs and the immutable snapshot.
        if data.get('schema_version')!=SCHEMA:raise ValueError('Sai phiên bản global JSON.')
        with self.write():
            if self.db.execute('SELECT 1 FROM documents LIMIT 1').fetchone():raise ValueError('Chỉ phục hồi vào kho global trống.')
            for doc,d in data['documents'].items():
                kg,issues=parse_import(d['payload'])
                if kg is not None:issues+=validate(kg,self.ontology,self.limits)
                if kg is None or issues or kg.document.document_id!=doc or sha256_of(d['payload'])!=d['hash']:raise ValueError('Tài liệu không hợp lệ: '+doc)
                self.db.execute('INSERT INTO documents VALUES(?,?,?,?,1)',(doc,d['version'],d['hash'],dumps(d['payload'])))
                if data['entity_mapping'][doc]['version']!=d['version']:raise ValueError('Phiên bản ánh xạ không khớp.')
                mapping=data['entity_mapping'][doc]['ids']
                if set(mapping)!={e.id for e in kg.entities}:raise ValueError('Ánh xạ không đầy đủ.')
                for local,gid in mapping.items():
                    if gid not in data['entities']:raise ValueError('ID toàn cục không tồn tại.')
                    self.db.execute('INSERT INTO mappings VALUES(?,?,?,?)',(doc,d['version'],local,gid))
            for gid,e in data['entities'].items():
                if e.get('id')!=gid or e.get('type') not in self.ontology.entity_types or not isinstance(e.get('canonical_name'),str):raise ValueError('Thực thể phục hồi không hợp lệ.')
                self.db.execute('INSERT INTO entities VALUES(?,?)',(gid,dumps(e)))
            for h in data.get('document_history',[]):
                if sha256_of(h['payload'])!=h['hash']:raise ValueError('Hash lịch sử không hợp lệ.')
                self.db.execute('INSERT INTO documents VALUES(?,?,?,?,0)',(h['document_id'],h['version'],h['hash'],dumps(h['payload'])))
                for local,gid in h['mapping'].items():self.db.execute('INSERT INTO mappings VALUES(?,?,?,?)',(h['document_id'],h['version'],local,gid))
            for a in data.get('review',{}).get('audit',[]):
                self.db.execute('INSERT INTO audit(stamp,action,data) VALUES(?,?,?)',(a['stamp'],a['action'],a['data']))
            for old,tid in data.get('redirects',{}).items():self.db.execute('INSERT INTO redirects VALUES(?,?)',(old,tid))
            for pair in data.get('review',{}).get('distinct_pairs',[]):self.db.execute('INSERT INTO distinct_pairs VALUES(?)',(pair,))
            for a in data['assertions'].values():
                if a.get('excluded_reason'):self.db.execute('INSERT INTO dispositions VALUES(?,?,?,?)',(a['document_id'],a['document_version'],a['original_relation_id'],a['excluded_reason']))
            rebuilt=self.materialize()
            for key in ('relations','assertions','evidence'):
                if rebuilt[key]!=data[key]:raise ValueError('Dữ liệu global không nhất quán: '+key)
            self.changed('restore',{'source_revision':data.get('revision')})
