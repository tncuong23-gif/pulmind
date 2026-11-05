"""Bounded graph joins and explicit structural inference; never writes facts back."""
from copy import deepcopy
from .models import Step

RULES = {
    'is_a_transitive': {'label': 'Phân loại bắc cầu: A IS_A B, B IS_A C', 'relation': 'IS_A',
                        'families': ({'Disease','DiseaseSubtype','Syndrome'}, {'Pathogen','Bacterium','Virus','Fungus','Parasite'}, {'DrugClass'})},
    'part_of_transitive': {'label': 'Bộ phận bắc cầu: A PART_OF B, B PART_OF C', 'relation': 'PART_OF',
                          'families': ({'AnatomicalStructure','Organ','OrganSystem'},)},
}

def rule_catalog(ontology):
    return [{'id': key, 'label': r['label'], 'relation': r['relation'], 'available': ontology.has_relation(r['relation'])}
            for key,r in RULES.items()]

def fact_key(f):
    return f.subject.id, f.predicate, f.object.id

def validate_steps(service, steps):
    if not 1 <= len(steps) <= 4:
        raise ValueError('Chuỗi truy vấn cần từ 1 đến 4 bước.')
    for s in steps:
        if s.direction not in ('auto','out','in','any'):
            raise ValueError('Hướng truy vấn phải là auto/out/in/any.')
        if s.rel_types:
            bad=[r for r in s.rel_types if not service.ontology.has_relation(r)]
            if bad:raise ValueError('Quan hệ không có trong ontology: '+', '.join(bad))
        elif s.intent not in service.intents or not service.intents[s.intent].relations:
            raise ValueError('Nhóm truy vấn không có quan hệ trong ontology: '+s.intent)
        if s.target_types and any(not service.ontology.has_entity_type(t) for t in s.target_types):
            raise ValueError('Loại đích không có trong ontology.')

def walk(service, anchors, steps, limit, *, prefixes=False):
    """Keep independent paths, so joining frontiers cannot splice unrelated branches."""
    validate_steps(service, steps)
    state_limit=min(200, service.limits.max_chains)
    states=[(a, [], frozenset((a.id,))) for a in anchors][:service.limits.max_frontier]
    truncated=len(anchors)>len(states); completed=[]; cache={}; fetches=0
    for hop, step in enumerate(steps, 1):
        nxt=[]
        for anchor, path, seen in states:
            key=(anchor.id,hop)
            if key not in cache:
                if fetches>=64:
                    truncated=True;continue
                fetches+=1;diag={}
                names=step.rel_types or service.intents[step.intent].relations
                cache[key]=service.neighbors([anchor], names, target_types=step.target_types,
                    hop=hop, diagnostics=diag, direction=step.direction)
                truncated |= diag.get('query_limited',False)
            edges=cache[key]
            # Keep one branch per edge and one explicit skip branch for optional steps.
            if step.include_previous:nxt.append((anchor,path,seen))
            for f in edges:
                far=f.far_end
                if far.id in seen:continue
                new_path=path+[f]
                nxt.append((far,new_path,seen|{far.id}))
                if prefixes and len(new_path)>=2:completed.append(new_path)
                if len(nxt)>state_limit:
                    truncated=True;break
            if len(nxt)>state_limit:break
        states=nxt[:state_limit]
        if not states:break
    if not prefixes:completed=[p for _,p,_ in states if p]
    selected=[];keys=set();seen_paths=set()
    for path in completed:
        signature=tuple(fact_key(f) for f in path)
        if signature in seen_paths:continue
        fresh=set(signature)-keys
        if len(keys)+len(fresh)>limit or len(selected)>=service.limits.max_chains:
            truncated=True;continue
        selected.append(path);keys.update(fresh);seen_paths.add(signature)
    # Never return a chain after dropping one of its premises for the fact budget.
    facts={}
    for path in selected:
        for f in path:facts.setdefault(fact_key(f),f)
    selected=[[facts[fact_key(f)] for f in path] for path in selected]
    return list(facts.values()), selected, truncated

def _supports(f):
    # Structural closure only accepts unconditional, non-contradicted statements.
    # Unknown properties may encode a population, time, modality, or condition.
    if not f.assertions:return {}
    for a in f.assertions:
        props=a.get('properties',{})
        if not a.get('properties_valid',False) or set(props)-{'negated'} or props.get('negated',False) is not False:
            return {}
    out={}
    for a in f.assertions:
        for ev in f.evidence_texts:
            if ev.get('doc_id')!=a.get('document_id') or ev.get('evidence_id') not in a.get('evidence_ids',[]) or not ev.get('text'):
                continue
            source=(ev.get('source_origin') or {}).get('source_document_id') or ev['doc_id']
            out.setdefault(source,[]).append({'assertion':deepcopy(a),'evidence':deepcopy(ev)})
    return out

def infer(service, anchors, rule_id, max_hops, limit, scope):
    if rule_id not in RULES:raise ValueError('Quy tắc suy luận không được hỗ trợ.')
    if scope not in ('same_document','cross_document'):raise ValueError('Phạm vi nguồn không hợp lệ.')
    rule=RULES[rule_id];relation=rule['relation']
    if not service.ontology.has_relation(relation):raise ValueError('Ontology không có quan hệ cho quy tắc này.')
    facts,paths,truncated=walk(service,anchors,[Step('related',rel_types=(relation,),direction='out')]*max_hops,limit,prefixes=True)
    service.attach_evidence(facts)
    # Cached paths may hold separate Fact objects for the same triple.
    canonical={fact_key(f):f for f in facts}
    proofs=[];rejected=0;kept=[]
    for path in paths:
        path=[canonical[fact_key(f)] for f in path]
        types={path[0].subject.type,*[f.object.type for f in path]}
        if not any(types<=family for family in rule['families']):rejected+=1;continue
        support=[_supports(f) for f in path]
        if not all(support):rejected+=1;continue
        common=set.intersection(*(set(s) for s in support))
        if scope=='same_document' and not common:rejected+=1;continue
        premises=[]
        for f, sources in zip(path,support):
            chosen=common if scope=='same_document' else set(sources)
            premises.append({'subject':vars(f.subject),'predicate':f.predicate,'object':vars(f.object),
                'support_by_source':{src:sources[src] for src in sorted(chosen)}})
        proofs.append({'kind':'inferred','rule':rule_id,'subject':vars(path[0].subject),
            'predicate':relation,'object':vars(path[-1].object),'hops':len(path),
            'evidence_scope':scope,'source_document_ids':sorted(set().union(*(set(p['support_by_source']) for p in premises))),
            'premises':premises,'persisted':False,
            'interpretation':'structural_closure_not_diagnosis_or_treatment_recommendation'})
        kept.append(path)
    used={fact_key(f) for path in kept for f in path}
    notes=['Kết luận suy ra bằng quy tắc cấu trúc; không được ghi thành quan hệ mới trong CSDL.']
    if rejected:notes.append(f'Bỏ {rejected} đường không đủ bằng chứng văn bản, cùng nguồn, cùng họ khái niệm hoặc có thuộc tính điều kiện/phủ định.')
    if scope=='cross_document':notes.append('Đã cho phép kết hợp nguồn khác nhau; cần đối chiếu sự tương thích của tài liệu.')
    return [f for f in facts if fact_key(f) in used],kept,proofs,truncated,notes
