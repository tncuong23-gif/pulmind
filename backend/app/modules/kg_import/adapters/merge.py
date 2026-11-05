"""Atomic graph merge adapters; original nodes are archived as EntityAlias, never discarded."""
from copy import deepcopy
import json
from ..manual_merge import snapshot_hash
from ..utils import sha256_of,utcnow_iso
from ..ontology import RELATION_TYPE_RE

def moved_props(edge,ids,target):
    p=deepcopy(edge['props']);s=target if edge['source_id'] in ids else edge['source_id'];t=target if edge['target_id'] in ids else edge['target_id']
    p['content_hash']=sha256_of({'type':edge['type'],'source':s,'target':t,'confidence':p.get('confidence'),
        'properties':json.loads(p.get('properties_json') or '{}'),'propositions':p.get('source_proposition_ids',[]),'evidence':p.get('evidence_ids',[])})
    return s,t,p

class Neo4jMergeMixin:
    def _merge_snapshot(self,tx,ids,limit):
        nodes=[dict(r['p']) for r in tx.run('MATCH (e:Entity) WHERE e.id IN $ids RETURN properties(e) AS p ORDER BY e.id',ids=ids)]
        for n in nodes:n.pop('_merge_lock',None)
        records=list(tx.run('''MATCH (s)-[r]->(t) WHERE s.id IN $ids OR t.id IN $ids
            RETURN properties(r) AS p, type(r) AS type, s.id AS source_id, t.id AS target_id,
            s.entity_type AS source_type, t.entity_type AS target_type,
            s:Entity AS source_entity, t:Entity AS target_entity ORDER BY type, r.id LIMIT $limit''',ids=ids,limit=limit+1))
        if len(records)>limit:raise ValueError('Quá nhiều quan hệ cho một lần gộp; chia nhóm hoặc xử lý ngoại tuyến.')
        edges=[]
        for r in records:
            if not r['source_entity'] or not r['target_entity'] or not r['p'].get('id'):raise ValueError('Có quan hệ ngoài KG được quản lý; không tự di chuyển.')
            edges.append({'props':dict(r['p']),'type':r['type'],'source_id':r['source_id'],'target_id':r['target_id'],'source_type':r['source_type'],'target_type':r['target_type']})
        return {'nodes':nodes,'edges':edges}
    def merge_snapshot(self,ids,limit):
        with self.driver.session(database=self.database) as s:return s.execute_read(lambda tx:self._merge_snapshot(tx,ids,limit))
    def entity_redirects(self,ids):
        q='''MATCH (a:EntityAlias) WHERE a.id IN $ids MATCH (e:Entity {id:a.merged_into}) RETURN a.id AS old, properties(e) AS p
        UNION MATCH (e:Entity) WHERE e.id IN $ids AND e.merge_originals_json IS NOT NULL RETURN e.id AS old, properties(e) AS p'''
        with self.driver.session(database=self.database) as s:return {r['old']:dict(r['p']) for r in s.execute_read(lambda tx:list(tx.run(q,ids=ids)))}
    def apply_merge(self,ids,target,expected,token,limit):
        def work(tx):
            # Locks endpoint nodes, serializing relationship creation against the snapshot check.
            tx.run('MATCH (e:Entity) WHERE e.id IN $ids SET e._merge_lock = true',ids=ids).consume()
            current=self._merge_snapshot(tx,ids,limit)
            if snapshot_hash(current)!=snapshot_hash(expected):raise ValueError('Graph đã thay đổi sau xem trước; hãy xem trước lại.')
            if tx.run('MATCH (a:EntityAlias {id:$id}) RETURN a.id',id=target['id']).single():raise ValueError('ID chuẩn đã là bí danh; chọn node hiện hành.')
            # Every edge is recreated with the SAME relationship ID and properties in one transaction.
            for edge in current['edges']:
                kind=edge['type']
                if not RELATION_TYPE_RE.fullmatch(kind):raise ValueError('Invalid relationship type')
                tx.run(f'MATCH (s:Entity {{id:$s}})-[r:`{kind}` {{id:$id}}]->(t:Entity {{id:$t}}) DELETE r',id=edge['props']['id'],s=edge['source_id'],t=edge['target_id']).consume()
            tx.run('MERGE (e:Entity {id:$id}) SET e += $props REMOVE e._merge_lock',id=target['id'],props={**target,'updated_at':utcnow_iso()}).consume()
            for edge in current['edges']:
                s,t,p=moved_props(edge,ids,target['id']);kind=edge['type']
                tx.run(f'MATCH (s:Entity {{id:$s}}),(t:Entity {{id:$t}}) CREATE (s)-[r:`{kind}`]->(t) SET r=$props',s=s,t=t,props=p).consume()
            retired=[i for i in ids if i!=target['id']]
            tx.run('''MATCH (e:Entity) WHERE e.id IN $ids REMOVE e:Entity SET e:EntityAlias, e.merged_into=$target REMOVE e._merge_lock''',ids=retired,target=target['id']).consume()
            tx.run('UNWIND $ids AS id MERGE (a:EntityAlias {id:id}) SET a.merged_into=$target',ids=retired,target=target['id']).consume()
            tx.run('MATCH (a:EntityAlias) WHERE a.merged_into IN $ids SET a.merged_into=$target',ids=retired,target=target['id']).consume()
            tx.run('CREATE (a:KGMergeAudit {id:$id, created_at:$now, target_id:$target, snapshot_json:$snapshot})',id=token,now=utcnow_iso(),target=target['id'],snapshot=json.dumps(current,ensure_ascii=False,default=str)).consume()
        with self.driver.session(database=self.database) as s:s.execute_write(work)

class MemoryMergeMixin:
    def merge_snapshot(self,ids,limit):
        nodes=[deepcopy(self.entities[i]) for i in sorted(ids) if i in self.entities];edges=[]
        for r in sorted(self.relations.values(),key=lambda r:(r['type'],r['id'])):
            if r['source_id'] not in ids and r['target_id'] not in ids:continue
            p={k:v for k,v in r.items() if k not in ('source_id','target_id','type')}
            p['source_proposition_ids']=p.pop('proposition_ids',p.get('source_proposition_ids',[]))
            edges.append({'props':p,'type':r['type'],'source_id':r['source_id'],'target_id':r['target_id'],
                'source_type':self.entities[r['source_id']]['entity_type'],'target_type':self.entities[r['target_id']]['entity_type']})
        if len(edges)>limit:raise ValueError('Too many relations')
        return {'nodes':nodes,'edges':edges}
    def entity_redirects(self,ids):
        aliases=getattr(self,'merge_aliases',{})
        return {**{i:deepcopy(self.entities[aliases[i]['merged_into']]) for i in ids if i in aliases},
            **{i:deepcopy(self.entities[i]) for i in ids if i in self.entities and self.entities[i].get('merge_originals_json')}}
    def apply_merge(self,ids,target,expected,token,limit):
        if self.fail_on_write:raise RuntimeError('injected merge failure')
        if snapshot_hash(self.merge_snapshot(ids,limit))!=snapshot_hash(expected):raise ValueError('Graph changed; preview again')
        ents=deepcopy(self.entities);rels=deepcopy(self.relations);aliases=deepcopy(getattr(self,'merge_aliases',{}))
        if target['id'] in aliases:raise ValueError('Target is retired')
        ents[target['id']]={**ents.get(target['id'],{}),**target}
        for edge in expected['edges']:
            s,t,p=moved_props(edge,ids,target['id']);p['proposition_ids']=p.pop('source_proposition_ids',[])
            rels[p['id']]={**p,'type':edge['type'],'source_id':s,'target_id':t}
        for i in ids:
            if i!=target['id']:aliases[i]={**ents.pop(i,{'id':i}),'merged_into':target['id']}
        for a in aliases.values():
            if a['merged_into'] in ids:a['merged_into']=target['id']
        self.entities,self.relations,self.merge_aliases=ents,rels,aliases
        if not hasattr(self,'merge_audits'):self.merge_audits={}
        self.merge_audits[token]=deepcopy(expected)
