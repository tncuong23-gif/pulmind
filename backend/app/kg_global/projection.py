"""Validated medical-triple projection, independent of database clients."""
from .store import dumps
from app.modules.kg_import.utils import fold
from app.modules.kg_import.ontology import RELATION_TYPE_RE

PROJECTION_VERSION = 'triples-only/2'


def build_projection(data):
    entities=data['entities'];ontology=data['ontology'];nodes={};edges={}
    for rid,r in data['relations'].items():
        kind=r['type'];source=r['source'];target=r['target']
        if not RELATION_TYPE_RE.fullmatch(kind) or kind not in ontology['relation_types']:
            raise ValueError('PROJECTION_ONTOLOGY: '+kind)
        if source not in entities or target not in entities or source==target:
            raise ValueError('PROJECTION_ENDPOINT: '+rid)
        spec=ontology['relation_types'][kind]
        for eid,allowed in ((source,spec.get('domain',[])),(target,spec.get('range',[]))):
            e=entities[eid]
            if e['type'] not in ontology['entity_types'] or (allowed and e['type'] not in allowed):
                raise ValueError('PROJECTION_DOMAIN_RANGE: '+rid)
            if not isinstance(e['canonical_name'],str) or not fold(e['canonical_name']):
                raise ValueError('PROJECTION_NAME: '+eid)
            nodes[eid]={'id':eid,'canonical_name':e['canonical_name'],'entity_type':e['type'],
                        'normalized_name':fold(e['canonical_name']),'aliases':e['aliases'],
                        'normalized_aliases':sorted({fold(a) for a in e['aliases'] if fold(a)}),
                        'properties_json':dumps(e['properties'])}
        assertions=[]
        if not r['assertion_ids']:raise ValueError('PROJECTION_ASSERTIONS: '+rid)
        for aid in r['assertion_ids']:
            a=data['assertions'].get(aid)
            if not a or a['relation_id']!=rid or a.get('excluded_reason') or not a['evidence_ids'] or not a['proposition_ids']:
                raise ValueError('PROJECTION_PROVENANCE: '+rid)
            if a['document_id'] not in data['documents']:
                raise ValueError('PROJECTION_DOCUMENT: '+aid)
            for evid in a['evidence_ids']:
                ev=data['evidence'].get(evid)
                if not ev or ev['document_id']!=a['document_id'] or ev['document_version']!=a['document_version']:
                    raise ValueError('PROJECTION_EVIDENCE: '+aid)
            assertions.append({'assertion_id':aid,'rel_id':rid,'doc_id':a['document_id'],
                               'document_version':a['document_version'],'original_relation_id':a['original_relation_id'],
                               'evidence_ids':a['evidence_ids'],'proposition_ids':a['proposition_ids'],
                               'confidence':a['confidence'],'properties_json':dumps(a['properties'])})
        if r['id']!=rid:raise ValueError('PROJECTION_RELATION_ID: '+rid)
        edges[rid]={'id':rid,'s':source,'t':target,'type':kind,'assertions':dumps(assertions)}
    return {'version':PROJECTION_VERSION,'nodes':nodes,'edges':edges,
            'counts':{'source_entities':len(entities),'graph_entities':len(nodes),
                      'isolated_source_entities':len(entities)-len(nodes),'relations':len(edges)}}


def verify_projection(tx, kind, projection):
    """Compare actual endpoints, types, properties and provenance before commit."""
    actual_nodes={}
    for row in tx.run(f'MATCH (n:{kind}) RETURN properties(n) AS node'):
        node=dict(row['node']);eid=node.get('id')
        if eid in actual_nodes:raise ValueError('VERIFY_DUPLICATE_ENTITY')
        actual_nodes[eid]=node
    actual_edges={}
    for row in tx.run(f'MATCH (s)-[r]->(t) WHERE s:{kind} OR t:{kind} '
                      'RETURN r.id AS id, s.id AS s, t.id AS t, type(r) AS type, r.global_assertions AS assertions'):
        edge=dict(row);rid=edge['id']
        if rid in actual_edges:raise ValueError('VERIFY_DUPLICATE_RELATION')
        actual_edges[rid]=edge
    if actual_nodes!=projection['nodes']:raise ValueError('VERIFY_ENTITIES: dữ liệu node không khớp projection.')
    if actual_edges!=projection['edges']:raise ValueError('VERIFY_RELATIONS: số cạnh, đầu mút, loại hoặc bằng chứng không khớp.')
    foreign_count=tx.run(f'MATCH (s)-[r]->(t) WHERE (s:{kind} OR t:{kind}) '
                         f'AND NOT (s:{kind} AND t:{kind}) RETURN count(r) AS count').single()['count']
    if foreign_count:raise ValueError('VERIFY_FOREIGN_ENDPOINT: cạnh trỏ ra ngoài snapshot.')
    isolated_count=tx.run(f'MATCH (n:{kind}) WHERE NOT (n)--() RETURN count(n) AS count').single()['count']
    if isolated_count:raise ValueError('VERIFY_ISOLATED_NODE')
    term_count=tx.run(f'MATCH (n:{kind}Term) RETURN count(n) AS count').single()['count']
    if term_count:raise ValueError('VERIFY_TECHNICAL_TERMS: graph chứa node Term.')
    return {**projection['counts'],'version':PROJECTION_VERSION,'verified':True}
