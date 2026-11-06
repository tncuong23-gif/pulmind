"""Bounded, read-only browsing of the graph selected for KG queries."""
import json
import logging
from collections import defaultdict

from fastapi import HTTPException, Query

from app.modules.kg_import.utils import fold

log = logging.getLogger(__name__)
PAGE = 20
NODE = "{id: n.id, name: n.canonical_name, type: n.entity_type}"
EDGE = "{id: elementId(r), relation_id: r.id, source: s.id, target: t.id, type: type(r)}"


def page(rows):
    return {"items": rows[:PAGE], "more": len(rows) > PAGE}


def register_browse(app, get_service):
    def service(snapshot):
        try:
            svc = get_service()
        except Exception as exc:
            log.exception("Cannot initialize KG browser")
            raise HTTPException(503, "Không thể kết nối kho KG.") from exc
        current = getattr(svc, "global_label", None) or "Entity"
        if snapshot is not None and snapshot != current:
            raise HTTPException(409, "Snapshot đã thay đổi. Tải lại trang để tiếp tục.")
        return svc, current

    def read(svc, query, **params):
        try:
            return svc._read(query, **params)
        except Exception as exc:
            log.exception("KG browser read failed")
            raise HTTPException(503, "Không đọc được đồ thị Neo4j.") from exc

    @app.get("/api/browse/search")
    def search(q: str = Query("", max_length=200), kind: str = Query("", max_length=100),
               offset: int = Query(0, ge=0, le=10000), snapshot: str | None = None):
        svc, current = service(snapshot)
        rows = read(svc, f"""
            MATCH (n:Entity)
            WHERE ($kind = '' OR n.entity_type = $kind) AND
                  ($q = '' OR coalesce(n.normalized_name, toLower(n.canonical_name)) CONTAINS $q
                   OR any(a IN coalesce(n.normalized_aliases, n.aliases, []) WHERE toLower(a) CONTAINS $q)
                   OR n.id = $id)
            RETURN {NODE} AS node
            ORDER BY CASE WHEN n.normalized_name = $q OR n.id = $id THEN 0 ELSE 1 END,
                     n.canonical_name, n.id
            SKIP $offset LIMIT $limit
        """, q=fold(q), id=q.strip(), kind=kind, offset=offset, limit=PAGE + 1)
        return {**page([r["node"] for r in rows]), "snapshot": current,
                "types": sorted(svc.ontology.entity_types), "relations": svc.ontology.relation_names()}

    @app.get("/api/browse/graph")
    def graph(snapshot: str = Query(..., max_length=80), kind: str = Query(..., pattern="^(nodes|edges)$"),
              offset: int = Query(0, ge=0)):
        svc, _ = service(snapshot)
        limit = 2000
        if kind == "nodes":
            rows = read(svc, f"""
                MATCH (n:Entity)
                RETURN {NODE} AS item ORDER BY n.id, elementId(n)
                SKIP $offset LIMIT $limit
            """, offset=offset, limit=limit + 1)
        else:
            rows = read(svc, f"""
                MATCH (s:Entity)-[r]->(t:Entity)
                RETURN {EDGE} AS item ORDER BY elementId(r)
                SKIP $offset LIMIT $limit
            """, offset=offset, limit=limit + 1)
        return {"items": [row["item"] for row in rows[:limit]],
                "next": offset + limit if len(rows) > limit else None}

    @app.get("/api/browse/node")
    def node(id: str = Query(..., max_length=200), snapshot: str = Query(..., max_length=80),
             relation: str = Query("", max_length=100), kind: str = Query("", max_length=100),
             offset: int = Query(0, ge=0, le=10000)):
        svc, _ = service(snapshot)
        details = read(svc, f"""
            MATCH (n:Entity {{id: $id}})
            RETURN {NODE} AS node, n.aliases AS aliases, n.properties_json AS attributes
        """, id=id)
        if not details:
            raise HTTPException(404, "Không tìm thấy thực thể.")
        rows = read(svc, f"""
            MATCH (a:Entity {{id: $id}})-[r]-(n:Entity)
            WHERE ($relation = '' OR type(r) = $relation) AND ($kind = '' OR n.entity_type = $kind)
            WITH r, n, startNode(r) AS s, endNode(r) AS t
            RETURN DISTINCT {EDGE} AS edge, {NODE} AS neighbor
            ORDER BY edge.relation_id, edge.id
            SKIP $offset LIMIT $limit
        """, id=id, relation=relation, kind=kind, offset=offset, limit=PAGE + 1)
        source_ids = getattr(svc, 'source_entity_ids', {}).get(details[0]['node']['id'], [])
        return {**details[0], 'source_ids': source_ids, **page(rows)}

    @app.get("/api/browse/edge")
    def edge(id: str = Query(..., max_length=200), snapshot: str = Query(..., max_length=80),
             offset: int = Query(0, ge=0, le=10000)):
        svc, _ = service(snapshot)
        rows = read(svc, f"""
            MATCH (s:Entity)-[r]->(t:Entity) WHERE elementId(r) = $id
            RETURN {EDGE} AS edge, s.canonical_name AS subject, t.canonical_name AS object,
                   r.global_assertions AS assertions, r.source_document_id AS document,
                   r.evidence_ids AS evidence, r.properties_json AS attributes,
                   r.confidence AS confidence, r.source_proposition_ids AS propositions
        """, id=id)
        if not rows:
            raise HTTPException(404, "Không tìm thấy quan hệ.")
        row = rows[0]
        assertions = json.loads(row["assertions"]) if row["assertions"] else [{
            "doc_id": row["document"], "evidence_ids": row["evidence"] or [],
            "properties_json": row["attributes"], "confidence": row["confidence"],
            "proposition_ids": row["propositions"] or [],
        }]
        keys = list(dict.fromkeys((a["doc_id"], eid) for a in assertions
                                  if a.get("doc_id") for eid in a.get("evidence_ids", [])))
        groups = defaultdict(list)
        for doc, eid in keys[offset:offset + PAGE]:
            groups[doc].append(eid)
        evidence = []
        unavailable = not svc.evidence_store
        if not unavailable:
            try:
                for doc, ids in groups.items():
                    found = svc.evidence_store.fetch(doc, ids)
                    evidence.extend({k: found[eid].get(k) for k in (
                        "evidence_id", "document_id", "document_title", "source_origin",
                        "text", "section_id", "section_title", "sentence_id", "location"
                    )} for eid in ids if eid in found)
            except Exception:
                log.exception("KG browser evidence lookup failed")
                unavailable = True
        return {"edge": row["edge"], "subject": row["subject"], "object": row["object"],
                "assertions": [{k: v for k, v in a.items() if k != "evidence_ids"}
                               for a in assertions[offset:offset + PAGE]],
                "assertion_count": len(assertions), "evidence": evidence,
                "evidence_count": len(keys), "unavailable": unavailable,
                "more": max(len(keys), len(assertions)) > offset + PAGE}
