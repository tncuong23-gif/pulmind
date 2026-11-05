"""Explicit concept merge preview/commit, independent of document import commits."""
from copy import deepcopy
import json,secrets,time
from .models import parse_import
from .validation import validate
from .utils import clean_text,fold,sha256_of,utcnow_iso

MAX_EDGES=2000

def snapshot_hash(snapshot):
    return sha256_of(snapshot)

def rewrite(payload, ids, target):
    if payload is None:return None
    out=deepcopy(payload);selected=set(ids);old=[e for e in out.get('entities',[]) if e['id'] in selected]
    out['entities']=[e for e in out.get('entities',[]) if e['id'] not in selected]
    out['entities'].append({'id':target['id'],'canonical_name':target['canonical_name'],'type':target['entity_type'],
        'aliases':target['aliases'],'properties':json.loads(target['properties_json'])})
    mapping={eid:target['id'] for eid in ids}
    for r in out.get('relations',[]):
        for key in ('source','target'):r[key]=mapping.get(r[key],r[key])
    for p in out.get('propositions',[]):
        if 'entity_ids' in p:p['entity_ids']=list(dict.fromkeys(mapping.get(e,e) for e in p['entity_ids']))
    # Only the merged members lose their former decisions. Unrelated approvals survive.
    for key in ('entity_link_decisions','entity_type_decisions'):
        if key in out:
            out[key] = {eid: (mapping.get(value, value) if key == 'entity_link_decisions' else value)
                        for eid, value in out[key].items() if eid not in selected}
    meta=out['document'].setdefault('metadata',{})
    meta.setdefault('manual_concept_merges',[]).append({'ids':ids,'target_id':target['id'],
        'name':target['canonical_name'],'type':target['entity_type'],'original_entities':old})
    return out

def resolve_redirects(payload, graph):
    """Old IDs survive as EntityAlias records; retain original payload facts in metadata."""
    if not isinstance(payload,dict):return payload
    if not isinstance(payload.get('entities',[]),list) or not isinstance(payload.get('relations',[]),list):return payload
    ids={e.get('id') for e in payload.get('entities',[]) if isinstance(e,dict) and isinstance(e.get('id'),str)}
    for r in payload.get('relations',[]):
        if isinstance(r,dict):ids.update(v for k,v in r.items() if k in ('source','target') and isinstance(v,str))
    fn=getattr(graph,'entity_redirects',None)
    if not fn or not ids:return payload
    redirects=fn(sorted(ids));out=payload
    links=payload.get('entity_link_decisions',{})
    if isinstance(links,dict):
        destinations=fn(sorted({v for v in links.values() if isinstance(v,str) and v!='new'}))
        if destinations:
            out=deepcopy(payload)
            out['entity_link_decisions']={k:destinations[v]['id'] if v in destinations else v for k,v in links.items()}
    targets={t['id']:t for t in redirects.values()}
    for target in targets.values():
        members=[old for old,t in redirects.items() if t['id']==target['id']]
        if target['id'] not in members and any(e.get('id')==target['id'] for e in out.get('entities',[])):members.append(target['id'])
        current=next((e for e in out.get('entities',[]) if e.get('id')==target['id']),None)
        if members==[target['id']] and current and current.get('type')==target['entity_type'] and current.get('canonical_name')==target['canonical_name']:
            continue
        # Do not silently discard changed custom properties on a retired ID.
        for e in out.get('entities',[]):
            if e.get('id') in members and e.get('properties') and e['properties']!=json.loads(target.get('properties_json') or '{}'):
                raise ValueError('Thuộc tính của ID cũ khác node chuẩn; cần duyệt lại trước khi nạp.')
        out=rewrite(out,members,target)
    return out

class ManualMerge:
    def __init__(self, importer):self.imp=importer;self.tokens={}
    def preview(self,payload,choice):
        if not isinstance(choice,dict):raise ValueError('Thiếu lựa chọn gộp.')
        ids=choice.get('ids');tid=choice.get('target_id');kind=choice.get('type');name=choice.get('name')
        if not isinstance(ids,list) or not 2<=len(ids)<=20 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids):raise ValueError('Chọn từ 2 đến 20 ID khác nhau.')
        if tid not in ids or kind not in self.imp.ontology.entity_types or not isinstance(name,str) or not name.strip() or len(name)>500:raise ValueError('Chọn ID chuẩn, tên và loại hợp lệ.')
        local={}
        if payload is not None:
            kg,issues=parse_import(payload)
            if kg is None:raise ValueError('Tài liệu sai cấu trúc: '+ '; '.join(i.message for i in issues))
            local={e.id:{'id':e.id,'entity_type':e.type,'canonical_name':e.canonical_name,'aliases':list(e.aliases),'properties_json':json.dumps(e.properties)} for e in kg.entities}
        retired=self.imp.graph.entity_redirects(ids)
        if any(old!=row['id'] for old,row in retired.items()):raise ValueError('Có ID đã gộp trước đó; mở lại tài liệu/graph để dùng ID chuẩn hiện hành.')
        snap=self.imp.graph.merge_snapshot(ids,MAX_EDGES)
        stored={e['id']:e for e in snap['nodes']};members={**local,**stored}
        if any(i not in members for i in ids):raise ValueError('Thực thể đã thay đổi/không tồn tại; xem trước lại.')
        props={};aliases=[];source_ids=[];conflicts=[]
        for i in ids:
            for row in [local.get(i),stored.get(i)]:
                if not row:continue
                p=json.loads(row.get('properties_json') or '{}')
                for k,v in p.items():
                    if k in props and props[k]!=v:conflicts.append({'code':'PROPERTY_CONFLICT','entity_id':i,'message':f'Thuộc tính {k} khác nhau; cần xử lý trước khi gộp.'})
                    props[k]=v
                aliases.extend([row['canonical_name'],*(row.get('aliases') or [])]);source_ids.extend(row.get('source_ids') or [])
        target={'id':tid,'entity_type':kind,'canonical_name':clean_text(name),'normalized_name':fold(name),
            'aliases':list(dict.fromkeys(a for a in aliases if fold(a)!=fold(name))),
            'properties_json':json.dumps(props,ensure_ascii=False,sort_keys=True),'source_ids':sorted(set(source_ids)),
            'merge_member_ids':sorted(set(ids+ [old for i in ids for old in members[i].get('merge_member_ids',[])]))}
        target['merge_originals_json']=json.dumps([members[i] for i in ids],ensure_ascii=False,default=str)
        target['content_hash']=sha256_of({'entity_type':kind,'canonical_name':target['canonical_name'],'aliases':target['aliases'],'properties':props})
        updated=rewrite(payload,ids,target)
        if updated:
            kg,issues=parse_import(updated)
            if kg:issues+=validate(kg,self.imp.ontology,self.imp.limits)
            conflicts.extend(i.to_dict() for i in issues)
        edges=[]
        for edge in snap['edges']:
            s=tid if edge['source_id'] in ids else edge['source_id'];t=tid if edge['target_id'] in ids else edge['target_id']
            st=kind if edge['source_id'] in ids else edge['source_type'];tt=kind if edge['target_id'] in ids else edge['target_type']
            if edge['type'] not in self.imp.ontology.relations:msg='Loại quan hệ ngoài ontology; không tự sửa.'
            else:msg=self.imp.ontology.domain_range_error(edge['type'],st,tt)
            if msg:conflicts.append({'code':'RELATION_TYPE_CONFLICT','relation_id':edge['props'].get('id'),'message':msg})
            if s==t:conflicts.append({'code':'SELF_RELATION','relation_id':edge['props'].get('id'),'message':'Gộp tạo quan hệ tự nối; cần duyệt riêng.'})
            edges.append({'id':edge['props'].get('id'),'relation':edge['type'],'before':[edge['source_id'],edge['target_id']],
                'after':[s,t],'document_id':edge['props'].get('source_document_id'),'evidence_ids':edge['props'].get('evidence_ids',[])})
        if updated:
            for r in updated.get('relations',[]):
                if r['source']==r['target']:conflicts.append({'code':'SELF_RELATION','relation_id':r['id'],'message':'Gộp tạo quan hệ tự nối trong tài liệu.'})
        result={'target':target,'members':[members[i] for i in ids],'stored_nodes':len(stored),'stored_relations':edges,
            'document_relations':[{'id':r['id'],'relation':r['type'],'after':[r['source'],r['target']]} for r in (updated or {}).get('relations',[]) if tid in (r['source'],r['target'])],
            'conflicts':conflicts,'can_apply':not conflicts}
        now=time.monotonic();self.tokens={k:v for k,v in self.tokens.items() if v['expires']>now}
        if len(self.tokens)>=128:self.tokens.pop(next(iter(self.tokens)))
        if not conflicts:
            token=secrets.token_urlsafe(32);self.tokens[token]={'expires':now+600,'payload_hash':sha256_of(payload),
                'snapshot':snap,'target':target,'ids':ids,'payload':updated,'choice':deepcopy(choice)};result['token']=token
        return result
    def apply(self,payload,token):
        from app.kg_global.query import active
        if active():raise ValueError('KG global đang hoạt động; duyệt nhóm trong Kho global.')
        saved=self.tokens.get(token)
        if not saved or saved['expires']<time.monotonic() or sha256_of(payload)!=saved['payload_hash']:raise ValueError('Xem trước đã hết hạn hoặc tài liệu thay đổi; xem trước lại.')
        # Always recheck the graph inside its write transaction, before any changes.
        self.imp.graph.apply_merge(saved['ids'],saved['target'],saved['snapshot'],token,MAX_EDGES)
        self.imp.invalidate_previews();warning=None
        if self.imp.entity_index:
            try:
                self.imp.entity_index.delete_entities(saved['target']['merge_member_ids'])
                self.imp.entity_index.upsert_entities([saved['target']])
            except Exception:
                warning='Graph đã gộp; đồng bộ vector chưa hoàn tất. Chạy python -m scripts.kg.reindex_merged để đồng bộ lại chỉ mục.'
        self.tokens.pop(token,None)
        return {'applied':True,'payload':saved['payload'],'canonical_id':saved['target']['id'],
            'warning':warning,'message':'Đã gộp khái niệm. Tài liệu vẫn cần xem trước và lưu duyệt trước khi nạp.'}

def manager(importer):
    if not hasattr(importer,'_manual_merge'):importer._manual_merge=ManualMerge(importer)
    return importer._manual_merge
