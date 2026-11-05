"""Read JSON/ZIP data only; no extraction or execution of scripts in a package."""
import hashlib, io, json, zipfile
from pathlib import PurePosixPath
from copy import deepcopy
MAX_FILE=20*1024*1024
MAX_ZIP=64*1024*1024
MAX_EXPANDED=128*1024*1024

def read_json(data):
    if len(data)>MAX_FILE:raise ValueError('JSON vượt 20 MiB.')
    try:value=json.loads(data.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise ValueError('JSON không hợp lệ.')
    if not isinstance(value,dict):raise ValueError('JSON phải là một đối tượng.')
    return value

def load_package(content,filename,selection='merged'):
    if len(content)>MAX_ZIP:raise ValueError('File vượt 64 MiB.')
    if 'review' in PurePosixPath(filename.replace('\\','/')).name.casefold():
        raise ValueError('Không tự nhập bộ quan hệ cần rà soát kg_review.json.')
    provenance={'input_sha256':hashlib.sha256(content).hexdigest(),'filename':PurePosixPath(filename).name}
    if not filename.lower().endswith('.zip'):
        raw=read_json(content)
        doc=raw.get('document',{}).get('document_id')
        # Known cumulative format requires its mapping; do not silently lose provenance.
        if raw.get('document',{}).get('document_type')=='clinical_guideline_collection':
            raise ValueError('Bản hợp nhất cần ZIP có cumulative_source_mapping.json để giữ đúng nguồn.')
        provenance.update(source_document_ids=[doc],sentences={})
        return raw,provenance
    if selection not in ('merged','single'):raise ValueError('Chọn bản hợp nhất hoặc tài liệu riêng.')
    try:z=zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:raise ValueError('ZIP không hợp lệ.')
    with z:
        infos=z.infolist()
        if len(infos)>2000 or sum(i.file_size for i in infos)>MAX_EXPANDED:raise ValueError('ZIP quá nhiều file hoặc vượt giới hạn giải nén.')
        paths={}
        for i in infos:
            p=PurePosixPath(i.filename.replace('\\','/'))
            if p.is_absolute() or '..' in p.parts or ':' in i.filename:raise ValueError('Đường dẫn ZIP không hợp lệ.')
            if i.filename in paths:raise ValueError('ZIP có đường dẫn trùng.')
            paths[i.filename]=i
        wanted='kg_merged.json' if selection=='merged' else 'kg_import.json'
        candidates=[n for n in paths if PurePosixPath(n).name==wanted]
        if len(candidates)!=1:raise ValueError('ZIP phải chứa đúng một '+wanted+'.')
        name=candidates[0];base=str(PurePosixPath(name).parent)
        def sibling(n):return n if base=='.' else base+'/'+n
        def optional(n):
            path=sibling(n)
            if path not in paths:return None
            if paths[path].file_size>MAX_FILE:raise ValueError(n+' vượt giới hạn.')
            return json.loads(z.read(path).decode('utf-8-sig'))
        raw=read_json(z.read(name));provenance['input_sha256']=hashlib.sha256(z.read(name)).hexdigest();provenance['selected_file']=name
        ontology=optional('ontology_used.json')
        if ontology:provenance['ontology']=ontology
        doc=raw.get('document',{}).get('document_id')
        sentences={s['sentence_id']:s['text'] for sec in raw.get('document',{}).get('sections',[]) for p in sec.get('paragraphs',[]) for s in p.get('sentences',[])}
        origins={}
        if selection=='merged':
            mapping=optional('cumulative_source_mapping.json')
            if not isinstance(mapping,dict) or mapping.get('merged_document_id')!=doc:raise ValueError('Thiếu hoặc sai ánh xạ nguồn bản hợp nhất.')
            source_ids={s['document_id'] for s in mapping['sources']}
            maps={}
            # Carry source line/file/hash when a sidecar supplies them.
            for side in ('source_mapping.json','DOC_000002_source_mapping.json','previous_cumulative_source_mapping.json'):
                value=optional(side)
                rows=value if isinstance(value,list) else value.get('sentences',[]) if isinstance(value,dict) else []
                for r in rows:
                    d=r.get('source_document_id',r.get('document_id'));sid=r.get('source_sentence_id',r.get('sentence_id'))
                    if d and sid:maps[(d,sid)]=r
            for r in mapping.get('sentences',[]):
                sid=r.get('merged_sentence_id');src=r.get('source_document_id');orig=r.get('source_sentence_id')
                if sid not in sentences or src not in source_ids or not orig or sid in origins:raise ValueError('Ánh xạ câu nguồn không hợp lệ hoặc trùng.')
                origin={**maps.get((src,orig),{}),'source_document_id':src,'source_sentence_id':orig}
                origin.pop('merged_sentence_id',None)
                origins[sid]=origin
            provenance['source_document_ids']=sorted(source_ids);provenance['sources']=mapping['sources'];provenance['cumulative_mapping']=mapping
        else:
            mapping=optional('source_mapping.json')
            if mapping is not None:
                if not isinstance(mapping,list):raise ValueError('source_mapping.json phải là danh sách.')
                for r in mapping:
                    sid=r.get('sentence_id')
                    if sid not in sentences or r.get('document_id')!=doc or sid in origins:raise ValueError('Ánh xạ nguồn không hợp lệ.')
                    origins[sid]={**r,'source_document_id':doc,'source_sentence_id':sid}
            provenance['source_document_ids']=[doc]
        if (selection=='merged' or origins) and set(origins)!=set(sentences):raise ValueError('Ánh xạ nguồn chưa bao phủ đầy đủ các câu.')
        # source_sha256 in the supplied extraction package hashes the original
        # Markdown LINE, not the whole file. Verify against the declared line.
        cache={}
        for origin in origins.values():
            source=origin.get('source_file');expected=origin.get('source_sha256')
            if source:
                possibilities=[sibling('sources/'+PurePosixPath(source).name),sibling(PurePosixPath(source).name)]
                path=next((p for p in possibilities if p in paths),None)
                if path is None:raise ValueError('Thiếu file nguồn được khai báo trong ánh xạ: '+source)
                if path:
                    if path not in cache:
                        data=z.read(path);cache[path]=(hashlib.sha256(data).hexdigest(),data.decode('utf-8-sig').splitlines())
                    file_hash,lines=cache[path];line=origin.get('source_line')
                    origin['source_file_sha256']=file_hash
                    if expected:
                        if expected==file_hash:origin['source_hash_scope']='file'
                        elif isinstance(line,int) and 1<=line<=len(lines) and hashlib.sha256(lines[line-1].encode()).hexdigest()==expected:
                            origin['source_hash_scope']='line'
                        else:raise ValueError('Hash nguồn không khớp file/dòng: '+source+' dòng '+str(line))
        manifest=optional('manifest_sha256.json')
        if manifest:
            for path in (name,*cache):
                relative=path[len(base)+1:] if base!='.' else path
                expected=manifest.get('files',{}).get(relative,{}).get('sha256')
                if expected and hashlib.sha256(z.read(path)).hexdigest()!=expected:raise ValueError('Manifest không khớp: '+relative)
        entity_mapping=optional('entity_mapping.json') if selection=='merged' else None
        if selection=='merged':
            if not isinstance(entity_mapping,dict) or entity_mapping.get('merged_document_id')!=doc:
                raise ValueError('Bản hợp nhất cần entity_mapping.json để giữ ID thực thể từ các tài liệu gốc.')
            known_entities={e['id'] for e in raw.get('entities',[])}
            mapped=set();source_keys=set()
            for entry in entity_mapping.get('entity_mappings',[]):
                merged_id=entry.get('merged_id')
                if merged_id not in known_entities or merged_id in mapped:raise ValueError('Ánh xạ thực thể trỏ ID không tồn tại hoặc bị lặp.')
                mapped.add(merged_id)
                if not entry.get('sources'):raise ValueError('Ánh xạ thực thể thiếu nguồn gốc.')
                for source in entry['sources']:
                    key=(source.get('document_id'),source.get('entity_id'))
                    if key[0] not in source_ids or not key[1]:raise ValueError('Ánh xạ thực thể thiếu nguồn/ID gốc.')
                    if key in source_keys:raise ValueError('Một ID thực thể nguồn có nhiều ánh xạ hoặc bị lặp.')
                    source_keys.add(key)
            if mapped!=known_entities:raise ValueError('Ánh xạ thực thể chưa bao phủ đầy đủ dữ liệu.')
            provenance['entity_mapping']=entity_mapping
        alias_evidence=optional('alias_evidence.json')
        if alias_evidence is not None:
            if not isinstance(alias_evidence,list):raise ValueError('alias_evidence.json phải là danh sách.')
            # Keep original attestation records; do not infer sentence IDs for them.
            provenance['alias_evidence']=alias_evidence
        provenance['sentences']=origins
        return raw,provenance

def rag_payload(raw,provenance):
    out=deepcopy(raw)
    out['document'].setdefault('metadata',{})['import_provenance']=deepcopy({k:v for k,v in provenance.items() if k not in ('filename','selected_file')})
    for sec in out['document']['sections']:
        for p in sec['paragraphs']:
            for s in p['sentences']:
                s['source_origin']=deepcopy(provenance.get('sentences',{}).get(s['sentence_id'],{'source_document_id':raw['document']['document_id'],'source_sentence_id':s['sentence_id']}))
    return out
