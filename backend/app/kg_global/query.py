"""Bind one immutable global snapshot to one query service/request."""
import sqlite3,json,threading
from collections import defaultdict
from .store import root
from .publish import label
LOCK=threading.Lock()
class GlobalEvidence:
    def __init__(self,db,sid):self.coll=db['global_evidence'];self.sid=sid
    def fetch(self,document_id,evidence_ids):
        return {r['evidence_id']:r for r in self.coll.find({'snapshot':self.sid,'document_id':document_id,'evidence_id':{'$in':list(evidence_ids)}},{'_id':0})}
def active():
    path=root()/'global.sqlite3'
    if not path.exists():return None
    with sqlite3.connect(path,timeout=5) as db:
        row=db.execute("SELECT value FROM meta WHERE key='active'").fetchone()
        return json.loads(row[0])['id'] if row else None

def select_service(base):
    sid=active()
    if not sid or not hasattr(base,'driver'):return base
    with LOCK:
        cached=getattr(base,'_global_service',None)
        if cached and cached[0]==sid:return cached[1]
        from app.modules.kg_query.service import KGQueryService
        from app.modules.kg_query.concept_groups import snapshot_groups
        ev=GlobalEvidence(base.evidence_store.coll.database,sid) if base.evidence_store else None
        with sqlite3.connect(root()/'global.sqlite3') as db:
            snapshot=json.loads(db.execute('SELECT payload FROM snapshots WHERE id=?',(sid,)).fetchone()[0])
        from app.modules.kg_import.ontology import Ontology
        svc=KGQueryService(base.driver,Ontology.from_dict(snapshot['ontology']),database=base.database,limits=base.limits,evidence_store=ev,merge_alias_siblings=False)
        svc.concept_groups=snapshot_groups(snapshot)
        # These are IDs in the imported document, including V71B ENT_ IDs.
        source_ids=defaultdict(list)
        for document_id,mapping in sorted(snapshot.get('entity_mapping',{}).items()):
            for source_id,gid in sorted(mapping['ids'].items()):
                source_ids[gid].append({'id':source_id,'document_id':document_id})
        svc.source_entity_ids=dict(source_ids)
        svc.global_label=label(sid);svc.entity_redirects=snapshot.get('redirects',{});base._global_service=(sid,svc)
        return svc
