"""Resolve reviewed V71B identities against one immutable snapshot."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('v71b_concepts.json').read_text(encoding='utf-8'))


def snapshot_groups(snapshot):
    policy = catalog()
    documents = snapshot['documents']
    if any(documents.get(doc, {}).get('hash') != digest for doc, digest in policy['documents'].items()):
        return {}
    entities = snapshot['entities']
    mapping = snapshot['entity_mapping']
    linked = {gid for relation in snapshot['relations'].values() for gid in (relation['source'], relation['target'])}
    groups = {}
    for entry in policy['groups']:
        members = []
        for local, kind in entry['members'].items():
            gids = {mapping[doc]['ids'][local] for doc in policy['documents'] if local in mapping.get(doc, {}).get('ids', {})}
            if len(gids) != 1:
                break
            gid, = gids
            entity = entities.get(gid, {})
            if gid not in linked or entity.get('type') != kind or entity.get('canonical_name') != entry['name']:
                break
            members.append({'id':gid, 'type':kind, 'name':entry['name']})
        if len(members) == len(entry['members']) and len({row['id'] for row in members}) == len(members):
            for row in members:
                groups[row['id']] = members
    return groups


def expand_groups(groups, membership):
    for group in groups:
        candidates = group['candidates']
        if not candidates or any(row['matched_by'] == 'fuzzy' for row in candidates):
            continue
        members = membership.get(candidates[0]['id'])
        if members and {row['id'] for row in candidates} <= {row['id'] for row in members}:
            group['concept_members'] = members
