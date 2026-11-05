"""Exact, versioned corpus identity decisions. Never merge by similarity alone."""
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from .errors import Issue, ValidationError
from .utils import fold, sha256_of

POLICY_PATH=Path(__file__).resolve().parents[3]/'examples/kg/concept_identity_policy.json'

@lru_cache(maxsize=1)
def policy():
    return json.loads(POLICY_PATH.read_text(encoding='utf-8'))

def profile():
    return sha256_of(policy())

def registry():
    return {e['id']:(e,g) for g in policy()['groups'] for e in g['members']}

def normalization_issues(payload):
    """Block old IDs so importing old corpus cannot recreate resolved duplicates."""
    if not isinstance(payload,dict) or not isinstance(payload.get('entities'),list):return []
    known=registry();issues=[]
    approved = {(m.get('target_id'), m.get('name'), m.get('type')) for m in payload.get('document',{}).get('metadata',{}).get('manual_concept_merges',[]) if isinstance(m,dict)}
    for e in payload['entities']:
        if not isinstance(e,dict):continue
        if (e.get('id'),e.get('canonical_name'),e.get('type')) in approved:continue
        pair=known.get(e.get('id'))
        if not pair:continue
        expected,g=pair
        if e.get('type')!=expected['type'] or fold(str(e.get('canonical_name','')))!=fold(expected['canonical_name']):
            issues.append(Issue('CONCEPT_IDENTITY_MISMATCH',f"ID {e['id']} không khớp tên/loại trong bảng định danh; cần kiểm tra lại ID."))
        elif e['id']!=g['canonical_id']:
            issues.append(Issue('CONCEPT_NORMALIZATION_REQUIRED',
                'Dùng corpus đã chuẩn hóa hoặc chạy python -m scripts.kg.normalize_corpus trước khi nạp.',
                context={'original_id':e['id'],'canonical_id':g['canonical_id'],'canonical_type':g['canonical_type']}))
    return issues

def normalize_concepts(payload):
    """Offline conversion, preserving statements/evidence and all original entity records."""
    out=deepcopy(payload);known=registry();merged={};mapping={};originals=[]
    for e in out['entities']:
        original=deepcopy(e);pair=known.get(e['id'])
        if pair:
            expected,g=pair
            if e['type']!=expected['type'] or fold(e['canonical_name'])!=fold(expected['canonical_name']):
                raise ValidationError('identity mismatch',issues=[Issue('CONCEPT_IDENTITY_MISMATCH',e['id'])])
            e['id']=g['canonical_id'];e['type']=g['canonical_type'];e['canonical_name']=g['canonical_name']
        mapping[original['id']]=e['id']
        if original!=e:originals.append(original)
        if e['id'] in merged:
            existing=merged[e['id']]
            if existing.get('properties',{})!=e.get('properties',{}):
                raise ValidationError('conflicting entity properties',issues=[Issue('CONCEPT_PROPERTY_CONFLICT',e['id'])])
            originals.append(original)
            existing['aliases']=list(dict.fromkeys([*existing.get('aliases',[]),*e.get('aliases',[])]))
        else:merged[e['id']]=e
    out['entities']=list(merged.values())
    for r in out['relations']:
        for key in ('source','target'):r[key]=mapping.get(r[key],r[key])
    for p in out['propositions']:
        if 'entity_ids' in p:p['entity_ids']=list(dict.fromkeys(mapping.get(x,x) for x in p['entity_ids']))
    if originals:
        metadata=out['document'].setdefault('metadata',{})
        metadata['concept_identity']={'policy':policy()['version'],'policy_hash':profile(),
            'original_to_canonical':mapping,'original_entities':originals}
        out.pop('entity_link_decisions',None);out.pop('entity_type_decisions',None)
        # Old PASS labels predate this transformation; retain them only as history.
        for key in ('validation_summary','migration_metadata'):
            if key in out:metadata['previous_'+key]=out.pop(key)
    return out,mapping
