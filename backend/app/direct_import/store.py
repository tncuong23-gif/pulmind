from __future__ import annotations
import json
from collections import defaultdict
from app.kg_global.store import GlobalStore, dumps, ident
from app.modules.kg_import.models import parse_import
from app.modules.kg_import.validation import validate
from app.modules.kg_import.utils import fold, clean_text, sha256_of

POLICY = 'source-scoped-reviewed-identity/2'

class ExactStore(GlobalStore):
    """SQLite registry serializes identity; immutable snapshots isolate live readers.

    Local IDs are scoped by document/version. Historical mappings are immutable;
    redirects resolve their current canonical IDs. No fuzzy/embedding lookup.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS exact_terms(kind TEXT,term TEXT,gid TEXT NOT NULL,PRIMARY KEY(kind,term));
        CREATE TABLE IF NOT EXISTS exact_term_candidates(kind TEXT,term TEXT,gid TEXT NOT NULL,PRIMARY KEY(kind,term,gid));
        CREATE TABLE IF NOT EXISTS alias_decisions(gid TEXT,term TEXT,status TEXT,reason TEXT,PRIMARY KEY(gid,term));
        CREATE TABLE IF NOT EXISTS source_provenance(doc TEXT,version INTEGER,data TEXT NOT NULL,PRIMARY KEY(doc,version));
        CREATE TABLE IF NOT EXISTS direct_jobs(id TEXT PRIMARY KEY,state TEXT,data TEXT NOT NULL);
        ''');self.db.commit()

    def resolve_gid(self, gid):
        seen=set()
        while gid not in seen:
            seen.add(gid)
            r=self.db.execute('SELECT target FROM redirects WHERE old=?',(gid,)).fetchone()
            if not r:return gid
            gid=r[0]
        raise ValueError('Vòng lặp ánh xạ ID: '+gid)

    def check(self, payload):
        kg, issues=parse_import(payload)
        if kg is not None:issues+=validate(kg,self.ontology,self.limits)
        if issues:raise ValueError('; '.join(f'{i.path or "$"}: {i.code}: {i.message}' for i in issues[:30]))
        if kg is None:raise ValueError('JSON không hợp lệ.')
        # Complete documents are required: evidence and endpoints never guessed from other files.
        sentences={n.sentence_id for sec in kg.document.sections for par in sec.paragraphs for n in par.sentences}
        if not sentences:raise ValueError('Tài liệu phải có câu nguồn.')
        for proposition in kg.propositions:
            for ev in proposition.evidence:
                if not ev.sentence_id or ev.sentence_id not in sentences:raise ValueError('Mệnh đề '+proposition.id+': bằng chứng phải trỏ đến câu nguồn trong file.')
        ids={e.id for e in kg.entities}
        for r in kg.relations:
            if r.source not in ids or r.target not in ids:raise ValueError('Quan hệ '+r.id+': thiếu thực thể trong file.')
        return kg

    def _unify(self):
        """Refresh active declarations, never infer identity from a shared string.

        exact_terms remains a compatibility index of unambiguous terms only.
        Existing redirects are retained, not silently reversed by this migration.
        """
        declarations=defaultdict(list)
        for row in self.db.execute('SELECT * FROM documents WHERE active=1 ORDER BY doc'):
            mapping={r['local']:self.resolve_gid(r['gid']) for r in self.db.execute(
                'SELECT local,gid FROM mappings WHERE doc=? AND version=?',(row['doc'],row['version']))}
            for e in json.loads(row['payload'])['entities']:
                declarations[mapping[e['id']]].append((row['doc'],e))
        terms=defaultdict(set)
        for gid, sources in declarations.items():
            stored=json.loads(self.db.execute('SELECT data FROM entities WHERE id=?',(gid,)).fetchone()[0])
            # Reviewed names survive refresh; otherwise source order determines the name.
            canonical=stored.get('reviewed_name') or clean_text(sources[0][1]['canonical_name'])
            names={};props={}
            for _,e in sources:
                if e['type']!=stored['type'] and not stored.get('reviewed_name'):
                    raise ValueError('IDENTITY_TYPE_CONFLICT: '+gid)
                for key,value in e.get('properties',{}).items():
                    if key in props and props[key]!=value:
                        raise ValueError('IDENTITY_PROPERTY_CONFLICT: '+gid+': '+key)
                    props[key]=value
                for name in [e['canonical_name'],*e.get('aliases',[])]:
                    if fold(name):names.setdefault(fold(name),clean_text(name))
            out={**stored,'canonical_name':canonical,'aliases':[names[k] for k in sorted(names) if k!=fold(canonical)],'properties':props}
            self.db.execute('UPDATE entities SET data=? WHERE id=?',(dumps(out),gid))
            for name in [canonical,*out['aliases']]:terms[(out['type'],fold(name))].add(gid)
        rejected={(self.resolve_gid(r['gid']),r['term']) for r in self.db.execute("SELECT gid,term FROM alias_decisions WHERE status='rejected'")}
        for (kind,term),ids in terms.items():ids.difference_update({gid for gid in ids if (gid,term) in rejected})
        self.db.execute('DELETE FROM exact_terms')
        self.db.execute('DELETE FROM exact_term_candidates')
        for (kind,term),ids in sorted(terms.items()):
            for gid in sorted(ids):self.db.execute('INSERT INTO exact_term_candidates VALUES(?,?,?)',(kind,term,gid))
            if len(ids)==1:self.db.execute('INSERT INTO exact_terms VALUES(?,?,?)',(kind,term,next(iter(ids))))
        return 0

    def lookup_term(self, term, kind=None):
        """Return every active candidate; ambiguity is explicit, never an identity decision."""
        data=self.materialize()
        ids=sorted({t['entity_id'] for t in data['terms'] if t['term']==fold(term) and (kind is None or t['type']==kind)})
        return {'ambiguous':len(ids)>1,'candidates':[data['entities'][i] for i in ids]}

    def decide_alias(self,body):
        with self.write(body['revision']):
            data=self.materialize();gid=body['entity_id'];term=fold(body['term'])
            status=body['status'];reason=body.get('reason','').strip()
            e=data['entities'].get(gid)
            if not e or not term or status not in ('accepted','rejected') or not reason:
                raise ValueError('Chọn thực thể, alias, trạng thái và lý do hợp lệ.')
            if term==fold(e['canonical_name']):raise ValueError('Không đổi trạng thái tên chuẩn qua alias.')
            if not any(a['entity_id']==gid and fold(a['term'])==term and a['active_source'] for a in data['alias_sources']):
                raise ValueError('Alias phải có khai báo trong nguồn đang có hiệu lực.')
            self.db.execute('INSERT OR REPLACE INTO alias_decisions VALUES(?,?,?,?)',(gid,term,status,reason))
            self._unify()
            self.changed('alias_decision',body)
        return self.lookup_term(body['term'],e['type'])

    def ingest(self,payload,filename='',provenance=None):
        kg=self.check(payload);doc=kg.document.document_id
        provenance=provenance or {};h=sha256_of(payload)
        with self.write():
            for current in self.db.execute('SELECT payload FROM documents WHERE active=1'):
                self.check(json.loads(current[0]))
            previous=self.db.execute('SELECT * FROM documents WHERE doc=? AND active=1',(doc,)).fetchone()
            # Never overlap a cumulative package and one of its component documents.
            incoming=set(provenance.get('source_document_ids') or [doc])
            for row in self.db.execute('SELECT doc,version FROM documents WHERE active=1 AND doc<>?',(doc,)):
                p=self.db.execute('SELECT data FROM source_provenance WHERE doc=? AND version=?',(row['doc'],row['version'])).fetchone()
                sources=set(json.loads(p[0]).get('source_document_ids') or [row['doc']]) if p else {row['doc']}
                if incoming & sources:raise ValueError('SOURCE_OVERLAP: nguồn đã có trong bộ '+row['doc']+'. Chọn bản riêng hoặc bản hợp nhất, không nhập chồng.')
            if previous and previous['hash']==h:
                prior=self.db.execute('SELECT data FROM source_provenance WHERE doc=? AND version=?',(doc,previous['version'])).fetchone()
                if prior and json.loads(prior[0])!=provenance:
                    # Provenance corrections create a version even if source JSON is unchanged.
                    pass
                elif prior or not provenance:
                    merged=self._unify()
                    errors=[c for c in self.materialize()['conflicts'] if c['kind']!='polarity']
                    if errors:raise ValueError('ALIAS_GRAPH_CONFLICT: '+dumps(errors[:5]))
                    if merged:self.changed('exact_alias_migration',{'merged':merged})
                    return {'document_id':doc,'status':'unchanged','version':previous['version'],'merged':merged}
            version=self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM documents WHERE doc=?',(doc,)).fetchone()[0]
            oldents={e['id']:e for e in json.loads(previous['payload'])['entities']} if previous else {}
            oldmap={r['local']:r['gid'] for r in self.db.execute('SELECT local,gid FROM mappings WHERE doc=? AND version=?',(doc,previous['version']))} if previous else {}
            self.db.execute('UPDATE documents SET active=0 WHERE doc=?',(doc,))
            self.db.execute('INSERT INTO documents VALUES(?,?,?,?,1)',(doc,version,h,dumps(payload)))
            # Sort new declarations for deterministic canonical naming within one file.
            for e in sorted(kg.entities,key=lambda e:(e.type,fold(e.canonical_name),e.id)):
                old=oldents.get(e.id,{})
                gid=oldmap.get(e.id) if old.get('type')==e.type and fold(old.get('canonical_name',''))==fold(e.canonical_name) else None
                if gid:gid=self.resolve_gid(gid)
                else:
                    gid=ident('GE_')
                    self.db.execute('INSERT INTO entities VALUES(?,?)',(gid,dumps({'id':gid,'canonical_name':clean_text(e.canonical_name),'type':e.type,'aliases':list(e.aliases),'properties':e.properties})))
                self.db.execute('INSERT INTO mappings VALUES(?,?,?,?)',(doc,version,e.id,gid))
            self.db.execute('INSERT INTO source_provenance VALUES(?,?,?)',(doc,version,dumps(provenance)))
            merged=self._unify()
            data=self.materialize()
            errors=[c for c in data['conflicts'] if c['kind']!='polarity']
            if errors:raise ValueError('ALIAS_GRAPH_CONFLICT: '+dumps(errors[:5]))
            self.changed('exact_import',{'document_id':doc,'version':version,'filename':filename,'merged':merged,'policy':POLICY})
            return {'document_id':doc,'version':version,'status':'staged','merged':merged}

    def materialize(self):
        with self.lock:
            data=super().materialize()
            data['identity_policy']=POLICY
            data['projection_mode']='triples_only'
            legacy_merges=any(json.loads(r['data']).get('merged',0)>0 and json.loads(r['data']).get('policy')!=POLICY
                              for r in self.db.execute("SELECT data FROM audit WHERE action IN ('exact_import','exact_alias_migration')"))
            data['identity_warnings']=['Kho còn định danh đã tự gộp theo chính sách cũ; cần kiểm toán hoặc dựng kho mới từ nguồn gốc.'] if legacy_merges else []
            # Reconstruct only from active declarations, including after withdrawal/review.
            decisions={}
            for r in self.db.execute('SELECT * FROM alias_decisions ORDER BY gid,term'):
                key=(self.resolve_gid(r['gid']),r['term'])
                if decisions.get(key,{}).get('status')!='rejected':decisions[key]=dict(r)
            data['alias_decisions']=list(decisions.values())
            active_names=defaultdict(dict);active_canonical={};active_props=defaultdict(dict)
            for doc,d in data['documents'].items():
                for e in d['payload']['entities']:
                    gid=data['entity_mapping'][doc]['ids'][e['id']]
                    active_canonical.setdefault(gid,clean_text(e['canonical_name']))
                    for key,value in e.get('properties',{}).items():
                        if key in active_props[gid] and active_props[gid][key]!=value:
                            raise ValueError('IDENTITY_PROPERTY_CONFLICT: '+gid+': '+key)
                        active_props[gid][key]=value
                    for name in [e['canonical_name'],*e.get('aliases',[])]:
                        if fold(name):active_names[gid].setdefault(fold(name),clean_text(name))
            for gid,e in data['entities'].items():
                e['canonical_name']=e.get('reviewed_name') or active_canonical[gid]
                e['properties']=active_props[gid]
                e['aliases']=[n for k,n in sorted(active_names[gid].items()) if k!=fold(e['canonical_name']) and decisions.get((gid,k),{}).get('status')!='rejected']

            data['terms']=[{'key':sha256_of([e['type'],fold(n),gid]),'type':e['type'],'term':fold(n),'entity_id':gid}
                           for gid,e in data['entities'].items() for n in [e['canonical_name'],*e['aliases']]]
            buckets=defaultdict(set)
            for term in data['terms']:buckets[(term['type'],term['term'])].add(term['entity_id'])
            data['ambiguous_terms']=[{'type':kind,'term':term,'entity_ids':sorted(ids)}
                                     for (kind,term),ids in sorted(buckets.items()) if len(ids)>1]
            data['alias_sources']=[]
            for row in self.db.execute('SELECT * FROM documents ORDER BY doc,version'):
                raw=json.loads(row['payload']);mapping={r['local']:self.resolve_gid(r['gid']) for r in self.db.execute('SELECT * FROM mappings WHERE doc=? AND version=?',(row['doc'],row['version']))}
                for e in raw['entities']:
                    for n in [e['canonical_name'],*e.get('aliases',[])]:
                        data['alias_sources'].append({'id':sha256_of([row['doc'],row['version'],e['id'],n]),'document_id':row['doc'],
                            'document_version':row['version'],'original_entity_id':e['id'],'original_name':e['canonical_name'],
                            'entity_id':mapping[e['id']],'term':n,'type':e['type'],'declaration_only':True,'active_source':bool(row['active']),
                            'status':('inactive' if not row['active'] else decisions.get((mapping[e['id']],fold(n)),{}).get('status','declared')),
                            'decision_reason':decisions.get((mapping[e['id']],fold(n)),{}).get('reason')})
            for history in data['document_history']:
                row=self.db.execute('SELECT data FROM source_provenance WHERE doc=? AND version=?',(history['document_id'],history['version'])).fetchone()
                history['provenance']=json.loads(row[0]) if row else {}
                history['canonical_mapping']={local:self.resolve_gid(gid) for local,gid in history['mapping'].items()}
            for doc,d in data['documents'].items():
                row=self.db.execute('SELECT data FROM source_provenance WHERE doc=? AND version=?',(doc,d['version'])).fetchone()
                d['provenance']=json.loads(row[0]) if row else {}
            data['source_entity_mapping']=[]
            source_versions=[(doc,d,data['entity_mapping'][doc]['ids'],True) for doc,d in data['documents'].items()]
            source_versions += [(h['document_id'],h,h['canonical_mapping'],False) for h in data['document_history']]
            for doc,d,local,active_source in source_versions:
                for entry in d['provenance'].get('entity_mapping',{}).get('entity_mappings',[]):
                    merged_id=entry['merged_id']
                    for source in entry.get('sources',[]):
                        data['source_entity_mapping'].append({'id':sha256_of([doc,d['version'],source['document_id'],source['entity_id']]),
                            'import_document_id':doc,'import_version':d['version'],'source_document_id':source['document_id'],
                            'source_entity_id':source['entity_id'],'source_name':source.get('canonical_name'),
                            'import_entity_id':merged_id,'canonical_entity_id':local[merged_id],'active_source':active_source})
            for ev in data['evidence'].values():
                p=data['documents'][ev['document_id']]['provenance']
                ev['source_origin']=p.get('sentences',{}).get(ev['sentence_id'],{})
                source_id=ev['source_origin'].get('source_document_id')
                titles={x.get('document_id'):x.get('title') for x in p.get('sources',[])}
                ev['document_title']=titles.get(source_id) or data['documents'][ev['document_id']]['payload']['document']['title']
        return data

    def _restore_metadata(self,data):
        for doc,d in data['documents'].items():
            self.db.execute('INSERT OR REPLACE INTO source_provenance VALUES(?,?,?)',(doc,d['version'],dumps(d.get('provenance',{}))))
        for d in data.get('document_history',[]):
            self.db.execute('INSERT OR REPLACE INTO source_provenance VALUES(?,?,?)',(d['document_id'],d['version'],dumps(d.get('provenance',{}))))
        for d in data.get('alias_decisions',[]):
            self.db.execute('INSERT OR REPLACE INTO alias_decisions VALUES(?,?,?,?)',(d['gid'],d['term'],d['status'],d['reason']))
        self._unify()

    def seal_direct(self):
        with self.write():
            data=self.materialize()
            if not data['documents']:raise ValueError('Chưa có tài liệu.')
            errors=[c for c in data['conflicts'] if c['kind']!='polarity']
            if errors:raise ValueError(dumps(errors[:5]))
            previous=self.db.execute('SELECT id FROM snapshots WHERE revision=? ORDER BY rowid DESC LIMIT 1',(self.revision(),)).fetchone()
            if previous:
                old=self.snapshot(previous['id'])
                if old.get('identity_policy')==POLICY:return previous['id']
            sid=ident('S_');self.db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?)',(sid,self.revision(),dumps(data),sha256_of(data),'sealed','{}'))
            return sid
