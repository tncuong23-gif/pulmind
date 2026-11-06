"""Review literal canonical-name duplicates in one revision-guarded transaction."""
from collections import defaultdict

from app.modules.kg_import.utils import sha256_of


def plan(store):
    data = store.materialize()
    groups = defaultdict(list)
    for gid, entity in data['entities'].items():
        groups[(entity['type'], entity['canonical_name'])].append(gid)
    groups = {key: sorted(ids) for key, ids in groups.items() if len(ids) > 1}
    membership = {gid: key for key, ids in groups.items() for gid in ids}
    related = defaultdict(list)
    for relation in data['relations'].values():
        keys = {membership.get(relation['source']), membership.get(relation['target'])}
        for key in keys - {None}:
            related[key].append(relation)
    distinct = {row[0] for row in store.db.execute('SELECT pair FROM distinct_pairs')}
    eligible, blocked, changes = [], [], []
    for (kind, name), ids in sorted(groups.items()):
        # The lexicographically first ID is stable between preview and confirmation.
        row = {'type': kind, 'name': name, 'ids': ids, 'target_id': ids[0]}
        try:
            if len(ids) > 1000:
                raise ValueError('Nhóm vượt quá 1.000 thực thể.')
            result = store.validate_merge(data, ids, ids[0], kind, name, related[(kind, name)], distinct)
        except ValueError as error:
            blocked.append({**row, 'reason': str(error)})
        else:
            eligible.append(row)
            changes.append((ids, result))
    revision = data['revision']
    preview = {'revision': revision, 'eligible': eligible, 'blocked': blocked}
    preview['token'] = sha256_of(preview)
    return preview, changes


def preview(store):
    # Hold a consistent SQLite revision while reading registry and review decisions.
    with store.write():
        return plan(store)[0]


def confirm(store, revision, token):
    with store.write(revision):
        report, changes = plan(store)
        if report['token'] != token:
            raise ValueError('Bản xem trước không còn hợp lệ. Hãy quét lại.')
        if not changes:
            raise ValueError('Không có nhóm đủ điều kiện hợp nhất.')
        for ids, result in changes:
            store.apply_merge(ids, result)
        store._unify()
        store.changed('batch_exact_name_merge', {'groups': report['eligible'], 'preview_token': token})
        return {'merged_groups': len(changes), 'retired_entities': sum(len(ids)-1 for ids, _ in changes),
                'blocked_groups': len(report['blocked']), 'revision': store.revision()}
